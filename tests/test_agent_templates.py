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
    with pytest.raises(ValidationError, match="credential-like"):
        AgentTemplate(
            template_id="unsafe-config",
            version="1.0.0",
            display_name="Unsafe",
            description="Unsafe",
            instructions="Unsafe",
            plugin_config={"notes": {"api_key": "secret"}},
        )
    with pytest.raises(ValidationError, match="secret-like"):
        AgentTemplate(
            template_id="unsafe-value",
            version="1.0.0",
            display_name="Unsafe",
            description="Unsafe",
            instructions="Unsafe",
            required_plugins=["notes"],
            plugin_config={"notes": {"notebook_name": "Bearer secret"}},
        )
    with pytest.raises(ValidationError, match="required"):
        AgentTemplate(
            template_id="unrequired-config",
            version="1.0.0",
            display_name="Unsafe",
            description="Unsafe",
            instructions="Unsafe",
            plugin_config={"notes": {"notebook_name": "Personal"}},
        )
    with pytest.raises(ValidationError, match="duplicate"):
        AgentTemplate(
            template_id="duplicate-tools",
            version="1.0.0",
            display_name="Unsafe",
            description="Unsafe",
            instructions="Unsafe",
            tools=["read_file", "read_file"],
        )


def test_notes_template_instantiates_an_independent_agent(tmp_path: Path) -> None:
    agents, plugins = make_managers(tmp_path)
    plugins.install("notes")

    created = plugins.instantiate("notes-agent", "my-notes")

    assert created.agent_id == "my-notes"
    assert created.access_policy == "approval-required"
    assert created.plugins == ["notes"]
    assert created.plugin_config == {"notes": {"notebook_name": "Personal"}}
    assert created.full_access_confirmed is False
    assert agents.get_agent("my-notes") == created
    assert not (tmp_path / "agents" / ".default-agent").exists()
