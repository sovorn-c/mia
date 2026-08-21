"""Public contract tests for Mia's native orchestration model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.events import TurnStartEvent
from mia_agent.orchestration import (
    AgentRuntimeFactory,
    Mode,
    ModeRuntime,
    OrchestrationEventEnvelope,
    RuntimeIdentity,
    Workflow,
    WorkflowStage,
)
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.entries import CustomEntry, LeafEntry, MessageEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_ai.providers.mock import MockProvider
from mia_ai.types import ChatMessage


def test_models_single_mode_contract_validates_and_rejects_blank_names() -> None:
    workflow = Workflow(
        name="single-workflow",
        stages=[WorkflowStage(name="coordinator", profile="coding", kind="coordinator")],
    )
    mode = Mode(name="single", coordinator_profile="coding", workflow=workflow)

    assert mode.name == "single"
    assert mode.workflow.stages[-1].kind == "coordinator"

    with pytest.raises(ValidationError):
        Mode(name=" ", coordinator_profile="coding", workflow=workflow)


def test_models_workflow_requires_coordinator_as_final_stage() -> None:
    with pytest.raises(ValidationError, match="coordinator"):
        Workflow(
            name="invalid",
            stages=[
                WorkflowStage(name="coordinator", profile="coding", kind="coordinator"),
                WorkflowStage(name="specialist", profile="architect", kind="specialist"),
            ],
        )


def test_models_mode_validates_referenced_profiles() -> None:
    workflow = Workflow(
        name="research-workflow",
        stages=[
            WorkflowStage(name="specialist", profile="architect", kind="specialist"),
            WorkflowStage(name="coordinator", profile="coding", kind="coordinator"),
        ],
    )
    mode = Mode(name="research", coordinator_profile="coding", workflow=workflow)

    mode.validate_profiles({"architect", "coding"})
    with pytest.raises(ValueError, match="architect"):
        mode.validate_profiles({"coding"})


def test_orchestration_envelope_retains_inner_agent_event() -> None:
    inner = TurnStartEvent(turn_index=0, user_prompt="map the repository")
    envelope = OrchestrationEventEnvelope(
        mode="single",
        run_id="run-1",
        task_id="task-1",
        agent_id="agent-1",
        profile="coding",
        event=inner,
    )

    assert envelope.event is inner
    assert envelope.event.type == "turn_start"
    assert envelope.mode == "single"


def test_factory_builds_profile_scoped_runtime_and_persists_lineage(tmp_path) -> None:
    profiles = ProfileManager(sessions_base_dir=tmp_path / "sessions")
    config = ConfigManager(
        config_path=tmp_path / "config.json",
        credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
    )
    identity = RuntimeIdentity(
        mode="research",
        run_id="run-1",
        task_id="specialist",
        agent_id="agent-1",
        profile="architect",
        session_id="child-1",
        parent_session_id="root-1",
    )
    runtime = AgentRuntimeFactory(
        profile_manager=profiles,
        config_manager=config,
    ).build(
        identity=identity,
        provider=MockProvider(),
        cwd=tmp_path,
    )

    assert runtime.identity == identity
    assert runtime.harness.session_id == "child-1"
    assert [tool.name for tool in runtime.harness.tools] == ["read_file"]
    entries = runtime.session_store.load_entries()
    metadata = next(entry for entry in entries if isinstance(entry, CustomEntry))
    assert metadata.data["parent_session_id"] == "root-1"
    assert metadata.data["profile"] == "architect"


def test_factory_resumes_messages_from_active_session(tmp_path) -> None:
    profiles = ProfileManager(sessions_base_dir=tmp_path / "sessions")
    session_dir = profiles.get_session_dir("coding")
    store = JsonlSessionStore(session_dir / "root-1.jsonl")
    user_entry = MessageEntry(message=ChatMessage(role="user", content="existing prompt"))
    store.append_entry(user_entry)
    store.append_entry(
        MessageEntry(
            parent_id=user_entry.id,
            message=ChatMessage(role="assistant", content="existing answer"),
        )
    )
    store.append_entry(LeafEntry(entry_id=user_entry.id))

    identity = RuntimeIdentity(
        mode="single",
        run_id="run-1",
        task_id="task-1",
        agent_id="agent-1",
        profile="coding",
        session_id="root-1",
    )
    runtime = AgentRuntimeFactory(profile_manager=profiles).build(
        identity=identity,
        provider=MockProvider(),
        cwd=tmp_path,
    )

    assert [message.content for message in runtime.harness.messages] == ["existing prompt"]


@pytest.mark.asyncio
async def test_single_mode_runtime_preserves_one_agent_event_stream(tmp_path) -> None:
    provider = MockProvider()
    provider.queue_text_response("one coordinator answer")
    profiles = ProfileManager(sessions_base_dir=tmp_path / "sessions")
    factory = AgentRuntimeFactory(
        profile_manager=profiles,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )
    runtime = ModeRuntime(factory=factory, profile_manager=profiles)

    events = [
        event
        async for event in runtime.prompt(
            "one coordinator prompt",
            profile_name="coding",
            provider=provider,
            cwd=tmp_path,
        )
    ]

    assert len(provider.recorded_calls) == 1
    assert [event.event.type for event in events] == [
        "turn_start",
        "step_start",
        "assistant_chunk",
        "step_end",
        "turn_complete",
    ]
    assert all(event.mode == "single" for event in events)
    assert {event.profile for event in events} == {"coding"}
