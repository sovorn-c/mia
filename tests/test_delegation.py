"""Contract tests for bounded direct Agent Delegation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mia_agent.agents import AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.delegation import TaskRequest, TaskResult
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import RuntimeIdentity
from mia_ai.providers.mock import MockProvider
from mia_ai.types import StreamChunk


def make_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(
        agents_dir=tmp_path / "agents",
    )


def make_factory(tmp_path: Path, manager: AgentManager) -> AgentRuntimeFactory:
    return AgentRuntimeFactory(
        agent_manager=manager,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )


def test_task_contract_validates_attribution_timeout_and_secret_free_payload() -> None:
    request = TaskRequest(
        task_id="task-1",
        caller_agent_id="mia",
        recipient_agent_id="researcher",
        prompt="Summarize the repository.",
        parent_run_id="run-parent",
        parent_session_id="session-parent",
        timeout=30,
    )
    assert request.depth == 0
    assert request.timeout == 30
    assert "sk-secret" not in json.dumps(request.model_dump())

    with pytest.raises(ValidationError):
        TaskRequest(caller_agent_id="same", recipient_agent_id="same", prompt="work")
    with pytest.raises(ValidationError):
        TaskRequest(
            caller_agent_id="mia", recipient_agent_id="researcher", prompt="work", timeout=0
        )
    with pytest.raises(ValidationError):
        TaskRequest(
            caller_agent_id="mia",
            recipient_agent_id="researcher",
            prompt="work",
            timeout=301,
        )
    with pytest.raises(ValidationError):
        TaskRequest(caller_agent_id="mia", recipient_agent_id="researcher", prompt=" ")

    with pytest.raises(ValidationError):
        TaskResult(
            task_id="task-1",
            caller_agent_id="mia",
            recipient_agent_id="researcher",
            child_run_id="run-child",
            child_session_id="session-child",
            outcome="succeeded",
        )


@pytest.mark.asyncio
async def test_eligible_agent_delegates_to_recipient_owned_session(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller",
        display_name="Caller",
        instructions="Delegate bounded work.",
        tools=["read_file"],
        delegation_targets=["researcher"],
    )
    manager.create_agent(
        "researcher",
        display_name="Researcher",
        instructions="Return concise findings.",
        tools=[],
    )
    provider = MockProvider()
    provider.queue_text_response("The findings are ready.")
    from mia_agent.delegation import DelegationService

    service = DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=provider,
    )
    result = await service.delegate(
        TaskRequest(
            task_id="task-success",
            caller_agent_id="caller",
            recipient_agent_id="researcher",
            prompt="Find the key result.",
            parent_run_id="run-parent",
            parent_session_id="session-parent",
        )
    )

    assert result.outcome == "succeeded"
    assert result.response == "The findings are ready."
    assert result.caller_agent_id == "caller"
    assert result.recipient_agent_id == "researcher"
    assert result.child_run_id
    assert result.child_session_id
    child_path = manager.get_session_dir("researcher") / f"{result.child_session_id}.jsonl"
    assert child_path.exists()
    assert len(provider.recorded_calls) == 1
    assert provider.recorded_calls[0]["messages"][-1]["content"] == "Find the key result."


@pytest.mark.asyncio
async def test_ineligible_recipient_is_rejected_before_provider_or_session(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent("caller", display_name="Caller", tools=[])
    manager.create_agent("researcher", display_name="Researcher", tools=[])
    provider = MockProvider()
    from mia_agent.delegation import DelegationService

    service = DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=provider,
    )
    result = await service.delegate(
        TaskRequest(
            task_id="task-rejected",
            caller_agent_id="caller",
            recipient_agent_id="researcher",
            prompt="Do not run.",
        )
    )

    assert result.outcome == "rejected"
    assert result.error
    assert provider.recorded_calls == []
    assert not (tmp_path / "agents" / "researcher" / "sessions").exists()


@pytest.mark.asyncio
async def test_delegate_tool_returns_serialized_task_result() -> None:
    from mia_tools.delegate import DelegateTaskTool

    result = TaskResult(
        task_id="task",
        caller_agent_id="caller",
        recipient_agent_id="recipient",
        child_run_id="run",
        child_session_id="session",
        outcome="succeeded",
        response="done",
    )

    async def submit(_recipient: str, _prompt: str, _timeout: float) -> TaskResult:
        return result

    payload = await DelegateTaskTool(submit).execute("recipient", "work")
    assert payload["outcome"] == "succeeded"
    assert payload["task_id"] == "task"


def test_delegate_tool_is_injected_only_at_depth_zero(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller",
        display_name="Caller",
        tools=[],
        delegation_targets=["recipient"],
    )

    class Service:
        def for_caller(self, _identity: RuntimeIdentity):
            async def submit(_recipient: str, _prompt: str, _timeout: float) -> TaskResult:
                return TaskResult(
                    task_id="task",
                    caller_agent_id="caller",
                    recipient_agent_id="recipient",
                    child_run_id="run",
                    child_session_id="session",
                    outcome="failed",
                    error="not run",
                )

            return submit

    factory = make_factory(tmp_path, manager)
    root = factory.build(
        identity=RuntimeIdentity(
            agent_id="caller", run_id="run-root", task_id="root", session_id="session-root"
        ),
        provider=MockProvider(),
        delegation_service=Service(),
        delegation_depth=0,
    )
    child = factory.build(
        identity=RuntimeIdentity(
            agent_id="caller", run_id="run-child", task_id="task", session_id="session-child"
        ),
        provider=MockProvider(),
        delegation_service=Service(),
        delegation_depth=1,
    )
    assert [tool.name for tool in root.harness.tools] == ["delegate_task"]
    assert [tool.name for tool in child.harness.tools] == []


class ErrorChunkProvider(MockProvider):
    async def stream(self, **kwargs):
        yield StreamChunk(type="error", error="provider secret sk-error")
        yield StreamChunk(type="finish", finish_reason="stop")


class CancelledProvider(MockProvider):
    async def stream(self, **kwargs):
        raise asyncio.CancelledError()
        yield StreamChunk(type="finish")


class NeverProvider(MockProvider):
    async def stream(self, **kwargs):
        await asyncio.Event().wait()
        yield StreamChunk(type="finish")


class SlowProvider(MockProvider):
    async def stream(self, **kwargs):
        await asyncio.sleep(0.2)
        yield StreamChunk(type="finish", finish_reason="stop")


@pytest.mark.asyncio
async def test_delegation_uses_restrictive_access_and_capability_intersection(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller",
        display_name="Caller",
        tools=["read_file"],
        access_policy="approval-required",
        delegation_targets=["recipient"],
    )
    manager.create_agent(
        "recipient",
        display_name="Recipient",
        tools=["read_file", "write_file"],
        access_policy="full-access",
        confirm_full_access=True,
    )
    provider = MockProvider()
    provider.queue_text_response("safe result")
    from mia_agent.delegation import DelegationService

    result = await DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=provider,
    ).delegate(TaskRequest(caller_agent_id="caller", recipient_agent_id="recipient", prompt="work"))

    assert result.outcome == "succeeded"
    assert [tool["name"] for tool in provider.recorded_calls[0]["tools"]] == ["read_file"]


@pytest.mark.asyncio
async def test_provider_error_chunk_is_failed_not_success(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller", display_name="Caller", tools=[], delegation_targets=["recipient"]
    )
    manager.create_agent("recipient", display_name="Recipient", tools=[])
    from mia_agent.delegation import DelegationService

    service = DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=ErrorChunkProvider(),
    )
    result = await service.delegate(
        TaskRequest(caller_agent_id="caller", recipient_agent_id="recipient", prompt="work")
    )
    assert result.outcome == "failed"
    assert result.response is None
    assert "sk-error" not in str(result.model_dump())


@pytest.mark.asyncio
async def test_max_steps_is_failed_not_success(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller", display_name="Caller", tools=["read_file"], delegation_targets=["recipient"]
    )
    manager.create_agent(
        "recipient", display_name="Recipient", tools=["read_file"], max_steps_per_turn=1
    )
    provider = MockProvider()
    provider.queue_tool_call_response("read_file", {"path": "missing.txt"})
    from mia_agent.delegation import DelegationService

    result = await DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=provider,
    ).delegate(TaskRequest(caller_agent_id="caller", recipient_agent_id="recipient", prompt="work"))
    assert result.outcome == "failed"
    assert result.error and "max_steps" in result.error


@pytest.mark.asyncio
async def test_provider_cancellation_is_recorded_without_false_success(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller", display_name="Caller", tools=[], delegation_targets=["recipient"]
    )
    manager.create_agent("recipient", display_name="Recipient", tools=[])
    from mia_agent.delegation import DelegationService

    result = await DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=CancelledProvider(),
    ).delegate(TaskRequest(caller_agent_id="caller", recipient_agent_id="recipient", prompt="work"))
    assert result.outcome == "cancelled"


@pytest.mark.asyncio
async def test_caller_cancellation_is_recorded_and_propagated(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller", display_name="Caller", tools=[], delegation_targets=["recipient"]
    )
    manager.create_agent("recipient", display_name="Recipient", tools=[])
    from mia_agent.delegation import DelegationService

    service = DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=NeverProvider(),
    )
    task = asyncio.create_task(
        service.delegate(
            TaskRequest(caller_agent_id="caller", recipient_agent_id="recipient", prompt="work")
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    records = list((tmp_path / "agents" / "recipient" / "sessions").glob("*.jsonl"))
    assert records
    assert any('"outcome":"cancelled"' in path.read_text() for path in records)


@pytest.mark.asyncio
async def test_timeout_is_truthful_and_does_not_leave_a_child_running(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.create_agent(
        "caller", display_name="Caller", tools=[], delegation_targets=["recipient"]
    )
    manager.create_agent("recipient", display_name="Recipient", tools=[])
    from mia_agent.delegation import DelegationService

    service = DelegationService(
        agent_manager=manager,
        factory=make_factory(tmp_path, manager),
        provider=SlowProvider(),
    )
    result = await service.delegate(
        TaskRequest(
            caller_agent_id="caller",
            recipient_agent_id="recipient",
            prompt="work",
            timeout=0.01,
        )
    )
    assert result.outcome == "timed-out"
    await asyncio.sleep(0)
    assert not [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done()
    ]


def test_task_result_rejects_unknown_outcome_and_secret_values() -> None:
    with pytest.raises(ValidationError):
        TaskResult(
            task_id="task",
            caller_agent_id="caller",
            recipient_agent_id="recipient",
            child_run_id="run",
            child_session_id="session",
            outcome="unknown",
            error="bad",
        )
    result = TaskResult(
        task_id="task",
        caller_agent_id="caller",
        recipient_agent_id="recipient",
        child_run_id="run",
        child_session_id="session",
        outcome="failed",
        error="provider failed",
    )
    assert "sk-secret" not in json.dumps(result.model_dump())
