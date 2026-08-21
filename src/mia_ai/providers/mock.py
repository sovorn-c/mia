"""Deterministic Mock LLM Provider for offline testing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from mia_ai.providers.base import LLMProvider
from mia_ai.types import ChatMessage, StreamChunk, TokenUsage, ToolCall, ToolDefinition


class MockProvider(LLMProvider):
    """Replays pre-configured sequences of StreamChunks for deterministic tests."""

    def __init__(
        self,
        scripted_responses: Sequence[Sequence[StreamChunk]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._responses: list[list[StreamChunk]] = [
            list(resp) for resp in (scripted_responses or [])
        ]
        self.recorded_calls: list[dict[str, Any]] = []

    def queue_response(self, chunks: Sequence[StreamChunk]) -> None:
        """Add another response stream to the queue."""
        self._responses.append(list(chunks))

    def queue_text_response(
        self,
        text: str,
        thought: str = "",
        input_tokens: int = 10,
        output_tokens: int = 20,
    ) -> None:
        """Helper to queue a simple text response stream."""
        chunks: list[StreamChunk] = []
        if thought:
            chunks.append(StreamChunk(type="thought_delta", thought=thought))
        chunks.append(StreamChunk(type="text_delta", delta=text))
        chunks.append(
            StreamChunk(
                type="finish",
                finish_reason="stop",
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
            )
        )
        self.queue_response(chunks)

    def queue_tool_call_response(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str = "call_mock_1",
        pre_text: str = "",
        input_tokens: int = 15,
        output_tokens: int = 25,
    ) -> None:
        """Helper to queue a tool invocation turn."""
        chunks: list[StreamChunk] = []
        if pre_text:
            chunks.append(StreamChunk(type="text_delta", delta=pre_text))
        tool_call = ToolCall(id=call_id, name=tool_name, arguments=arguments)
        chunks.append(StreamChunk(type="tool_call_start", tool_call=tool_call))
        chunks.append(StreamChunk(type="tool_call_end", tool_call=tool_call))
        chunks.append(
            StreamChunk(
                type="finish",
                finish_reason="tool_calls",
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
            )
        )
        self.queue_response(chunks)

    def queue_tool_call(
        self,
        tool_call: ToolCall,
        thought: str = "",
        pre_text: str = "",
        input_tokens: int = 15,
        output_tokens: int = 25,
    ) -> None:
        """Helper to queue a tool invocation by ToolCall object."""
        chunks: list[StreamChunk] = []
        if thought:
            chunks.append(StreamChunk(type="thought_delta", thought=thought))
        if pre_text:
            chunks.append(StreamChunk(type="text_delta", delta=pre_text))
        chunks.append(StreamChunk(type="tool_call_start", tool_call=tool_call))
        chunks.append(StreamChunk(type="tool_call_end", tool_call=tool_call))
        chunks.append(
            StreamChunk(
                type="finish",
                finish_reason="tool_calls",
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
            )
        )
        self.queue_response(chunks)

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
        self.recorded_calls.append(
            {
                "model": model,
                "messages": [m.model_dump() for m in messages],
                "tools": [t.model_dump() for t in tools] if tools else None,
                "system": system,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if not self._responses:
            yield StreamChunk(
                type="finish",
                finish_reason="stop",
                usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )
            return

        stream = self._responses.pop(0)
        for chunk in stream:
            yield chunk
