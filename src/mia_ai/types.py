"""Type definitions and models for LLM streaming and communication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"]
THINKING_LEVELS: tuple[ThinkingLevel, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


def reasoning_effort_for_level(
    level: str | None,
    level_map: Mapping[str, str | None] | None = None,
    *,
    minimal: str = "minimal",
    xhigh: str = "high",
) -> str | None:
    """Map Mia's general level to a provider's reasoning-effort value."""
    normalized = level or "off"
    if normalized == "off":
        return None
    if level_map and normalized in level_map:
        return level_map[normalized]
    return {"minimal": minimal, "xhigh": xhigh, "max": xhigh}.get(normalized, normalized)


def anthropic_thinking_budget_for_level(level: str | None) -> int | None:
    """Map a general reasoning level to Anthropic extended-thinking tokens."""
    normalized = level or "off"
    if normalized == "off":
        return None
    return {
        "minimal": 1_024,
        "low": 2_048,
        "medium": 8_192,
        "high": 16_384,
        "xhigh": 16_384,
        "max": 16_384,
    }.get(normalized, 4_096)


class ToolCall(BaseModel):
    """Represents a completed tool invocation emitted by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallDelta(BaseModel):
    """Represents an incremental fragment of a tool invocation during streaming."""

    index: int = 0
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


class TokenUsage(BaseModel):
    """Token accounting and optional cost metrics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


class StreamChunk(BaseModel):
    """Unified chunk yielded by any LLM stream."""

    type: Literal[
        "text_delta",
        "thought_delta",
        "tool_call_start",
        "tool_call_delta",
        "tool_call_end",
        "finish",
        "error",
    ]
    delta: str = ""
    thought: str = ""
    tool_call: ToolCall | None = None
    tool_call_delta: ToolCallDelta | None = None
    finish_reason: Literal["stop", "tool_calls", "length", "error"] | str | None = None
    usage: TokenUsage | None = None
    error: str | None = None


class ChatMessage(BaseModel):
    """Represents a single message in the conversation history."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class ToolDefinition(BaseModel):
    """Schema descriptor for tools provided to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]
