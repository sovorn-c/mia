from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import Mock

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


def test_runtime_factory_rejects_unknown_constructor_options() -> None:
    from mia_agent.runtime_factory import AgentRuntimeFactory

    with pytest.raises(TypeError):
        AgentRuntimeFactory(removed_manager=object())  # type: ignore[call-arg]


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


@pytest.mark.asyncio
async def test_runner_rejects_unknown_agent_without_escaping(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_ai.providers.mock import MockProvider

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))

    events = [
        event
        async for event in runner.prompt(
            "hello", agent_id="missing", provider=MockProvider(), cwd=tmp_path
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0].event, RunErrorEvent)
    assert events[0].agent_id == "missing"


@pytest.mark.asyncio
async def test_runner_rejects_session_traversal_without_writing_outside(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_ai.providers.mock import MockProvider

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))

    events = [
        event
        async for event in runner.prompt(
            "hello", session_id="../outside", provider=MockProvider(), cwd=tmp_path
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0].event, RunErrorEvent)
    assert "/" not in events[0].session_id
    assert not (tmp_path / "outside.jsonl").exists()


@pytest.mark.asyncio
async def test_runner_propagates_cancellation_after_emitting_event(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_ai.providers.base import LLMProvider
    from mia_ai.types import ChatMessage, StreamChunk, ToolDefinition

    started = asyncio.Event()

    class BlockingProvider(LLMProvider):
        async def stream(
            self,
            *,
            model: str,
            messages: list[ChatMessage],
            tools: list[ToolDefinition] | None = None,
            system: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> AsyncIterator[StreamChunk]:
            started.set()
            await asyncio.Event().wait()
            yield StreamChunk(type="finish")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    seen = []

    async def consume() -> None:
        async for event in runner.prompt("hello", provider=BlockingProvider(), cwd=tmp_path):
            seen.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert isinstance(seen[-1].event, RunErrorEvent)
    assert seen[-1].event.cancelled is True


@pytest.mark.asyncio
async def test_research_coordinator_failure_is_attributed(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("findings")
    manager = AgentManager(agents_dir=tmp_path / "agents")
    identity = RuntimeIdentity(
        run_id="run-specialist",
        task_id="specialist",
        agent_id="architect",
        session_id="session-specialist",
    )
    specialist = AgentRuntimeFactory(agent_manager=manager).build(
        identity=identity, provider=provider, cwd=tmp_path
    )
    factory = Mock(spec=AgentRuntimeFactory)
    factory.build.side_effect = [specialist, RuntimeError("coordinator failed")]
    runner = AgentRunner(factory=factory, agent_manager=manager)

    events = [event async for event in runner.prompt("research", agent_id="research")]

    assert isinstance(events[-1].event, RunErrorEvent)
    assert events[-1].event.stage == "coordinator"


@pytest.mark.asyncio
async def test_research_factory_failure_is_sanitized(tmp_path) -> None:
    from unittest.mock import Mock

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory

    factory = Mock(spec=AgentRuntimeFactory)
    factory.build.side_effect = RuntimeError("Authorization: Bearer secret-token")
    runner = AgentRunner(
        factory=factory,
        agent_manager=AgentManager(agents_dir=tmp_path / "agents"),
    )

    events = [
        event
        async for event in runner.prompt("research", agent_id="research", session_id="../outside")
    ]

    assert len(events) == 1
    assert isinstance(events[0].event, RunErrorEvent)
    assert events[0].event.error == "Authorization: [REDACTED]"
    assert events[0].agent_id == "architect"
    assert "/" not in events[0].session_id


def test_error_redacts_plain_credential_assignments() -> None:
    from mia_middleware.access import sanitize_arguments

    assert sanitize_arguments("api_key=supersecret") == "api_key=[REDACTED]"
    assert sanitize_arguments("token: supersecret") == "token: [REDACTED]"
    assert sanitize_arguments("password='secret value'") == "password=[REDACTED]"
    assert "supersecret" not in sanitize_arguments('{"api_key": "supersecret"}')
    assert "super secret" not in sanitize_arguments("{'api_key': 'super secret'}")
    assert sanitize_arguments("Authorization: Basic abc123") == "Authorization: [REDACTED]"
    assert "gho_secret" not in sanitize_arguments("provider failed: gho_secret")


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


def test_run_request_validation_and_immutability() -> None:
    from mia_agent.runtime_models import RunRequest

    req = RunRequest(prompt_text="hello world", agent_id="mia")
    assert req.prompt_text == "hello world"
    assert req.agent_id == "mia"
    assert req.task_id == "root"

    # Immutability
    with pytest.raises(ValidationError):
        req.prompt_text = "new"  # type: ignore[misc]

    # Rejects extra fields
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", extra_field="bad")  # type: ignore[call-arg]

    # Rejects blank prompt
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="   \t\n  ")

    # Rejects unsafe IDs
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", agent_id="../bad")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", agent_id="has/slash")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", session_id="..\\traversal")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", session_id="bad/path")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", run_id="bad/run")
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", task_id="   ")

    # Rejects invalid compaction threshold
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", compaction_threshold=-0.1)
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", compaction_threshold=0.0)
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", compaction_threshold=1.5)

    # Valid compaction threshold
    valid_thresh = RunRequest(prompt_text="hello", compaction_threshold=0.8)
    assert valid_thresh.compaction_threshold == 0.8

    # Rejects invalid context window
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", context_window=0)
    with pytest.raises(ValidationError):
        RunRequest(prompt_text="hello", context_window=-10)

    # Valid context window
    valid_cw = RunRequest(prompt_text="hello", context_window=4096)
    assert valid_cw.context_window == 4096


@pytest.mark.asyncio
async def test_run_request_first_iteration_acceptance_and_attribution(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import AgentEventEnvelope
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("first iteration response")
    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))

    request = RunRequest(
        prompt_text="plan work",
        agent_id="mia",
        session_id="session-e07",
        task_id="task-1",
    )

    stream = runner.run(request, provider=provider, cwd=tmp_path)
    # Generator created, but not iterated yet — no provider calls made yet
    assert len(provider.sent_messages) == 0

    events: list[AgentEventEnvelope] = []
    async for env in stream:
        events.append(env)

    assert events
    assert all(isinstance(e, AgentEventEnvelope) for e in events)
    for e in events:
        assert e.agent_id == "mia"
        assert e.session_id == "session-e07"
        assert e.task_id == "task-1"
        assert e.run_id is not None
        assert e.run_id == events[0].run_id
    assert events[-1].event.type == "turn_complete"

