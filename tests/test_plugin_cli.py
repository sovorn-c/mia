"""Contract tests for explicit Plugin lifecycle commands."""

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
    agents.create_agent("alpha", tools=[])
    return agents, PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")


def test_cli_installs_and_enables_bundled_plugin(tmp_path: Path) -> None:
    agents, plugins = make_managers(tmp_path)
    with (
        patch("mia_cli.main.AgentManager", return_value=agents),
        patch("mia_cli.main.PluginManager", return_value=plugins),
    ):
        installed = runner.invoke(app, ["plugin", "install", "notes"])
        enabled = runner.invoke(app, ["plugin", "enable", "notes", "--agent", "alpha"])

    assert installed.exit_code == 0
    assert "notes" in installed.stdout
    assert enabled.exit_code == 0
    assert "alpha" in enabled.stdout
    assert agents.get_agent("alpha").plugins == ["notes"]


def test_cli_lists_shows_configures_and_disables_plugin(tmp_path: Path) -> None:
    agents, plugins = make_managers(tmp_path)
    plugins.install("notes")
    plugins.enable("alpha", "notes")
    with (
        patch("mia_cli.main.AgentManager", return_value=agents),
        patch("mia_cli.main.PluginManager", return_value=plugins),
    ):
        listed = runner.invoke(app, ["plugin", "list"])
        shown = runner.invoke(app, ["plugin", "show", "notes"])
        configured = runner.invoke(
            app,
            ["plugin", "configure", "notes", "--agent", "alpha", "--notebook-name", "Work"],
        )
        disabled = runner.invoke(app, ["plugin", "disable", "notes", "--agent", "alpha"])

    assert listed.exit_code == 0
    assert "installed" in listed.stdout
    assert shown.exit_code == 0
    assert "note_create" in shown.stdout
    assert configured.exit_code == 0
    assert "alpha" in configured.stdout
    assert disabled.exit_code == 0
    assert "alpha" in disabled.stdout
    assert agents.get_agent("alpha").plugins == []
    assert agents.get_agent("alpha").plugin_config == {"notes": {"notebook_name": "Work"}}


def test_agent_inspection_reports_enabled_plugins_without_config_values(tmp_path: Path) -> None:
    agents, plugins = make_managers(tmp_path)
    plugins.install("notes")
    plugins.enable("alpha", "notes")
    plugins.configure("alpha", "notes", {"notebook_name": "Private"})
    with (
        patch("mia_cli.main.AgentManager", return_value=agents),
        patch("mia_cli.main.PluginManager", return_value=plugins),
    ):
        shown = runner.invoke(app, ["agent", "show", "alpha"])

    assert shown.exit_code == 0
    assert "Plugins: notes" in shown.stdout
    assert "Private" not in shown.stdout
