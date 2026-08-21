"""Automated pilot tests for Mia Production Textual TUI."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.events import AssistantChunkEvent, ToolCallEvent, ToolResultEvent
from mia_agent.herd.manager import HerdManager
from mia_ai.providers.mock import MockProvider
from mia_cli.tui.app import MiaApp
from mia_cli.tui.sidebar import AgentListItem
from mia_cli.tui.widgets.prompt_editor import MiaPromptEditor
from mia_cli.tui.widgets.thinking_drawer import ThoughtDrawer
from mia_cli.tui.widgets.tool_card import ToolCallCard


@pytest.mark.asyncio
async def test_tui_app_mount_and_default_herd(tmp_path: Path) -> None:
    """Verify MiaApp mounts, registers default agents (@lead, @coder), and renders sidebar."""
    manager = HerdManager(cwd=tmp_path)
    app = MiaApp(herd_manager=manager, model_name="mock-model")

    async with app.run_test():
        # Check initial agents spawned
        agents = manager.list_agents()
        assert len(agents) >= 2
        assert any(a.id == "lead" for a in agents)
        assert any(a.id == "coder" for a in agents)

        # Check sidebar list items
        items = app.query(AgentListItem)
        assert len(items) >= 2

        # Check header content
        assert app.header_widget.model_name == "mock-model"
        assert "MIA" in app.header_widget._build_content().plain


@pytest.mark.asyncio
async def test_tui_switch_agent_actions(tmp_path: Path) -> None:
    """Verify switching active agent updates active selection and prompt editor target."""
    manager = HerdManager(cwd=tmp_path)
    app = MiaApp(herd_manager=manager, model_name="mock-model")

    async with app.run_test() as pilot:
        assert app.active_agent_id == "lead"

        # Trigger Alt+2 to switch to @coder
        await pilot.press("alt+2")
        assert app.active_agent_id == "coder"
        assert app.prompt_editor.default_target == "coder"

        # Trigger Ctrl+N to spawn a new agent
        await pilot.press("ctrl+n")
        assert len(manager.list_agents()) == 3


@pytest.mark.asyncio
async def test_tui_widget_live_rendering(tmp_path: Path) -> None:
    """Verify live events render cards and collapsible thinking drawers."""
    manager = HerdManager(cwd=tmp_path)
    mock = MockProvider()
    mock.queue_text_response("Plan ready.", thought="Evaluating system specs...")

    _ = manager.spawn_agent(
        agent_id="lead",
        name="Lead",
        profile="architect",
        custom_provider=mock,
    )

    app = MiaApp(herd_manager=manager, model_name="mock-model")

    async with app.run_test() as pilot:
        # Dispatch thoughts and tool calls to @lead
        app.pane_container.dispatch_event(
            "lead",
            AssistantChunkEvent(thought_delta="Evaluating architecture requirements..."),
        )
        app.pane_container.dispatch_event(
            "lead",
            ToolCallEvent(call_id="tc1", tool_name="read_file", arguments={"path": "README.md"}),
        )
        app.pane_container.dispatch_event(
            "lead",
            ToolResultEvent(
                call_id="tc1", tool_name="read_file", output="Sample file", duration_ms=1.5
            ),
        )
        app.pane_container.dispatch_event(
            "lead",
            AssistantChunkEvent(delta_text="Summary of system."),
        )

        await pilot.pause()

        # Check that widgets mounted inside the pane
        thought_drawers = app.query(ThoughtDrawer)
        assert len(thought_drawers) >= 1

        tool_cards = app.query(ToolCallCard)
        assert len(tool_cards) >= 1
        assert tool_cards[0].is_done is True


@pytest.mark.asyncio
async def test_tui_prompt_editor_submission_and_slash_command(tmp_path: Path) -> None:
    """Verify MiaPromptEditor handles prompt submissions and slash commands."""
    manager = HerdManager(cwd=tmp_path)
    app = MiaApp(herd_manager=manager, model_name="mock-model")

    async with app.run_test() as pilot:
        # Test slash command
        app.prompt_editor.post_message(
            MiaPromptEditor.SlashCommandTriggered(command="model", args="mimo-v2.5")
        )
        await pilot.pause()
        assert app.model_name == "mimo-v2.5"

        # Test prompt submission
        app.prompt_editor.post_message(
            MiaPromptEditor.PromptSubmitted(target_agent="coder", prompt_text="Fix typo")
        )
        await pilot.pause()
        assert app.active_agent_id == "coder"
