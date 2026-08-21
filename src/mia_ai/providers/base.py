"""Abstract base class and protocol for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from mia_ai.types import ChatMessage, StreamChunk, TokenUsage, ToolCall, ToolDefinition


class LLMProvider(ABC):
    """Base class for all multi-provider LLM adapters."""

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, **kwargs: Any
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.extra_config = kwargs

    @abstractmethod
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
        """Stream response chunks from the LLM."""
        yield  # type: ignore[misc]

    async def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> tuple[str, list[ToolCall], TokenUsage]:
        """Non-streaming convenience helper that consumes stream to completion."""
        accumulated_text: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = TokenUsage()

        async for chunk in self.stream(
            model=model,
            messages=messages,
            tools=tools,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.type == "text_delta":
                accumulated_text.append(chunk.delta)
            elif chunk.type == "tool_call_end" and chunk.tool_call:
                tool_calls.append(chunk.tool_call)
            elif chunk.type == "finish" and chunk.usage:
                usage = chunk.usage

        return "".join(accumulated_text), tool_calls, usage
