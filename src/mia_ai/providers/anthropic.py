"""Anthropic Claude SSE streaming provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from mia_ai.providers.base import LLMProvider
from mia_ai.types import (
    ChatMessage,
    StreamChunk,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic Messages streaming API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = "https://api.anthropic.com/v1",
        anthropic_version: str = "2023-06-01",
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            api_key=api_key, base_url=base_url or "https://api.anthropic.com/v1", **kwargs
        )
        self.anthropic_version = anthropic_version
        self.timeout = timeout

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
        formatted_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "tool":
                formatted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content
                                if isinstance(msg.content, str)
                                else json.dumps(msg.content),
                            }
                        ],
                    }
                )
            elif msg.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.name,
                                "input": tc.arguments,
                            }
                        )
                formatted_messages.append({"role": "assistant", "content": blocks or msg.content})
            elif msg.role == "user":
                formatted_messages.append({"role": "user", "content": msg.content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "stream": True,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": self.anthropic_version,
        }

        base = (self.base_url or "https://api.anthropic.com/v1").rstrip("/")
        url = f"{base}/messages"
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        usage = TokenUsage()
        finish_reason: str = "stop"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        yield StreamChunk(
                            type="error",
                            error=f"HTTP {response.status_code}: {body.decode('utf-8', errors='replace')}",
                        )
                        return

                    current_event_type = ""
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            current_event_type = line[len("event:") :].strip()
                            continue

                        if not line.startswith("data:"):
                            continue

                        raw_data = line[len("data:") :].strip()
                        try:
                            data = json.loads(raw_data)
                        except json.JSONDecodeError:
                            continue

                        if current_event_type == "message_start":
                            msg_meta = data.get("message", {})
                            u = msg_meta.get("usage", {})
                            usage.input_tokens = u.get("input_tokens", usage.input_tokens)

                        elif current_event_type == "content_block_start":
                            idx = data.get("index", 0)
                            cb = data.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_call_buffers[idx] = {
                                    "id": cb.get("id", f"call_{idx}"),
                                    "name": cb.get("name", ""),
                                    "arguments": "",
                                }
                                yield StreamChunk(
                                    type="tool_call_start",
                                    tool_call_delta=ToolCallDelta(
                                        index=idx,
                                        id=cb.get("id"),
                                        name=cb.get("name"),
                                    ),
                                )

                        elif current_event_type == "content_block_delta":
                            idx = data.get("index", 0)
                            delta = data.get("delta", {})
                            delta_type = delta.get("type")

                            if delta_type == "text_delta":
                                text = delta.get("text", "")
                                yield StreamChunk(type="text_delta", delta=text)

                            elif delta_type == "thinking_delta":
                                thought = delta.get("thinking", "")
                                yield StreamChunk(type="thought_delta", thought=thought)

                            elif delta_type == "input_json_delta":
                                partial_json = delta.get("partial_json", "")
                                if idx in tool_call_buffers:
                                    tool_call_buffers[idx]["arguments"] += partial_json
                                yield StreamChunk(
                                    type="tool_call_delta",
                                    tool_call_delta=ToolCallDelta(
                                        index=idx,
                                        arguments_delta=partial_json,
                                    ),
                                )

                        elif current_event_type == "content_block_stop":
                            idx = data.get("index", 0)
                            if idx in tool_call_buffers:
                                buf = tool_call_buffers[idx]
                                try:
                                    parsed = (
                                        json.loads(buf["arguments"]) if buf["arguments"] else {}
                                    )
                                except json.JSONDecodeError:
                                    parsed = {"raw": buf["arguments"]}
                                tc = ToolCall(id=buf["id"], name=buf["name"], arguments=parsed)
                                yield StreamChunk(type="tool_call_end", tool_call=tc)

                        elif current_event_type == "message_delta":
                            d = data.get("delta", {})
                            stop_r = d.get("stop_reason")
                            if stop_r == "tool_use":
                                finish_reason = "tool_calls"
                            elif stop_r:
                                finish_reason = stop_r

                            u = data.get("usage", {})
                            usage.output_tokens = u.get("output_tokens", usage.output_tokens)
                            usage.total_tokens = usage.input_tokens + usage.output_tokens

                        elif current_event_type == "message_stop":
                            yield StreamChunk(
                                type="finish",
                                finish_reason=finish_reason,
                                usage=usage,
                            )
        except Exception as exc:
            yield StreamChunk(type="error", error=str(exc))
