"""Onion-style middleware execution pipeline for tool invocations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field


class ToolCallContext(BaseModel):
    """Context object carried through the middleware chain."""

    session_id: str = "default"
    step_index: int = 1
    call_id: str = ""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Signature: (Context, NextCallable) -> Awaitable[Any]
ToolMiddleware = Callable[
    [ToolCallContext, Callable[[], Awaitable[Any]]],
    Awaitable[Any],
]


class ToolPipeline:
    """Async onion pipeline runner executing middlewares in registration order."""

    def __init__(self, middlewares: list[ToolMiddleware] | None = None) -> None:
        self.middlewares: list[ToolMiddleware] = list(middlewares or [])

    def use(self, middleware: ToolMiddleware) -> ToolPipeline:
        """Register a middleware at the end of the pipeline chain."""
        self.middlewares.append(middleware)
        return self

    async def execute(
        self,
        ctx: ToolCallContext,
        core_executor: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Execute the middleware chain wrapping the core tool executor."""

        async def dispatch(index: int) -> Any:
            if index < len(self.middlewares):
                middleware = self.middlewares[index]
                return await middleware(ctx, lambda: dispatch(index + 1))
            res = core_executor()
            if hasattr(res, "__await__"):
                return await res
            return res

        return await dispatch(0)
