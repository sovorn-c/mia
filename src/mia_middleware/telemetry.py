"""Telemetry, auditing, and cost quota enforcement middlewares."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from mia_middleware.access import sanitize_arguments
from mia_middleware.pipeline import ToolCallContext


class BudgetExceededError(RuntimeError):
    """Raised when execution limits (cost/turns) are exceeded."""


class AuditLogRecord(BaseModel):
    """Structured, attributed, secret-free telemetry record for Tool execution."""

    session_id: str
    step_index: int
    tool_name: str
    plugin_id: str | None = None
    agent_id: str = ""
    run_id: str = ""
    task_id: str = ""
    arguments: dict[str, Any]
    duration_ms: float
    is_error: bool = False
    error_message: str | None = None
    timestamp: float = Field(default_factory=time.time)


class CostBudgetMiddleware:
    """Enforces execution and cost budgets across tool invocations."""

    def __init__(
        self,
        max_tool_calls_per_turn: int = 50,
        max_cost_usd: float | None = None,
    ) -> None:
        self.max_tool_calls_per_turn = max_tool_calls_per_turn
        self.max_cost_usd = max_cost_usd
        self._tool_calls_count = 0
        self._current_cost_usd = 0.0

    @property
    def tool_calls_count(self) -> int:
        return self._tool_calls_count

    def add_cost(self, cost_usd: float) -> None:
        self._current_cost_usd += cost_usd

    async def __call__(
        self,
        ctx: ToolCallContext,
        next_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        self._tool_calls_count += 1

        if self._tool_calls_count > self.max_tool_calls_per_turn:
            raise BudgetExceededError(
                f"Budget Exceeded: Tool call limit of {self.max_tool_calls_per_turn} reached for turn."
            )

        if self.max_cost_usd is not None and self._current_cost_usd >= self.max_cost_usd:
            raise BudgetExceededError(
                f"Budget Exceeded: Cost limit of ${self.max_cost_usd:.4f} reached (Current: ${self._current_cost_usd:.4f})."
            )

        return await next_fn()


class AuditLogMiddleware:
    """Records structured audit records for all tool executions."""

    def __init__(self, callback: Callable[[AuditLogRecord], None] | None = None) -> None:
        self.logs: list[AuditLogRecord] = []
        self.callback = callback

    async def __call__(
        self,
        ctx: ToolCallContext,
        next_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        start_time = time.perf_counter()
        is_error = False
        err_msg: str | None = None

        try:
            result = await next_fn()
            return result
        except Exception as exc:
            is_error = True
            err_msg = str(sanitize_arguments(str(exc)))
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            record = AuditLogRecord(
                session_id=ctx.session_id,
                step_index=ctx.step_index,
                tool_name=ctx.tool_name,
                plugin_id=ctx.plugin_id or str(ctx.metadata.get("plugin_id", "")) or None,
                arguments=sanitize_arguments(ctx.arguments),
                duration_ms=duration_ms,
                agent_id=str(ctx.metadata.get("agent_id", "")),
                run_id=str(ctx.metadata.get("run_id", "")),
                task_id=str(ctx.metadata.get("task_id", "")),
                is_error=is_error,
                error_message=err_msg,
            )
            self.logs.append(record)
            if self.callback:
                self.callback(record)
