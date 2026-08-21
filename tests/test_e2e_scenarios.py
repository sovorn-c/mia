"""End-to-End headless simulation suite testing multi-turn developer lifecycles,
guardrails, low-threshold (30%) context compaction, and session branching.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.entries import CompactionEntry, LeafEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool


@pytest.mark.asyncio
async def test_e2e_autonomous_bug_fix_and_verify_cycle(tmp_path: Path) -> None:
    """Full developer workflow: read file -> test fails -> edit file -> test passes -> complete."""
    # 1. Setup sample project with buggy calculator and test
    calc_file = tmp_path / "calculator.py"
    calc_file.write_text(
        "def add(a: int, b: int) -> int:\n    return a - b  # BUG: should be +\n",
        encoding="utf-8",
    )

    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    # 2. Setup tools & middleware
    tools = [
        ReadFileTool(cwd=tmp_path),
        WriteFileTool(cwd=tmp_path),
        EditFileTool(cwd=tmp_path),
        BashTool(cwd=tmp_path),
    ]
    pipeline = ToolPipeline([SecurityGuardMiddleware(), AuditLogMiddleware()])
    session_file = tmp_path / "session_bugfix.jsonl"
    session_store = JsonlSessionStore(session_file)

    # 3. Script mock provider to emulate intelligent agent turns
    mock = MockProvider()

    # Step 1: Model inspects file
    mock.queue_tool_call(
        ToolCall(id="c1", name="read_file", arguments={"path": "calculator.py"}),
        thought="Let me read the calculator implementation.",
    )
    # Step 2: Model runs tests to confirm failure
    mock.queue_tool_call(
        ToolCall(id="c2", name="bash", arguments={"command": "python3 -m pytest test_calc.py"}),
        thought="Let me run pytest to observe the failure.",
    )
    # Step 3: Model fixes the bug with edit_file
    mock.queue_tool_call(
        ToolCall(
            id="c3",
            name="edit_file",
            arguments={
                "path": "calculator.py",
                "edits": [
                    {"oldText": "return a - b  # BUG: should be +", "newText": "return a + b"}
                ],
            },
        ),
        thought="Found the subtraction bug. Patching it with edit_file.",
    )
    # Step 4: Model re-runs tests to verify fix
    mock.queue_tool_call(
        ToolCall(id="c4", name="bash", arguments={"command": "python3 -m pytest test_calc.py"}),
        thought="Re-running tests to verify.",
    )
    # Step 5: Final completion response
    mock.queue_text_response("Bug in calculator.py fixed and all unit tests verified passing!")

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        tools=tools,
        pipeline=pipeline,
        session_store=session_store,
    )

    events = [
        e async for e in harness.prompt("Fix the bug in calculator.py and ensure tests pass.")
    ]

    # 4. Verify outcomes
    assert any(e.type == "turn_complete" and e.stop_reason == "stop" for e in events)
    assert "return a + b" in calc_file.read_text(encoding="utf-8")

    # Verify session journal
    entries = session_store.load_entries()
    assert len(entries) >= 10  # Multiple user/asst/tool messages and leaf entry
    assert isinstance(entries[-1], LeafEntry)


@pytest.mark.asyncio
async def test_e2e_security_guardrail_blocking_and_recovery(tmp_path: Path) -> None:
    """Agent attempts a hostile command, gets intercepted by SecurityGuardMiddleware, and recovers."""
    tools = [BashTool(cwd=tmp_path)]
    pipeline = ToolPipeline([SecurityGuardMiddleware()])

    mock = MockProvider()
    # Step 1: Dangerous command
    mock.queue_tool_call(
        ToolCall(id="bad_1", name="bash", arguments={"command": "rm -rf /"}),
        thought="Attempting cleanup.",
    )
    # Step 2: Safe recovery command
    mock.queue_tool_call(
        ToolCall(id="safe_2", name="bash", arguments={"command": "echo 'Safe cleanup completed'"}),
        thought="Destructive command was blocked. Running safe alternative.",
    )
    # Step 3: Finish
    mock.queue_text_response("Cleaned up safely without destructive commands.")

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        tools=tools,
        pipeline=pipeline,
    )

    events = [e async for e in harness.prompt("Clean the workspace.")]

    tool_results = [e for e in events if e.type == "tool_result"]
    assert len(tool_results) == 2
    # First result was blocked
    assert tool_results[0].is_error is True
    assert "Security Violation" in str(tool_results[0].output)
    # Second result succeeded
    assert tool_results[1].is_error is False
    assert "Safe cleanup completed" in str(tool_results[1].output)


@pytest.mark.asyncio
async def test_e2e_low_threshold_30_percent_context_compaction(tmp_path: Path) -> None:
    """Agent with 30% compaction threshold triggers structured compaction during heavy turns."""
    session_file = tmp_path / "compact_session.jsonl"
    session_store = JsonlSessionStore(session_file)

    # 30% threshold on a 1000 token context window = compaction triggers at >= 300 tokens
    compactor = ContextCompactor(
        context_window_tokens=1000,
        compaction_threshold_ratio=0.3,
        keep_recent_tokens=100,
    )

    mock = MockProvider()
    # Turn 1: Generates large assistant text (~400 tokens -> exceeds 300)
    large_response_1 = "Detailed architecture breakdown of subsystem A. " * 40
    mock.queue_text_response(large_response_1)

    # Turn 2: Followup prompt
    mock.queue_text_response("Turn 2 response with concise summary.")

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        session_store=session_store,
        compactor=compactor,
    )

    # Run Turn 1
    events_t1 = [e async for e in harness.prompt("Turn 1 prompt")]
    assert len(events_t1) > 0

    # Run Turn 2 -> Context exceeds 30%, compaction triggers automatically before turn 2 prompt
    events_t2 = [e async for e in harness.prompt("Turn 2 prompt")]
    assert len(events_t2) > 0

    # Verify compaction was executed and stored
    entries = session_store.load_entries()
    compaction_entries = [e for e in entries if isinstance(e, CompactionEntry)]
    assert len(compaction_entries) >= 1
    assert "## Goal" in compaction_entries[0].summary
    assert "## Progress" in compaction_entries[0].summary

    # Verify active messages in harness are compacted
    active_msgs = harness.messages
    assert any("Previous conversation summary" in str(m.content) for m in active_msgs)


@pytest.mark.asyncio
async def test_e2e_session_tree_branching_and_divergence(tmp_path: Path) -> None:
    """Verify durable JSONL tree creates branching paths without corrupting active history."""
    session_file = tmp_path / "branching_tree.jsonl"
    store = JsonlSessionStore(session_file)

    mock = MockProvider()
    mock.queue_text_response("Root answer.")
    mock.queue_text_response("Branch A response.")

    harness_a = AgentHarness(provider=mock, model="mock-model", session_store=store)

    # Turn 1 (Common Root)
    _ = [e async for e in harness_a.prompt("Root question")]
    entries_t1 = store.load_entries()
    last_msg_t1 = next(e for e in reversed(entries_t1) if e.type == "message")
    root_leaf_id = last_msg_t1.id  # Last message of turn 1

    # Turn 2 (Branch A)
    _ = [e async for e in harness_a.prompt("Branch A question")]

    # Branch B (Starting a new harness branching from root_leaf_id)
    mock.queue_text_response("Branch B response.")
    tree = SessionTree(store.load_entries())
    root_messages = tree.extract_messages_from_path(tree.get_path_to_entry(root_leaf_id))

    harness_b = AgentHarness(
        provider=mock,
        model="mock-model",
        messages=root_messages,
        session_store=store,
    )
    # Set parent entry ID to root leaf
    harness_b._last_entry_id = root_leaf_id
    _ = [e async for e in harness_b.prompt("Branch B question")]

    # Load complete tree and verify both branches exist
    all_entries = store.load_entries()
    full_tree = SessionTree(all_entries)

    assert len(all_entries) >= 7
    # Path along Branch B has root + Branch B prompt + Branch B answer
    active_b = full_tree.get_active_path()
    msgs_b = full_tree.extract_messages_from_path(active_b)
    assert msgs_b[0].content == "Root question"
    assert msgs_b[-1].content == "Branch B response."


def test_e2e_profile_permissions_read_only_and_minimal() -> None:
    """Verify architect profile blocks modification tools and minimal profile disables tools."""
    manager = ProfileManager()
    architect = manager.get_profile("architect")
    minimal = manager.get_profile("minimal")

    class ReadTool:
        name = "read_file"

    class WriteTool:
        name = "write_file"

    class BashTool:
        name = "bash"

    all_tools = [ReadTool(), WriteTool(), BashTool()]

    # Architect only allows read_file
    architect_tools = manager.filter_tools(architect, all_tools)
    assert len(architect_tools) == 1
    assert architect_tools[0].name == "read_file"

    # Minimal allows zero tools
    minimal_tools = manager.filter_tools(minimal, all_tools)
    assert len(minimal_tools) == 0
