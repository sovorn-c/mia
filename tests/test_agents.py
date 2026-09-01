"""Contract tests for canonical Agent identity and additive persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mia_agent.agents import Agent, AgentManager
from mia_agent.profiles.model import AgentProfile


def make_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
    )


def test_agent_model_normalizes_identity_and_keeps_serialization_secret_free() -> None:
    agent = Agent(
        agent_id=" Researcher ",
        display_name="Researcher",
        instructions="Find and summarize evidence.",
        provider="openai",
        account="personal",
        tools=["read_file"],
    )

    assert agent.agent_id == "researcher"
    assert agent.name == "Researcher"
    assert agent.system_prompt == "Find and summarize evidence."
    dumped = json.dumps(agent.model_dump())
    assert "openai" in dumped
    assert "personal" in dumped
    assert "api_key" not in dumped
    assert "access_token" not in dumped.lower()

    with pytest.raises(ValidationError):
        Agent(agent_id="../outside", display_name="Outside")
    with pytest.raises(ValidationError):
        Agent(agent_id="", display_name="Blank")
    with pytest.raises(ValidationError):
        Agent(agent_id="safe", display_name="Unsafe", metadata={"api_key": "secret"})


def test_default_mia_is_useful_without_saved_configuration(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    mia = manager.get_agent()

    assert mia.agent_id == "mia"
    assert mia.display_name == "Mia"
    assert mia.access_policy == "approval-required"
    assert mia.tools == ["read_file", "write_file", "edit_file", "bash"]
    assert manager.default_agent().agent_id == "mia"


def test_named_agent_lifecycle_survives_a_new_manager(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    created = manager.create_agent(
        " Researcher ",
        display_name="Researcher",
        instructions="Research carefully.",
        tools=["read_file"],
    )

    assert created.agent_id == "researcher"
    assert manager.get_agent("researcher") == created
    assert any(agent.agent_id == "researcher" for agent in manager.list_agents())
    assert manager.inspect_agent("researcher")["source"] == "native"

    manager.set_default("researcher")
    reloaded = make_manager(tmp_path)
    assert reloaded.default_agent().agent_id == "researcher"
    assert reloaded.get_session_dir("researcher") == tmp_path / "agents" / "researcher" / "sessions"

    assert reloaded.delete_agent("researcher") is True
    assert reloaded.default_agent().agent_id == "mia"
    with pytest.raises(ValueError, match="not found"):
        reloaded.get_agent("researcher")


def test_builtin_agents_cannot_be_overwritten_or_deleted(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    with pytest.raises(ValueError, match="built-in"):
        manager.save_agent(Agent(agent_id="mia", display_name="Not Mia"))
    with pytest.raises(ValueError, match="built-in"):
        manager.delete_agent("mia")

    assert manager.get_agent("mia").display_name == "Mia"


def test_agent_ids_are_rejected_before_filesystem_access(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    outside = tmp_path / "outside.json"

    for unsafe in ("../outside", "a/b", "a\\b", "/tmp/agent", "..", " "):
        with pytest.raises(ValueError):
            manager.create_agent(unsafe, display_name="Unsafe")
        with pytest.raises(ValueError):
            manager.get_agent(unsafe)

    assert not outside.exists()
    assert list(tmp_path.rglob("outside.json")) == []


def test_legacy_profile_projects_without_rewriting_and_native_wins(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile_file = profiles_dir / "reviewer.json"
    profile_file.write_text(
        json.dumps(
            AgentProfile(
                name="reviewer",
                description="Legacy reviewer",
                system_prompt="Review code.",
                tools=["read_file"],
                permission="read_only",
            ).model_dump()
        ),
        encoding="utf-8",
    )
    before = profile_file.read_bytes()
    manager = make_manager(tmp_path)

    legacy = manager.get_agent("reviewer")
    assert legacy.agent_id == "reviewer"
    assert legacy.instructions == "Review code."
    assert legacy.access_policy == "read-only"
    assert manager.inspect_agent("reviewer")["source"] == "legacy"
    assert profile_file.read_bytes() == before

    manager.save_agent(legacy)
    assert profile_file.read_bytes() == before
    assert (tmp_path / "agents" / "reviewer" / "agent.json").exists()
    assert manager.delete_agent("reviewer") is True

    manager.create_agent("reviewer", display_name="Native reviewer", tools=[])
    resolved = manager.get_agent("reviewer")
    inspection = manager.inspect_agent("reviewer")
    assert resolved.display_name == "Native reviewer"
    assert inspection["source"] == "native"
    assert inspection["collision"] is True


def test_native_agent_writes_are_atomic_and_do_not_copy_secret_values(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    agent = manager.create_agent(
        "safe-agent",
        display_name="Safe Agent",
        provider="openrouter",
        account="work",
        metadata={"purpose": "review"},
    )

    path = manager.agent_path(agent.agent_id)
    text = path.read_text(encoding="utf-8")
    assert '"provider": "openrouter"' in text
    assert '"account": "work"' in text
    assert "sk-" not in text
    assert "access_token" not in text
    assert not list(path.parent.glob("*.tmp"))
