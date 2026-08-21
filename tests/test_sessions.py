"""Tests for Slice 7: Durable Session Storage, JSONL Tree, and Context Compaction."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.session.compactor import (
    ContextCompactor,
    estimate_chat_messages_tokens,
)
from mia_agent.session.entries import (
    CompactionEntry,
    LeafEntry,
    MessageEntry,
    SessionInfoEntry,
)
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree, SessionTreeError
from mia_ai.types import ChatMessage


def test_session_entries_serialization() -> None:
    msg_entry = MessageEntry(
        parent_id=None,
        message=ChatMessage(role="user", content="Build a parser"),
    )
    assert msg_entry.type == "message"
    assert msg_entry.id is not None
    assert msg_entry.timestamp > 0
    assert msg_entry.message.content == "Build a parser"

    comp_entry = CompactionEntry(
        parent_id=msg_entry.id,
        summary="## Goal\nBuild a parser\n## Progress\nDone",
        replaces_entry_ids=[msg_entry.id],
    )
    assert comp_entry.type == "compaction"
    assert comp_entry.parent_id == msg_entry.id
    assert comp_entry.replaces_entry_ids == [msg_entry.id]


def test_jsonl_session_store_append_and_read(tmp_path: Path) -> None:
    session_file = tmp_path / "test_session.jsonl"
    store = JsonlSessionStore(session_file)

    assert store.load_entries() == []

    e1 = SessionInfoEntry(title="Test Coding Session", cwd="/tmp/project")
    e2 = MessageEntry(
        parent_id=e1.id,
        message=ChatMessage(role="user", content="Hello Mia"),
    )
    e3 = MessageEntry(
        parent_id=e2.id,
        message=ChatMessage(role="assistant", content="Hello! How can I help?"),
    )

    store.append_entry(e1)
    store.append_entry(e2)
    store.append_entry(e3)

    loaded = store.load_entries()
    assert len(loaded) == 3
    assert loaded[0].id == e1.id
    assert loaded[1].id == e2.id
    assert loaded[2].id == e3.id
    assert isinstance(loaded[0], SessionInfoEntry)
    assert isinstance(loaded[1], MessageEntry)
    assert isinstance(loaded[2], MessageEntry)


def test_session_tree_traversal_and_branching() -> None:
    e1 = MessageEntry(id="1", parent_id=None, message=ChatMessage(role="user", content="Turn 1"))
    e2 = MessageEntry(id="2", parent_id="1", message=ChatMessage(role="assistant", content="Ans 1"))
    e3 = MessageEntry(id="3", parent_id="2", message=ChatMessage(role="user", content="Turn 2A"))
    e4 = MessageEntry(
        id="4", parent_id="3", message=ChatMessage(role="assistant", content="Ans 2A")
    )
    # Branch at e2
    e5 = MessageEntry(id="5", parent_id="2", message=ChatMessage(role="user", content="Turn 2B"))

    tree = SessionTree([e1, e2, e3, e4, e5])

    # Path to e4 (Branch A)
    path_a = tree.get_path_to_entry("4")
    assert [e.id for e in path_a] == ["1", "2", "3", "4"]

    # Path to e5 (Branch B)
    path_b = tree.get_path_to_entry("5")
    assert [e.id for e in path_b] == ["1", "2", "5"]

    # Leaf resolution
    leaf_entry = LeafEntry(entry_id="4")
    tree_with_leaf = SessionTree([e1, e2, e3, e4, e5, leaf_entry])
    active_path = tree_with_leaf.get_active_path()
    assert [e.id for e in active_path] == ["1", "2", "3", "4"]

    messages = tree_with_leaf.extract_messages_from_path(active_path)
    assert len(messages) == 4
    assert messages[0].content == "Turn 1"
    assert messages[3].content == "Ans 2A"


def test_session_tree_cycle_detection() -> None:
    e1 = MessageEntry(id="1", parent_id="2", message=ChatMessage(role="user", content="Loop 1"))
    e2 = MessageEntry(id="2", parent_id="1", message=ChatMessage(role="user", content="Loop 2"))
    tree = SessionTree([e1, e2])

    with pytest.raises(SessionTreeError, match="Cycle detected"):
        tree.get_path_to_entry("2")


def test_harness_manual_compaction_updates_context_and_session(tmp_path: Path) -> None:
    from mia_agent.harness import AgentHarness
    from mia_ai.providers.mock import MockProvider

    first = MessageEntry(message=ChatMessage(role="user", content="Build a parser"))
    second = MessageEntry(
        parent_id=first.id,
        message=ChatMessage(role="assistant", content="A" * 1600),
    )
    store = JsonlSessionStore(tmp_path / "manual-compact.jsonl")
    store.append_entry(first)
    store.append_entry(second)
    messages = [first.message, second.message]
    harness = AgentHarness(
        provider=MockProvider(),
        model="mock-model",
        messages=messages,
        session_store=store,
        compactor=ContextCompactor(keep_recent_tokens=200),
        last_entry_id=second.id,
    )

    result = harness.compact_context()

    assert result is not None
    assert result.before_tokens == estimate_chat_messages_tokens(messages)
    assert result.after_tokens < result.before_tokens
    assert "Previous conversation summary" in str(harness.messages[0].content)

    entries = store.load_entries()
    compacted = next(entry for entry in entries if isinstance(entry, CompactionEntry))
    assert compacted.parent_id == second.id
    assert isinstance(entries[-1], LeafEntry)
    assert entries[-1].entry_id == compacted.id
    assert [entry.id for entry in entries[:2]] == [first.id, second.id]


def test_context_compactor_threshold_and_compaction() -> None:
    compactor = ContextCompactor(
        context_window_tokens=1000,
        compaction_threshold_ratio=0.8,  # Triggers at >= 800 tokens
        keep_recent_tokens=200,
    )

    # 1. Below threshold
    small_messages = [
        ChatMessage(role="user", content="Short message"),
        ChatMessage(role="assistant", content="Short reply"),
    ]
    tokens = estimate_chat_messages_tokens(small_messages)
    assert tokens < 800
    assert not compactor.should_compact(small_messages)

    # 2. Above threshold
    large_text = (
        "This is a detailed analysis of the system architecture. " * 80
    )  # ~4000 chars -> ~1000 tokens
    large_messages = [
        ChatMessage(role="user", content="Start project"),
        ChatMessage(role="assistant", content=large_text),
        ChatMessage(role="user", content="Second prompt with file reading"),
        ChatMessage(
            role="tool",
            tool_name="read_file",
            tool_call_id="call_1",
            content="Line 1: code\nLine 2: more code\n" * 50,
        ),
        ChatMessage(role="assistant", content="Latest output in progress"),
    ]

    assert compactor.should_compact(large_messages)

    # 3. Compact messages
    compacted_messages, summary_text = compactor.compact_messages(
        messages=large_messages,
        custom_instructions="Focus on architecture decisions",
    )

    assert len(compacted_messages) < len(large_messages)
    assert "## Goal" in summary_text
    assert "## Progress" in summary_text
    assert "Previous conversation summary" in str(compacted_messages[0].content)
    # The latest assistant message should be retained
    assert compacted_messages[-1].content == "Latest output in progress"


@pytest.mark.asyncio
async def test_harness_persists_session_and_resumes(tmp_path: Path) -> None:
    from mia_agent.harness import AgentHarness
    from mia_ai.providers.mock import MockProvider

    session_file = tmp_path / "harness_session.jsonl"
    store = JsonlSessionStore(session_file)

    mock = MockProvider()
    mock.queue_text_response("I am ready to help.")

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        session_store=store,
    )

    events = [e async for e in harness.prompt("Hello Mia")]
    assert len(events) > 0

    # Verify JSONL records created
    entries = store.load_entries()
    assert len(entries) >= 3  # User message, Assistant message, Leaf entry
    assert entries[0].type == "message"
    assert entries[1].type == "message"
    assert entries[-1].type == "leaf"

    # Resume from store
    tree = SessionTree(entries)
    resumed_messages = tree.extract_messages_from_path(tree.get_active_path())
    assert len(resumed_messages) == 2
    assert resumed_messages[0].content == "Hello Mia"
    assert resumed_messages[1].content == "I am ready to help."
