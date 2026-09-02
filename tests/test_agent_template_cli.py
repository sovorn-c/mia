"""Contract tests for Agent Template inspection and creation commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.plugins import PluginManager
from mia_cli.main import app

runner = CliRunner()


def make_managers(tmp_path: Path) -> tuple[AgentManager, PluginManager]:
    agents = AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
    )
    return agents, PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")


def test_cli_lists_and_creates_notes_agent_template(tmp_path: Path) -> None:
    agents, plugins = make_managers(tmp_path)
    plugins.install("notes")
    with patch("mia_cli.main.AgentManager", return_value=agents), patch(
        "mia_cli.main.PluginManager", return_value=plugins
    ):
        listed = runner.invoke(app, ["template", "list"])
        created = runner.invoke(app, ["template", "create", "notes-agent", "my-notes"])

    assert listed.exit_code == 0
    assert "notes-agent" in listed.stdout
    assert created.exit_code == 0
    assert "my-notes" in created.stdout
    assert agents.get_agent("my-notes").plugins == ["notes"]
