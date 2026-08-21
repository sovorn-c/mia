"""Tests for Slice 9: Multi-Agent Herd Orchestration Engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.herd.manager import HerdManager
from mia_agent.herd.models import AgentState, HerdEvent
from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall


@pytest.mark.asyncio
async def test_herd_manager_spawn_and_state_tracking(tmp_path: Path) -> None:
    events: list[HerdEvent] = []
    manager = HerdManager(cwd=tmp_path)
    manager.subscribe(lambda e: events.append(e))

    mock = MockProvider()
    mock.queue_text_response("Lead architect ready.")

    lead = manager.spawn_agent(
        agent_id="lead",
        name="Lead Architect",
        profile="architect",
        custom_provider=mock,
    )

    assert lead.id == "lead"
    assert lead.state == AgentState.IDLE
    assert len(manager.list_agents()) == 1

    # Run agent turn
    agent_events = [e async for e in manager.run_agent("lead", "Plan architecture")]
    assert len(agent_events) > 0
    assert lead.state == AgentState.DONE

    # Verify herd events emitted
    assert any(e.type == "agent_event_envelope" and e.agent_id == "lead" for e in events)


@pytest.mark.asyncio
async def test_herd_manager_inter_agent_delegation(tmp_path: Path) -> None:
    manager = HerdManager(cwd=tmp_path)

    # Setup mock for Coder
    mock_coder = MockProvider()
    mock_coder.queue_text_response("Function add(a, b) implemented.")

    _ = manager.spawn_agent(
        agent_id="coder",
        name="Senior Coder",
        profile="coding",
        custom_provider=mock_coder,
    )

    # Setup mock for Lead which delegates to Coder via invoke_subagent tool
    mock_lead = MockProvider()
    mock_lead.queue_tool_call(
        ToolCall(
            id="call_sub_1",
            name="invoke_subagent",
            arguments={"agent_id": "coder", "prompt": "Implement add(a, b)"},
        ),
        thought="Delegating coding task to @coder.",
    )
    mock_lead.queue_text_response("Task completed by coder and verified.")

    _ = manager.spawn_agent(
        agent_id="lead",
        name="Lead Architect",
        profile="architect",
        custom_provider=mock_lead,
    )

    # Run Lead turn
    lead_events = [e async for e in manager.run_agent("lead", "Build feature")]
    assert len(lead_events) > 0

    coder = manager.get_agent("coder")
    lead = manager.get_agent("lead")

    assert coder is not None and lead is not None
    assert coder.state == AgentState.DONE
    assert lead.state == AgentState.DONE


@pytest.mark.asyncio
async def test_herd_direct_messaging(tmp_path: Path) -> None:
    events: list[HerdEvent] = []
    manager = HerdManager(cwd=tmp_path)
    manager.subscribe(lambda e: events.append(e))

    _ = manager.spawn_agent(agent_id="lead", name="Lead", profile="architect")
    _ = manager.spawn_agent(agent_id="tester", name="Tester", profile="coding")

    await manager.send_direct_message(
        sender_id="lead",
        recipient_id="tester",
        content="Please run integration test suite.",
    )

    tester = manager.get_agent("tester")
    assert tester is not None
    assert tester.unread_messages == 1
    assert any(e.type == "inter_agent_message" and e.recipient_id == "tester" for e in events)
