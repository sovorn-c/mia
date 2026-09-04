from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
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
    assert len(provider.recorded_calls) == 0

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


@pytest.mark.asyncio
async def test_agent_runner_run_executes_research_sequencing(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("architecture findings")
    provider.queue_text_response("research final summary")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    request = RunRequest(
        prompt_text="investigate microservices",
        agent_id="research",
        session_id="session-res-1",
    )

    events = [event async for event in runner.run(request, provider=provider, cwd=tmp_path)]
    assert events

    # Check that both specialist (architect) and coordinator (research) envelopes were emitted
    specialist_events = [e for e in events if e.task_id == "specialist"]
    coordinator_events = [e for e in events if e.task_id == "root"]

    assert specialist_events
    assert coordinator_events
    assert specialist_events[0].agent_id == "architect"
    assert coordinator_events[0].agent_id == "research"
    assert coordinator_events[-1].event.type == "turn_complete"


@pytest.mark.asyncio
async def test_terminal_truth_exactly_one_terminal_envelope_normal_consumption(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("completed")
    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    request = RunRequest(prompt_text="hello", agent_id="mia")

    events = [e async for e in runner.run(request, provider=provider, cwd=tmp_path)]
    assert events
    assert events[-1].event.type == "turn_complete"
    # Verify no other terminal event exists earlier in the stream
    terminals = [e for e in events if e.event.type in ("turn_complete", "run_error")]
    assert len(terminals) == 1


@pytest.mark.asyncio
async def test_terminal_truth_missing_terminal_becomes_run_error(tmp_path) -> None:
    from unittest.mock import MagicMock

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.events import AssistantChunkEvent
    from mia_agent.runtime_events import RunErrorEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import AgentRuntime, RunRequest

    manager = AgentManager(agents_dir=tmp_path / "agents")

    # Mock harness that yields chunks but finishes without TurnCompleteEvent
    async def empty_prompt(prompt_text: str):
        yield AssistantChunkEvent(delta_text="unfinished work")

    mock_harness = MagicMock()
    mock_harness.prompt = empty_prompt

    factory = MagicMock(spec=AgentRuntimeFactory)
    mock_runtime = MagicMock(spec=AgentRuntime)
    mock_runtime.harness = mock_harness
    factory.build.return_value = mock_runtime

    runner = AgentRunner(factory=factory, agent_manager=manager)
    request = RunRequest(prompt_text="incomplete prompt", agent_id="mia")

    events = [e async for e in runner.run(request, cwd=tmp_path)]
    assert events
    last_event = events[-1].event
    assert isinstance(last_event, RunErrorEvent)
    assert last_event.code == "missing_terminal"
    terminals = [e for e in events if e.event.type in ("turn_complete", "run_error")]
    assert len(terminals) == 1


@pytest.mark.asyncio
async def test_terminal_truth_agent_error_normalized_to_run_error(tmp_path) -> None:
    from unittest.mock import MagicMock

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.events import AgentErrorEvent
    from mia_agent.runtime_events import RunErrorEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import AgentRuntime, RunRequest

    manager = AgentManager(agents_dir=tmp_path / "agents")

    async def error_prompt(prompt_text: str):
        yield AgentErrorEvent(error="agent failed unexpectedly")

    mock_harness = MagicMock()
    mock_harness.prompt = error_prompt

    factory = MagicMock(spec=AgentRuntimeFactory)
    mock_runtime = MagicMock(spec=AgentRuntime)
    mock_runtime.harness = mock_harness
    factory.build.return_value = mock_runtime

    runner = AgentRunner(factory=factory, agent_manager=manager)
    request = RunRequest(prompt_text="failing prompt", agent_id="mia")

    events = [e async for e in runner.run(request, cwd=tmp_path)]
    assert events
    last_event = events[-1].event
    assert isinstance(last_event, RunErrorEvent)
    assert last_event.code == "agent_error"
    assert "agent failed unexpectedly" in last_event.error
    # Ensure no raw AgentErrorEvent leaked into envelopes
    assert not any(e.event.type == "agent_error" for e in events)


@pytest.mark.asyncio
async def test_terminal_truth_duplicate_terminal_suppressed(tmp_path) -> None:
    from unittest.mock import MagicMock

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.events import AssistantChunkEvent, TurnCompleteEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import AgentRuntime, RunRequest

    manager = AgentManager(agents_dir=tmp_path / "agents")

    async def duplicate_terminal_prompt(prompt_text: str):
        yield TurnCompleteEvent(total_steps=1, stop_reason="stop")
        yield AssistantChunkEvent(delta_text="rogue event after completion")
        yield TurnCompleteEvent(total_steps=2, stop_reason="stop")

    mock_harness = MagicMock()
    mock_harness.prompt = duplicate_terminal_prompt

    factory = MagicMock(spec=AgentRuntimeFactory)
    mock_runtime = MagicMock(spec=AgentRuntime)
    mock_runtime.harness = mock_harness
    factory.build.return_value = mock_runtime

    runner = AgentRunner(factory=factory, agent_manager=manager)
    request = RunRequest(prompt_text="test duplicate terminal", agent_id="mia")

    events = [e async for e in runner.run(request, cwd=tmp_path)]
    assert len(events) == 1
    assert events[0].event.type == "turn_complete"


@pytest.mark.asyncio
async def test_cancellation_before_finalization_raises_without_envelope(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
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
        ):
            started.set()
            await asyncio.Event().wait()
            yield StreamChunk(type="finish")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    seen = []

    async def consume() -> None:
        req = RunRequest(prompt_text="hello", agent_id="mia")
        async for env in runner.run(req, provider=BlockingProvider(), cwd=tmp_path):
            seen.append(env)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Pre-finalization cancellation must NOT yield a terminal or error envelope
    terminals = [e for e in seen if e.event.type in ("turn_complete", "run_error")]
    assert len(terminals) == 0


@pytest.mark.asyncio
async def test_aclose_before_finalization_finalizes_cancelled_without_envelope(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("hello world")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    req = RunRequest(prompt_text="hello", agent_id="mia")
    stream = runner.run(req, provider=provider, cwd=tmp_path)

    # Receive the first event (turn_start), then close the stream before turn_complete
    first_event = await stream.__anext__()
    assert first_event.event.type == "turn_start"

    # Await aclose() on stream before finalization
    await stream.aclose()

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


@pytest.mark.asyncio
async def test_aclose_after_terminal_delivery_is_idempotent(tmp_path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("finished")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    req = RunRequest(prompt_text="hello", agent_id="mia")
    stream = runner.run(req, provider=provider, cwd=tmp_path)

    events = [e async for e in stream]
    assert events
    assert events[-1].event.type == "turn_complete"

    # Awaiting aclose() after terminal delivery is idempotent
    await stream.aclose()
    await stream.aclose()


@pytest.mark.asyncio
async def test_late_cancellation_deferred_until_terminal_envelope_returned(tmp_path) -> None:
    from unittest.mock import MagicMock

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.events import TurnCompleteEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import AgentRuntime, RunRequest

    manager = AgentManager(agents_dir=tmp_path / "agents")

    async def harness_prompt(prompt_text: str):
        yield TurnCompleteEvent(total_steps=1, stop_reason="stop")

    mock_harness = MagicMock()
    mock_harness.prompt = harness_prompt

    factory = MagicMock(spec=AgentRuntimeFactory)
    mock_runtime = MagicMock(spec=AgentRuntime)
    mock_runtime.harness = mock_harness
    factory.build.return_value = mock_runtime

    runner = AgentRunner(factory=factory, agent_manager=manager)
    req = RunRequest(prompt_text="hello", agent_id="mia")

    seen = []

    async def run_with_cancel() -> None:
        async for env in runner.run(req, cwd=tmp_path):
            seen.append(env)
            # Cancel current task immediately upon receiving terminal envelope
            asyncio.current_task().cancel()

    consume_task = asyncio.create_task(run_with_cancel())
    with pytest.raises(asyncio.CancelledError):
        await consume_task

    assert len(seen) == 1
    assert seen[0].event.type == "turn_complete"


@pytest.mark.asyncio
async def test_bare_abandonment_has_no_lifecycle_guarantee(tmp_path) -> None:
    """Document and test that bare abandonment has no timing guarantee, while aclosing is safe."""
    from contextlib import aclosing

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    provider = MockProvider()
    provider.queue_text_response("hello")

    runner = AgentRunner(agent_manager=AgentManager(agents_dir=tmp_path / "agents"))
    req = RunRequest(prompt_text="hello", agent_id="mia")

    # When using contextlib.aclosing, early break is safely closed
    async with aclosing(runner.run(req, provider=provider, cwd=tmp_path)) as stream:
        async for _env in stream:
            break


def test_settings_precedence_request_overrides_agent_over_global(tmp_path: Path) -> None:
    from mia_agent.agents import AgentManager
    from mia_agent.auth.config import ConfigManager, MiaConfig
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_ai.providers.mock import MockProvider

    agents_dir = tmp_path / "agents"
    manager = AgentManager(agents_dir=agents_dir)
    manager.create_agent(
        "custom",
        display_name="Custom",
        model="agent-model",
        context_window_tokens=60000,
        compaction_threshold_ratio=0.3,
    )

    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    config_mgr.save_config(
        MiaConfig(
            default_model="global-model",
            context_window_tokens=50000,
            compaction_threshold_ratio=0.4,
        )
    )

    factory = AgentRuntimeFactory(agent_manager=manager, config_manager=config_mgr)

    # 1. Request override wins
    runtime1 = factory.build(
        identity=RuntimeIdentity(run_id="r1", task_id="root", agent_id="custom", session_id="s1"),
        provider=MockProvider(),
        model_override="request-model",
        context_window=70000,
        compaction_threshold=0.2,
        cwd=tmp_path,
    )
    assert runtime1.harness.model == "request-model"
    assert runtime1.harness.compactor is not None
    assert runtime1.harness.compactor.context_window_tokens == 70000
    assert runtime1.harness.compactor.compaction_threshold_ratio == 0.2

    # 2. Agent wins when request has None
    runtime2 = factory.build(
        identity=RuntimeIdentity(run_id="r2", task_id="root", agent_id="custom", session_id="s2"),
        provider=MockProvider(),
        cwd=tmp_path,
    )
    assert runtime2.harness.model == "agent-model"
    assert runtime2.harness.compactor is not None
    assert runtime2.harness.compactor.context_window_tokens == 60000
    assert runtime2.harness.compactor.compaction_threshold_ratio == 0.3

    # 3. Global config wins when agent has None
    manager.create_agent(
        "bare",
        display_name="Bare",
    )
    runtime3 = factory.build(
        identity=RuntimeIdentity(run_id="r3", task_id="root", agent_id="bare", session_id="s3"),
        provider=MockProvider(),
        cwd=tmp_path,
    )
    assert runtime3.harness.model == "global-model"
    assert runtime3.harness.compactor is not None
    assert runtime3.harness.compactor.context_window_tokens == 50000
    assert runtime3.harness.compactor.compaction_threshold_ratio == 0.4


def test_capability_override_cannot_broaden_agent_tools(tmp_path: Path) -> None:
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_ai.providers.mock import MockProvider

    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent("limited", display_name="Limited", tools=["read_file"])
    factory = AgentRuntimeFactory(agent_manager=manager)

    with pytest.raises(ValueError, match="broaden.*capabilities"):
        factory.build(
            identity=RuntimeIdentity(
                run_id="r1", task_id="root", agent_id="limited", session_id="s1"
            ),
            provider=MockProvider(),
            capabilities_override=["read_file", "bash"],
            cwd=tmp_path,
        )


def test_access_policy_override_cannot_escalate_access(tmp_path: Path) -> None:
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_ai.providers.mock import MockProvider

    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent("readonly_agent", display_name="RO", access_policy="read-only")
    factory = AgentRuntimeFactory(agent_manager=manager)

    with pytest.raises(ValueError, match="escalate.*access"):
        factory.build(
            identity=RuntimeIdentity(
                run_id="r1", task_id="root", agent_id="readonly_agent", session_id="s1"
            ),
            provider=MockProvider(),
            access_policy_override="full-access",
            cwd=tmp_path,
        )


@pytest.mark.asyncio
async def test_session_admission_same_session_conflict_fails_fast_with_session_busy(
    tmp_path: Path,
) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_events import RunErrorEvent
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.base import LLMProvider
    from mia_ai.types import ChatMessage, StreamChunk, ToolDefinition

    started = asyncio.Event()
    unblock = asyncio.Event()

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
        ):
            started.set()
            await unblock.wait()
            yield StreamChunk(type="text_delta", delta="done")
            yield StreamChunk(type="finish", finish_reason="stop")

    manager = AgentManager(agents_dir=tmp_path / "agents")
    runner = AgentRunner(agent_manager=manager)
    req1 = RunRequest(prompt_text="turn 1", agent_id="mia", session_id="s_shared")
    req2 = RunRequest(prompt_text="turn 2", agent_id="mia", session_id="s_shared")
    from mia_ai.providers.mock import MockProvider

    provider2 = MockProvider()
    events1: list[object] = []
    events2: list[object] = []

    async def run1():
        async for env in runner.run(req1, provider=BlockingProvider(), cwd=tmp_path):
            events1.append(env)

    async def run2():
        async for env in runner.run(req2, provider=provider2, cwd=tmp_path):
            events2.append(env)

    task1 = asyncio.create_task(run1())
    await started.wait()

    # While run1 is active on (mia, s_shared), start run2
    await run2()

    assert len(events2) == 1
    assert isinstance(events2[0].event, RunErrorEvent)
    assert events2[0].event.code == "session_busy"
    assert events2[0].event.stage == "admission"

    # Unblock run1
    unblock.set()
    await task1

    assert any(env.event.type == "turn_complete" for env in events1)


@pytest.mark.asyncio
async def test_session_admission_released_on_completion_cancellation_and_error(
    tmp_path: Path,
) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    manager = AgentManager(agents_dir=tmp_path / "agents")
    runner = AgentRunner(agent_manager=manager)
    provider = MockProvider()
    provider.queue_text_response("first")
    provider.queue_text_response("second")

    req = RunRequest(prompt_text="first turn", agent_id="mia", session_id="s_admit")
    events = []
    async for env in runner.run(req, provider=provider, cwd=tmp_path):
        events.append(env)
    assert any(env.event.type == "turn_complete" for env in events)

    # Immediately run again on the same session; it must succeed (admission was released)
    req2 = RunRequest(prompt_text="second turn", agent_id="mia", session_id="s_admit")
    events2 = []
    async for env in runner.run(req2, provider=provider, cwd=tmp_path):
        events2.append(env)
    assert any(env.event.type == "turn_complete" for env in events2)


@pytest.mark.asyncio
async def test_session_admission_distinct_sessions_run_concurrently(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    manager = AgentManager(agents_dir=tmp_path / "agents")
    runner = AgentRunner(agent_manager=manager)

    provider1 = MockProvider()
    provider1.queue_text_response("sess1 done")
    provider2 = MockProvider()
    provider2.queue_text_response("sess2 done")

    req1 = RunRequest(prompt_text="hello 1", agent_id="mia", session_id="sess_1")
    req2 = RunRequest(prompt_text="hello 2", agent_id="mia", session_id="sess_2")

    events1 = []
    events2 = []

    async def r1():
        async for env in runner.run(req1, provider=provider1, cwd=tmp_path):
            events1.append(env)

    async def r2():
        async for env in runner.run(req2, provider=provider2, cwd=tmp_path):
            events2.append(env)

    await asyncio.gather(r1(), r2())

    assert any(env.event.type == "turn_complete" for env in events1)
    assert any(env.event.type == "turn_complete" for env in events2)


@pytest.mark.asyncio
async def test_lifecycle_execution_order_finalization_cleanup_admission_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.agent_runner import AgentRunner, _RunLifecycle
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_agent.session.admission import SessionAdmission
    from mia_ai.providers.mock import MockProvider

    events_log: list[str] = []

    orig_finalize = _RunLifecycle.finalize

    def spy_finalize(self, outcome: str, envelope=None) -> bool:
        events_log.append(f"finalize:{outcome}")
        return orig_finalize(self, outcome, envelope)

    monkeypatch.setattr(_RunLifecycle, "finalize", spy_finalize)

    orig_release = SessionAdmission.release

    def spy_release(agent_id: str, session_id: str) -> None:
        events_log.append("admission_release")
        return orig_release(agent_id, session_id)

    monkeypatch.setattr(SessionAdmission, "release", spy_release)

    def test_disposer() -> None:
        # SessionAdmission must still be held during cleanup
        assert SessionAdmission.is_admitted("mia", "s_order")
        events_log.append("cleanup")

    test_disposer.plugin_id = "test_plugin"  # type: ignore[attr-defined]

    agents = AgentManager(agents_dir=tmp_path / "agents")
    factory = AgentRuntimeFactory(agent_manager=agents)

    orig_build = factory.build

    def build_with_disposer(*args, **kwargs):
        kwargs["disposers"] = [test_disposer]
        return orig_build(*args, **kwargs)

    factory.build = build_with_disposer  # type: ignore[method-assign]

    runner = AgentRunner(agent_manager=agents, factory=factory)
    provider = MockProvider()
    provider.queue_text_response("completed order test")

    req = RunRequest(prompt_text="test order", agent_id="mia", session_id="s_order")

    async for env in runner.run(req, provider=provider, cwd=tmp_path):
        if env.event.type == "turn_complete":
            # SessionAdmission must already be released before terminal delivery
            assert not SessionAdmission.is_admitted("mia", "s_order")
            events_log.append("terminal_delivery")

    assert events_log == ["finalize:success", "cleanup", "admission_release", "terminal_delivery"]


@pytest.mark.asyncio
async def test_lifecycle_execution_order_on_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.agent_runner import AgentRunner, _RunLifecycle
    from mia_agent.agents import AgentManager
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_agent.session.admission import SessionAdmission
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
        ):
            started.set()
            await asyncio.Event().wait()
            yield StreamChunk(type="finish")

    events_log: list[str] = []

    orig_finalize = _RunLifecycle.finalize

    def spy_finalize(self, outcome: str, envelope=None) -> bool:
        events_log.append(f"finalize:{outcome}")
        return orig_finalize(self, outcome, envelope)

    monkeypatch.setattr(_RunLifecycle, "finalize", spy_finalize)

    orig_release = SessionAdmission.release

    def spy_release(agent_id: str, session_id: str) -> None:
        events_log.append("admission_release")
        return orig_release(agent_id, session_id)

    monkeypatch.setattr(SessionAdmission, "release", spy_release)

    def cancel_disposer() -> None:
        # SessionAdmission must still be held during cleanup
        assert SessionAdmission.is_admitted("mia", "s_cancel_order")
        events_log.append("cleanup")

    cancel_disposer.plugin_id = "cancel_plugin"  # type: ignore[attr-defined]

    agents = AgentManager(agents_dir=tmp_path / "agents")
    factory = AgentRuntimeFactory(agent_manager=agents)

    orig_build = factory.build

    def build_with_disposer(*args, **kwargs):
        kwargs["disposers"] = [cancel_disposer]
        return orig_build(*args, **kwargs)

    factory.build = build_with_disposer  # type: ignore[method-assign]

    runner = AgentRunner(agent_manager=agents, factory=factory)
    req = RunRequest(prompt_text="cancel me", agent_id="mia", session_id="s_cancel_order")

    async def consume() -> None:
        async for _ in runner.run(req, provider=BlockingProvider(), cwd=tmp_path):
            pass

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert events_log == ["finalize:cancelled", "cleanup", "admission_release"]
    assert not SessionAdmission.is_admitted("mia", "s_cancel_order")
