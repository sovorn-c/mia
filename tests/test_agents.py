"""Contract tests for canonical Agent identity and additive persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import RuntimeIdentity
from mia_ai.providers.mock import MockProvider


def make_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(agents_dir=tmp_path / "agents")


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
    assert agent.display_name == "Researcher"
    assert agent.instructions == "Find and summarize evidence."
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
    with pytest.raises(ValidationError):
        Agent(
            agent_id="safe",
            display_name="Unsafe",
            metadata={"nested": ({"access_token": "secret"},)},
        )


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


def test_agent_session_paths_reject_traversal_and_symlinks(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(outside_root, target_is_directory=True)
    with pytest.raises(ValueError, match="storage root"):
        AgentManager(agents_dir=linked_root)
    with pytest.raises(ValueError, match="Unsafe Agent ID"):
        manager.get_session_path("mia", "../escaped")
    assert not (tmp_path / "agents" / "escaped.jsonl").exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    (agents_dir / "evil").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        manager.get_session_dir("evil")
    with pytest.raises(ValueError, match="symlink"):
        manager.create_agent("evil", display_name="Evil")

    manager.create_agent("safe", display_name="Safe")
    session_dir = manager.get_session_dir("safe")
    outside_session = outside / "outside.jsonl"
    outside_session.write_text("", encoding="utf-8")
    (session_dir / "session.jsonl").symlink_to(outside_session)
    with pytest.raises(ValueError, match="symlink"):
        manager.get_session_path("safe", "session")


def test_factory_builds_agent_owned_runtime_and_session(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "researcher",
        display_name="Researcher",
        instructions="Research with care.",
        tools=["read_file"],
    )
    identity = RuntimeIdentity(
        agent_id="researcher",
        run_id="run-researcher",
        task_id="root",
        session_id="session-researcher",
    )

    runtime = AgentRuntimeFactory(
        agent_manager=manager,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    ).build(identity=identity, provider=MockProvider())

    assert runtime.agent.agent_id == "researcher"
    assert runtime.harness.system_prompt == "Research with care."
    assert (
        runtime.session_store.path
        == (tmp_path / "agents" / "researcher" / "sessions" / "session-researcher.jsonl").resolve()
    )
    metadata = next(
        entry for entry in runtime.session_store.load_entries() if entry.type == "custom"
    )
    assert metadata.namespace == "agent"
    assert metadata.data["agent_id"] == "researcher"
    assert metadata.data["run_id"] == "run-researcher"


def test_full_access_requires_explicit_creation_confirmation(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    with pytest.raises(ValueError, match="confirmation"):
        manager.create_agent("autonomous", access_policy="full-access")

    autonomous = manager.create_agent(
        "autonomous",
        access_policy="full-access",
        confirm_full_access=True,
    )
    assert autonomous.access_policy == "full-access"


def test_canonical_agent_rejects_historical_fields_and_manager_options(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Agent.model_validate({"agent_id": "reviewer", "name": "Reviewer"})
    with pytest.raises(ValidationError):
        Agent.model_validate({"agent_id": "reviewer", "system_prompt": "Review"})
    with pytest.raises(ValidationError):
        Agent.model_validate({"agent_id": "reviewer", "access": "read_only"})
    with pytest.raises(ValidationError):
        Agent.model_validate({"agent_id": "reviewer", "permission": "standard"})

    with pytest.raises(TypeError):
        AgentManager(legacy_options=tmp_path)  # type: ignore[call-arg]


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
