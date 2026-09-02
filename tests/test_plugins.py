"""Contract tests for bundled Plugin installation."""

from __future__ import annotations

from pathlib import Path

from mia_agent.agents import AgentManager
from mia_agent.plugins import PluginManager


def make_agent_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
    )


def test_bundled_notes_plugin_installs_without_network(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    available = plugins.list_available()
    assert available[0].plugin_id == "notes"
    assert available[0].version == "1.0.0"
    assert available[0].tools == ["note_create", "note_list", "note_read"]
    assert plugins.list_installed() == []

    installed = plugins.install("notes")

    assert installed.plugin_id == "notes"
    assert [item.plugin_id for item in plugins.list_installed()] == ["notes"]
    assert plugins.install("notes") == installed
    assert (tmp_path / "plugins" / "installed.json").exists()
