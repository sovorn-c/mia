"""Immutable event domain models emitted by the headless agent loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BaseAgentEvent(BaseModel):
    """Root model for all events with UTC timestamp."""

    timestamp: datetime = Field(default_factory=_utc_now)


class TurnStartEvent(BaseAgentEvent):
    """Emitted when a new user turn begins."""

    type: Literal["turn_start"] = "turn_start"
    turn_index: int = 0
    user_prompt: str = ""


class StepStartEvent(BaseAgentEvent):
    """Emitted at the beginning of each step (LLM interaction)."""

    type: Literal["step_start"] = "step_start"
    step_index: int


class AssistantChunkEvent(BaseAgentEvent):
    """Emitted as the LLM streams text or reasoning."""

    type: Literal["assistant_chunk"] = "assistant_chunk"
    delta_text: str = ""
    thought_delta: str | None = None


class ToolCallEvent(BaseAgentEvent):
    """Emitted when the LLM requests a tool execution."""

    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    plugin_id: str | None = None


class ToolResultEvent(BaseAgentEvent):
    """Emitted when a tool finishes execution."""

    type: Literal["tool_result"] = "tool_result"
    call_id: str
    tool_name: str
    output: Any
    is_error: bool = False
    duration_ms: float = 0.0
    plugin_id: str | None = None


class StepEndEvent(BaseAgentEvent):
    """Emitted when a step completes with token usage statistics."""

    type: Literal["step_end"] = "step_end"
    step_index: int
    input_tokens: int = 0
    output_tokens: int = 0


class TurnCompleteEvent(BaseAgentEvent):
    """Emitted when the agent finishes answering the turn."""

    type: Literal["turn_complete"] = "turn_complete"
    total_steps: int
    total_cost_usd: float = 0.0
    stop_reason: Literal["stop", "tool_calls", "max_steps", "error"] | str = "stop"


class AgentErrorEvent(BaseAgentEvent):
    """Emitted when an unhandled error occurs during turn execution."""

    type: Literal["agent_error"] = "agent_error"
    error: str
    step_index: int | None = None


AgentEvent = Annotated[
    TurnStartEvent
    | StepStartEvent
    | AssistantChunkEvent
    | ToolCallEvent
    | ToolResultEvent
    | StepEndEvent
    | TurnCompleteEvent
    | AgentErrorEvent,
    Field(discriminator="type"),
]
