"""Bounded, synchronous Agent-to-Agent Delegation."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from mia_agent.agents import AgentManager
from mia_agent.delegation_models import (
    MAX_DELEGATION_TIMEOUT,
    TaskOutcome,
    TaskRequest,
    TaskResult,
)
from mia_agent.events import AgentErrorEvent, AssistantChunkEvent, TurnCompleteEvent
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import AgentRuntime, RuntimeIdentity
from mia_agent.session import SessionAdmission
from mia_agent.session.entries import CustomEntry
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import compose_effective_access, sanitize_arguments


class DelegationService:
    """Coordinate one validated, one-hop child Run through the shared runtime factory."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        factory: AgentRuntimeFactory | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self.agent_manager = agent_manager or (factory.agent_manager if factory else AgentManager())
        self.factory = factory or AgentRuntimeFactory(agent_manager=self.agent_manager)
        self.factory.delegation_service = self
        self.provider = provider

    async def delegate(
        self,
        request: TaskRequest | None = None,
        **request_fields: Any,
    ) -> TaskResult:
        """Validate and execute one bounded Task, returning one terminal result."""
        if request is None:
            request = TaskRequest(**request_fields)
        elif request_fields:
            raise TypeError("Pass either a TaskRequest or request fields, not both")

        caller, recipient, rejection = self._resolve_target(request)
        if rejection:
            return self._rejected(request, rejection)

        assert caller is not None
        assert recipient is not None
        effective = compose_effective_access(
            caller.access_policy,
            recipient.access_policy,
            caller.tools,
            recipient.tools,
        )
        child_session = (
            request.child_session_id
            if request.child_session_id is not None
            else f"session_{uuid.uuid4().hex[:12]}"
        )
        child_identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id=request.task_id,
            agent_id=recipient.agent_id,
            session_id=child_session,
            parent_session_id=request.parent_session_id,
        )

        if not SessionAdmission.acquire(child_identity.agent_id, child_identity.session_id):
            result = self._result(
                request,
                child_identity,
                "failed",
                error=f"Session '{child_identity.session_id}' is already active for Agent '{child_identity.agent_id}'",
            )
            return self._persist_result(runtime=None, result=result)

        try:
            try:
                runtime = self.factory.build(
                    identity=child_identity,
                    provider=self.provider,
                    access_policy_override=effective.access_level,
                    capabilities_override=effective.capabilities,
                    full_access_confirmed=(
                        caller.full_access_confirmed and recipient.full_access_confirmed
                    ),
                    delegation_depth=1,
                )
            except Exception as exc:
                result = self._result(
                    request,
                    child_identity,
                    "failed",
                    error=f"child runtime could not start: {exc}",
                )
                return self._persist_result(runtime=None, result=result)

            try:
                result = await self._run_child(request, runtime)
            except asyncio.CancelledError:
                result = self._result(
                    request,
                    child_identity,
                    "cancelled",
                    error="child Task was cancelled",
                )
                self._persist_result(runtime=runtime, result=result)
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                return result
            except TimeoutError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    result = self._result(
                        request,
                        child_identity,
                        "cancelled",
                        error="child Task was cancelled",
                    )
                    self._persist_result(runtime=runtime, result=result)
                    raise asyncio.CancelledError from None
                result = self._result(
                    request,
                    child_identity,
                    "timed-out",
                    error=f"child Task exceeded {request.timeout:g}s timeout",
                )
            except Exception as exc:
                result = self._result(
                    request,
                    child_identity,
                    "failed",
                    error=f"child Task failed: {exc}",
                )
            return self._persist_result(runtime=runtime, result=result)
        finally:
            SessionAdmission.release(child_identity.agent_id, child_identity.session_id)

    def for_caller(
        self,
        identity: RuntimeIdentity,
    ) -> Callable[[str, str, float], Awaitable[TaskResult]]:
        """Bind the built-in Tool to one caller's attribution."""

        async def submit(recipient_agent_id: str, prompt: str, timeout: float) -> TaskResult:
            return await self.delegate(
                TaskRequest(
                    caller_agent_id=identity.agent_id,
                    recipient_agent_id=recipient_agent_id,
                    prompt=prompt,
                    parent_run_id=identity.run_id,
                    parent_session_id=identity.session_id,
                    timeout=timeout,
                    depth=1 if identity.task_id != "root" else 0,
                )
            )

        return submit

    def _resolve_target(self, request: TaskRequest) -> tuple[Any | None, Any | None, str | None]:
        if request.depth != 0:
            return None, None, "recursive Delegation is not supported"
        try:
            caller = self.agent_manager.get_agent(request.caller_agent_id)
        except ValueError:
            return None, None, f"caller Agent '{request.caller_agent_id}' was not found"
        if request.recipient_agent_id not in caller.delegation_targets:
            return (
                caller,
                None,
                (
                    f"recipient Agent '{request.recipient_agent_id}' is not an eligible Delegation target"
                ),
            )
        try:
            recipient = self.agent_manager.get_agent(request.recipient_agent_id)
        except ValueError:
            return caller, None, f"recipient Agent '{request.recipient_agent_id}' was not found"
        return caller, recipient, None

    async def _run_child(self, request: TaskRequest, runtime: AgentRuntime) -> TaskResult:
        response: list[str] = []
        terminal: str | None = None
        terminal_error: str | None = None
        async with asyncio.timeout(request.timeout):
            async with contextlib.aclosing(runtime.harness.prompt(request.prompt)) as stream:
                async for event in stream:
                    if isinstance(event, AssistantChunkEvent) and event.delta_text:
                        response.append(event.delta_text)
                    elif isinstance(event, AgentErrorEvent):
                        terminal_error = event.error
                    elif isinstance(event, TurnCompleteEvent):
                        terminal = event.stop_reason

        content = "".join(response).strip()
        if terminal_error:
            return self._result(
                request,
                runtime.identity,
                "failed",
                error=f"recipient Agent error: {terminal_error}",
            )
        if terminal == "stop" and content:
            return self._result(request, runtime.identity, "succeeded", response=content)
        if terminal == "max_steps":
            return self._result(
                request, runtime.identity, "failed", error="recipient reached max_steps"
            )
        return self._result(
            request,
            runtime.identity,
            "failed",
            error="recipient did not produce a successful terminal response",
        )

    @staticmethod
    def _result(
        request: TaskRequest,
        identity: RuntimeIdentity,
        outcome: TaskOutcome,
        *,
        response: str | None = None,
        error: str | None = None,
    ) -> TaskResult:
        safe_response = sanitize_arguments(response) if response is not None else None
        safe_error = sanitize_arguments(error) if error is not None else None
        return TaskResult(
            task_id=request.task_id,
            caller_agent_id=request.caller_agent_id,
            recipient_agent_id=request.recipient_agent_id,
            parent_run_id=request.parent_run_id,
            parent_session_id=request.parent_session_id,
            child_run_id=identity.run_id,
            child_session_id=identity.session_id,
            outcome=outcome,
            response=safe_response,
            error=safe_error,
        )

    @staticmethod
    def _rejected(request: TaskRequest, reason: str) -> TaskResult:
        return TaskResult(
            task_id=request.task_id,
            caller_agent_id=request.caller_agent_id,
            recipient_agent_id=request.recipient_agent_id,
            parent_run_id=request.parent_run_id,
            parent_session_id=request.parent_session_id,
            outcome="rejected",
            error=reason,
        )

    @staticmethod
    def _persist_result(runtime: AgentRuntime | None, result: TaskResult) -> TaskResult:
        if runtime is not None:
            entries = runtime.session_store.load_entries()
            runtime.session_store.append_entry(
                CustomEntry(
                    parent_id=entries[-1].id if entries else None,
                    namespace="delegation",
                    data=result.model_dump(exclude_none=True),
                )
            )
        return result


__all__ = [
    "DelegationService",
    "MAX_DELEGATION_TIMEOUT",
    "TaskOutcome",
    "TaskRequest",
    "TaskResult",
]
