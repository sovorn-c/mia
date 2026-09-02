"""Contract tests for portable Agent Templates."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mia_agent.agents import AgentManager
from mia_agent.plugins import AgentTemplate, PluginManager


def make_managers(tmp_path: Path) -> tuple[AgentManager, PluginManager]:
    agents = AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
    )
    return agents, PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")


def test_notes_agent_template_is_allowlisted_and_serializable(tmp_path: Path) -> None:
    _, plugins = make_managers(tmp_path)

    templates = plugins.list_templates()
    assert [template.template_id for template in templates] == ["notes-agent"]
    template = templates[0]
    assert template.required_plugins == ["notes"]
    assert template.access_policy == "approval-required"
    assert template.tools == []
    assert template.plugin_config == {"notes": {"notebook_name": "Personal"}}
    dumped = template.model_dump()
    assert "agent_id" not in dumped
    assert "provider" not in dumped
    assert "account" not in dumped
    assert "memory_path" not in dumped
    assert "full_access_confirmed" not in dumped
    assert "metadata" not in dumped

    with pytest.raises(ValidationError):
        AgentTemplate(template_id="unsafe", unknown_private_field="secret")
