"""Agent-native Textual frontend contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.agents import AgentManager
from mia_cli.tui.app import MiaApp
from mia_cli.tui.sidebar import AgentListItem


@pytest.mark.asyncio
async def test_tui_mount_lists_builtin_and_persisted_agents(tmp_path: Path) -> None:
    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent(
        "reviewer",
        display_name="Reviewer",
        instructions="Review local changes.",
    )
    app = MiaApp(agent_manager=manager, model_name="mock-model")

    async with app.run_test():
        assert app.active_agent_id == "mia"
        assert {item.agent.agent_id for item in app.query(AgentListItem)} >= {
            "mia",
            "reviewer",
        }
        assert not {item.agent.agent_id for item in app.query(AgentListItem)} & {
            "lead",
            "coder",
        }


@pytest.mark.asyncio
async def test_tui_prompt_routes_through_agent_runner(tmp_path: Path) -> None:
    from mia_ai.providers.mock import MockProvider
    from mia_cli.tui.widgets.message_card import AssistantMessageCard, UserMessageCard

    manager = AgentManager(agents_dir=tmp_path / "agents")
    provider = MockProvider()
    provider.queue_text_response("The Agent response.")
    app = MiaApp(
        agent_manager=manager,
        model_name="mock-model",
        cwd=tmp_path,
        provider=provider,
    )

    async with app.run_test() as pilot:
        textarea = app.query_one("#prompt-textarea")
        textarea.text = "Hello Mia"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert provider.recorded_calls
        assert provider.recorded_calls[0]["system"]
        assert app.query(UserMessageCard)
        assert app.query(AssistantMessageCard)


@pytest.mark.asyncio
async def test_tui_passes_approval_callback_to_agent_runner(tmp_path: Path) -> None:
    from mia_ai.providers.mock import MockProvider

    approvals = []
    provider = MockProvider()
    provider.queue_tool_call_response("write_file", {"path": "approved.txt", "content": "approved"})
    provider.queue_text_response("The file is ready.")
    app = MiaApp(
        agent_manager=AgentManager(agents_dir=tmp_path / "agents"),
        model_name="mock-model",
        cwd=tmp_path,
        provider=provider,
        approval_callback=lambda request: approvals.append(request) or True,
    )

    async with app.run_test() as pilot:
        textarea = app.query_one("#prompt-textarea")
        textarea.text = "Write the file"
        await pilot.press("enter")
        for _ in range(3):
            await pilot.pause()

    assert approvals
    assert approvals[0].tool_name == "write_file"
    assert (tmp_path / "approved.txt").read_text() == "approved"


@pytest.mark.asyncio
async def test_tui_switches_and_persists_a_new_agent(tmp_path: Path) -> None:
    manager = AgentManager(agents_dir=tmp_path / "agents")
    app = MiaApp(agent_manager=manager, model_name="mock-model", cwd=tmp_path)

    async with app.run_test():
        agents = manager.list_agents()
        target = agents[1]
        app.action_switch_agent(2)
        assert app.active_agent_id == target.agent_id
        assert app.prompt_editor.default_target == target.agent_id

        app.action_spawn_new_agent()
        created = manager.get_agent(app.active_agent_id)
        assert created.display_name.startswith("Worker ")
        assert created.tools == ["read_file", "write_file", "edit_file", "bash"]


@pytest.mark.asyncio
async def test_tui_renders_canonical_stream_events(tmp_path: Path) -> None:
    from mia_agent.events import AssistantChunkEvent, ToolCallEvent, ToolResultEvent
    from mia_cli.tui.widgets.thinking_drawer import ThoughtDrawer
    from mia_cli.tui.widgets.tool_card import ToolCallCard

    app = MiaApp(
        agent_manager=AgentManager(agents_dir=tmp_path / "agents"),
        model_name="mock-model",
        cwd=tmp_path,
    )

    async with app.run_test():
        app.pane_container.dispatch_event(
            "mia", AssistantChunkEvent(thought_delta="Checking the request.")
        )
        app.pane_container.dispatch_event(
            "mia", ToolCallEvent(call_id="call-1", tool_name="read_file", arguments={})
        )
        app.pane_container.dispatch_event(
            "mia",
            ToolResultEvent(call_id="call-1", tool_name="read_file", output="done"),
        )
        app.pane_container.dispatch_event("mia", AssistantChunkEvent(delta_text="Finished."))

        assert app.query(ThoughtDrawer)
        assert app.query(ToolCallCard)
        assert app.query(ToolCallCard)[0].is_done is True


@pytest.mark.asyncio
async def test_tui_uses_run_request_and_closeable_stream(tmp_path: Path) -> None:
    from mia_agent.events import TurnCompleteEvent
    from mia_agent.runtime_events import AgentEventEnvelope
    from mia_agent.runtime_models import RunRequest

    received_requests: list[RunRequest] = []
    closed = False

    async def mock_run(req: RunRequest, **kwargs: object):
        nonlocal closed
        received_requests.append(req)
        try:
            yield AgentEventEnvelope(
                run_id="r1",
                task_id="root",
                agent_id="mia",
                session_id="s1",
                event=TurnCompleteEvent(total_steps=1, total_cost_usd=0.0, stop_reason="stop"),
            )
        finally:
            closed = True

    app = MiaApp(
        agent_manager=AgentManager(agents_dir=tmp_path / "agents"),
        model_name="mock-model",
        cwd=tmp_path,
    )
    app.agent_runner.run = mock_run  # type: ignore[method-assign]
    async with app.run_test():
        worker = app.run_agent_turn_worker("mia", "Test TUI prompt")
        await worker.wait()
    assert len(received_requests) == 1
    assert received_requests[0].prompt_text == "Test TUI prompt"
    assert received_requests[0].agent_id == "mia"
    assert closed is True
