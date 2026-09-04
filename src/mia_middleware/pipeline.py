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
    plugin_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Signature: (Context, NextCallable) -> Awaitable[Any]
ToolMiddleware = Callable[
    [ToolCallContext, Callable[[], Awaitable[Any]]],
    Awaitable[Any],
]


class ToolPipeline:
    """Async onion pipeline runner executing middlewares in registration order."""

    def __init__(
        self,
        middlewares: list[ToolMiddleware] | None = None,
        final_validator: Callable[[ToolCallContext], Awaitable[None] | None] | None = None,
    ) -> None:
        self.middlewares: list[ToolMiddleware] = list(middlewares or [])
        self.final_validator = final_validator

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
        initial_tool_name = ctx.tool_name
        initial_plugin_id = ctx.plugin_id

        execution_count = 0
        core_rejection: BaseException | None = None

        async def dispatch(index: int) -> Any:
            nonlocal execution_count, core_rejection
            if index < len(self.middlewares):
                middleware = self.middlewares[index]
                return await middleware(ctx, lambda: dispatch(index + 1))

            # Final Core Gate right before executor
            if execution_count > 0:
                core_rejection = RuntimeError(
                    "Core tool executor cannot be invoked more than once for a single tool call"
                )
                raise core_rejection

            if ctx.tool_name != initial_tool_name:
                core_rejection = ValueError(
                    f"Tool identity cannot be modified: requested '{initial_tool_name}', got '{ctx.tool_name}'"
                )
                raise core_rejection

            if ctx.plugin_id != initial_plugin_id:
                core_rejection = ValueError("Tool attribution cannot be modified")
                raise core_rejection

            if self.final_validator is not None:
                try:
                    val_res = self.final_validator(ctx)
                    if val_res is not None:
                        await val_res
                except BaseException as exc:
                    core_rejection = exc
                    raise

            execution_count += 1
            try:
                res = core_executor()
                if hasattr(res, "__await__"):
                    return await res
                return res
            except BaseException as exc:
                core_rejection = exc
                raise

        try:
            result = await dispatch(0)
        except BaseException as exc:
            if core_rejection is not None:
                raise core_rejection from exc
            raise

        if core_rejection is not None:
            raise core_rejection

        if execution_count == 0:
            raise RuntimeError(
                "Tool execution was bypassed: middleware cannot fabricate success without Core execution"
            )

        return result
