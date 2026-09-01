"""Bounded, synchronous Agent-to-Agent Delegation."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from mia_agent.agents import AgentManager
from mia_agent.events import AgentErrorEvent, AssistantChunkEvent, TurnCompleteEvent
from mia_agent.orchestration import AgentRuntime, AgentRuntimeFactory, RuntimeIdentity
from mia_agent.session.entries import CustomEntry
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import compose_effective_access, sanitize_arguments

TaskOutcome = Literal["succeeded", "failed", "rejected", "cancelled", "timed-out"]
MAX_TASK_PROMPT_LENGTH = 20_000
MAX_DELEGATION_TIMEOUT = 300.0


class TaskRequest(BaseModel):
    """Validated bounded input to one direct Delegation call."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex}")
    caller_agent_id: str = Field(validation_alias=AliasChoices("caller_agent_id", "caller_id"))
    recipient_agent_id: str = Field(
        validation_alias=AliasChoices("recipient_agent_id", "recipient_id")
    )
    prompt: str = Field(
        validation_alias=AliasChoices("prompt", "task_prompt", "text"),
        min_length=1,
        max_length=MAX_TASK_PROMPT_LENGTH,
    )
    parent_run_id: str = "root"
    parent_session_id: str = "root"
    timeout: float = 60.0
    depth: int = 0

    @field_validator(
        "task_id", "caller_agent_id", "recipient_agent_id", "parent_run_id", "parent_session_id"
    )
    @classmethod
    def require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task identity fields must not be blank")
        return value

    @field_validator("prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task prompt must not be blank")
        return value

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 0 < value <= MAX_DELEGATION_TIMEOUT:
            raise ValueError(
                f"Task timeout must be greater than 0 and at most {MAX_DELEGATION_TIMEOUT:g}s"
            )
        return value

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, value: int) -> int:
        if value not in {0, 1}:
            raise ValueError("Delegation depth must be 0 or 1")
        return value

    @model_validator(mode="after")
    def reject_self_target(self) -> TaskRequest:
        if self.caller_agent_id.strip().lower() == self.recipient_agent_id.strip().lower():
            raise ValueError("An Agent cannot delegate a Task to itself")
        return self


class TaskResult(BaseModel):
    """Serializable, attributable terminal result for one Task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    caller_agent_id: str
    recipient_agent_id: str
    parent_run_id: str = "root"
    parent_session_id: str = "root"
    child_run_id: str = ""
    child_session_id: str = ""
    outcome: TaskOutcome
    response: str | None = None
    error: str | None = None

    @field_validator(
        "task_id",
        "caller_agent_id",
        "recipient_agent_id",
        "parent_run_id",
        "parent_session_id",
    )
    @classmethod
    def require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task result identity fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> TaskResult:
        if self.outcome == "succeeded":
            if not self.response or not self.response.strip():
                raise ValueError("Succeeded Task results require response content")
            if self.error is not None:
                raise ValueError("Succeeded Task results cannot carry an error")
        elif not self.error or not self.error.strip():
            raise ValueError(f"{self.outcome} Task results require terminal error context")
        return self


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
        child_identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id=request.task_id,
            agent_id=recipient.agent_id,
            session_id=f"session_{uuid.uuid4().hex[:12]}",
            parent_session_id=request.parent_session_id,
        )

        try:
            runtime = self.factory.build(
                identity=child_identity,
                provider=self.provider,
                access_policy_override=effective.access_level,
                capabilities_override=effective.capabilities,
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
            async for event in runtime.harness.prompt(request.prompt):
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
