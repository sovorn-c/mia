from __future__ import annotations

import pytest
from pydantic import ValidationError

from mia_agent.runtime_models import RuntimeIdentity


def test_runtime_identity_contains_only_canonical_attribution() -> None:
    identity = RuntimeIdentity(
        run_id="run-1",
        task_id="root",
        agent_id="mia",
        session_id="session-1",
        parent_session_id="parent-session-1",
    )

    assert identity.model_dump() == {
        "run_id": "run-1",
        "task_id": "root",
        "agent_id": "mia",
        "session_id": "session-1",
        "parent_session_id": "parent-session-1",
    }

    with pytest.raises(ValidationError):
        RuntimeIdentity(
            run_id="run-1",
            task_id="root",
            agent_id="mia",
            session_id="session-1",
            mode="single",
        )


def test_agent_event_envelope_retains_the_inner_agent_event() -> None:
    from mia_agent.events import TurnStartEvent
    from mia_agent.runtime_events import AgentEventEnvelope

    inner = TurnStartEvent(turn_index=0, user_prompt="map the repository")
    envelope = AgentEventEnvelope(
        run_id="run-1",
        task_id="root",
        agent_id="mia",
        session_id="session-1",
        event=inner,
    )

    assert envelope.event is inner
    assert envelope.event.type == "turn_start"
    assert not hasattr(envelope, "mode")
    assert not hasattr(envelope, "profile")


def test_runtime_factory_does_not_accept_profile_manager() -> None:
    from mia_agent.runtime_factory import AgentRuntimeFactory

    from mia_agent.profiles.manager import ProfileManager

    with pytest.raises(TypeError):
        AgentRuntimeFactory(profile_manager=ProfileManager())  # type: ignore[call-arg]


def test_runtime_factory_builds_agent_owned_runtime(tmp_path) -> None:
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_ai.providers.mock import MockProvider

    manager = AgentManager(agents_dir=tmp_path / "agents")
    identity = RuntimeIdentity(
        run_id="run-1",
        task_id="root",
        agent_id="mia",
        session_id="session-1",
    )

    runtime = AgentRuntimeFactory(agent_manager=manager).build(
        identity=identity,
        provider=MockProvider(),
        cwd=tmp_path,
    )

    assert runtime.agent.agent_id == "mia"
    assert runtime.session_store.path.parent == manager.agent_home("mia") / "sessions"
    assert not hasattr(runtime, "profile")
    metadata = runtime.session_store.load_entries()[0]
    assert metadata.data == identity.model_dump(exclude_none=True)


@pytest.mark.asyncio
async def test_agent_runner_emits_canonical_event_envelopes(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import AgentEventEnvelope
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("done")
    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))

    events = [event async for event in runner.prompt("say hello", provider=provider, cwd=tmp_path)]

    assert events
    assert all(isinstance(event, AgentEventEnvelope) for event in events)
    assert events[-1].agent_id == "mia"
    assert events[-1].event.type == "turn_complete"


def test_run_error_event_is_sanitized_and_attributed() -> None:
    from mia_agent.runtime_events import RunErrorEvent, error_envelope

    identity = RuntimeIdentity(
        run_id="run-1",
        task_id="root",
        agent_id="mia",
        session_id="session-1",
    )

    envelope = error_envelope(
        identity,
        "provider",
        "Authorization: Bearer secret-token",
        cancelled=True,
    )

    assert isinstance(envelope.event, RunErrorEvent)
    assert envelope.event.type == "run_error"
    assert envelope.event.error == "Authorization: [REDACTED]"
    assert envelope.event.cancelled is True
