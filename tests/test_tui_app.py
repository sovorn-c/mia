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
