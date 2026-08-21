"""OpenAI and OpenAI-compatible SSE streaming provider."""

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


class OpenAICompatibleProvider(LLMProvider):
    """Adapter for OpenAI, DeepSeek, vLLM, Ollama, and OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = "https://api.openai.com/v1",
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            api_key=api_key, base_url=base_url or "https://api.openai.com/v1", **kwargs
        )
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
        if system:
            formatted_messages.append({"role": "system", "content": system})

        for msg in messages:
            item: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict)
                            else str(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            if msg.tool_name:
                item["name"] = msg.tool_name
            formatted_messages.append(item)

        payload: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }

        base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base}/chat/completions"
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        usage = TokenUsage()

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

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        raw_data = line[len("data:") :].strip()
                        if raw_data == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(raw_data)
                        except json.JSONDecodeError:
                            continue

                        if "usage" in chunk_data and chunk_data["usage"]:
                            u = chunk_data["usage"]
                            usage.input_tokens = u.get("prompt_tokens", usage.input_tokens)
                            usage.output_tokens = u.get("completion_tokens", usage.output_tokens)
                            usage.total_tokens = u.get("total_tokens", usage.total_tokens)

                        choices = chunk_data.get("choices", [])
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})

                        # 1. Reasoning / Thinking content (e.g. DeepSeek-R1 / MiMo / OpenAI o-series)
                        thought = (
                            delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or delta.get("thought")
                        )
                        if thought:
                            yield StreamChunk(type="thought_delta", thought=thought)

                        # 2. Text delta
                        content = delta.get("content")
                        if content:
                            yield StreamChunk(type="text_delta", delta=content)

                        # 3. Tool call streaming
                        raw_tool_calls = delta.get("tool_calls", [])
                        for tc_delta in raw_tool_calls:
                            idx = tc_delta.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc_delta.get("id", f"call_{idx}"),
                                    "name": "",
                                    "arguments": "",
                                }
                                yield StreamChunk(
                                    type="tool_call_start",
                                    tool_call_delta=ToolCallDelta(
                                        index=idx,
                                        id=tool_call_buffers[idx]["id"],
                                        name=tool_call_buffers[idx]["name"],
                                    ),
                                )

                            buf = tool_call_buffers[idx]
                            if tc_delta.get("id"):
                                buf["id"] = tc_delta["id"]

                            func = tc_delta.get("function", {})
                            if func.get("name"):
                                buf["name"] += func["name"]
                            if func.get("arguments"):
                                arg_delta = func["arguments"]
                                buf["arguments"] += arg_delta
                                yield StreamChunk(
                                    type="tool_call_delta",
                                    tool_call_delta=ToolCallDelta(
                                        index=idx,
                                        arguments_delta=arg_delta,
                                    ),
                                )

                        finish_reason = choice.get("finish_reason")
                        if finish_reason:
                            # Emit completed tool calls
                            for _idx, buf in sorted(tool_call_buffers.items()):
                                try:
                                    parsed_args = (
                                        json.loads(buf["arguments"]) if buf["arguments"] else {}
                                    )
                                except json.JSONDecodeError:
                                    parsed_args = {"raw": buf["arguments"]}

                                completed_tc = ToolCall(
                                    id=buf["id"],
                                    name=buf["name"],
                                    arguments=parsed_args,
                                )
                                yield StreamChunk(
                                    type="tool_call_end",
                                    tool_call=completed_tc,
                                )
                            tool_call_buffers.clear()

                            yield StreamChunk(
                                type="finish",
                                finish_reason=finish_reason,
                                usage=usage,
                            )
        except Exception as exc:
            yield StreamChunk(type="error", error=str(exc))
