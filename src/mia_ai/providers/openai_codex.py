"""OpenAI Codex subscription Responses API provider."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.auth.openai_auth import (
    OPENAI_CODEX_PROVIDER,
    OpenAIOAuthManager,
    account_id_from_access_token,
    oauth_credential_is_expired,
)
from mia_ai.providers.base import LLMProvider
from mia_ai.types import (
    ChatMessage,
    StreamChunk,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api"


class OpenAICodexProvider(LLMProvider):
    """Stream ChatGPT subscription responses using a Codex OAuth credential."""

    def __init__(
        self,
        *,
        credential_store: FileCredentialStore | None = None,
        base_url: str = DEFAULT_CODEX_BASE_URL,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(base_url=base_url)
        self.credential_store = credential_store or FileCredentialStore()
        self.timeout = timeout
        self.client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self.client is not None and self._owns_client:
            await self.client.aclose()
            self.client = None

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
        del temperature, max_tokens
        try:
            access_token, account_id = await self._resolve_credentials()
            payload = _build_payload(model, messages, tools or [], system or "")
            headers = {
                "Authorization": f"Bearer {access_token}",
                "chatgpt-account-id": account_id,
                "originator": "tau",
                "User-Agent": "tau",
                "OpenAI-Beta": "responses=experimental",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            }
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{(self.base_url or DEFAULT_CODEX_BASE_URL).rstrip('/')}/codex/responses",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    yield StreamChunk(
                        type="error",
                        error=f"OpenAI Codex request failed (HTTP {response.status_code}): {body[:1000]}",
                    )
                    return
                async for chunk in _read_events(response):
                    yield chunk
        except Exception as exc:  # provider failures are surfaced to the harness
            yield StreamChunk(type="error", error=str(exc))

    async def _resolve_credentials(self) -> tuple[str, str]:
        credential = self.credential_store.get_oauth(OPENAI_CODEX_PROVIDER)
        if credential is not None:
            if oauth_credential_is_expired(credential):
                if not credential.refresh:
                    raise RuntimeError("OpenAI Codex access token expired; run /login oauth again")
                credential = await asyncio.to_thread(
                    OpenAIOAuthManager(self.credential_store).refresh_token,
                    credential.refresh,
                )
                self.credential_store.set_oauth(OPENAI_CODEX_PROVIDER, credential)
            account_id = credential.account_id or account_id_from_access_token(credential.access)
            if account_id:
                return credential.access, account_id

        raise RuntimeError("Missing OpenAI Codex OAuth credentials; run /login oauth")

    def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        return self.client


async def _read_events(response: httpx.Response) -> AsyncIterator[StreamChunk]:
    buffers: list[str] = []
    tool_calls: dict[str, dict[str, Any]] = {}
    tool_indexes: dict[int, str] = {}
    usage = TokenUsage()
    finished = False

    async for line in response.aiter_lines():
        line = line.strip()
        if line:
            if line.startswith("data:"):
                data = line[5:].strip()
                if data != "[DONE]":
                    buffers.append(data)
            continue
        if buffers:
            event = _parse_event("\n".join(buffers))
            buffers = []
            if event is not None:
                async for chunk in _event_chunks(event, tool_calls, tool_indexes, usage):
                    if chunk.type == "finish":
                        finished = True
                    yield chunk

    if buffers:
        event = _parse_event("\n".join(buffers))
        if event is not None:
            async for chunk in _event_chunks(event, tool_calls, tool_indexes, usage):
                if chunk.type == "finish":
                    finished = True
                yield chunk
    if not finished:
        yield StreamChunk(type="finish", finish_reason="stop", usage=usage)


async def _event_chunks(
    event: dict[str, Any],
    tool_calls: dict[str, dict[str, Any]],
    tool_indexes: dict[int, str],
    usage: TokenUsage,
) -> AsyncIterator[StreamChunk]:
    event_type = event.get("type")
    if event_type in {"error", "response.failed"}:
        error = event.get("error")
        if isinstance(error, dict):
            error = error.get("message") or error.get("code")
        yield StreamChunk(type="error", error=str(error or "OpenAI Codex request failed"))
        return

    if event_type == "response.output_text.delta":
        delta = event.get("delta")
        if isinstance(delta, str):
            yield StreamChunk(type="text_delta", delta=delta)
        return

    if event_type in {
        "response.reasoning.delta",
        "response.reasoning_summary_text.delta",
        "response.reasoning_text.delta",
    }:
        delta = event.get("delta")
        if isinstance(delta, str):
            yield StreamChunk(type="thought_delta", thought=delta)
        return

    item = event.get("item")
    if event_type == "response.output_item.added" and isinstance(item, dict):
        if item.get("type") == "function_call":
            call_id = str(item.get("call_id") or item.get("id") or f"call_{len(tool_calls)}")
            output_index = event.get("output_index")
            if isinstance(output_index, int):
                tool_indexes[output_index] = call_id
            tool_calls[call_id] = {
                "id": call_id,
                "name": str(item.get("name") or ""),
                "arguments": "",
            }
            yield StreamChunk(
                type="tool_call_start",
                tool_call_delta=ToolCallDelta(
                    index=output_index if isinstance(output_index, int) else len(tool_calls) - 1,
                    id=call_id,
                    name=tool_calls[call_id]["name"],
                ),
            )
        return

    if event_type == "response.function_call_arguments.delta":
        delta_call_id = _resolve_call_id(event, tool_indexes)
        delta = event.get("delta")
        if delta_call_id and isinstance(delta, str):
            tool_calls.setdefault(
                delta_call_id, {"id": delta_call_id, "name": "", "arguments": ""}
            )["arguments"] += delta
            yield StreamChunk(
                type="tool_call_delta",
                tool_call_delta=ToolCallDelta(
                    index=_tool_index(delta_call_id, tool_indexes), arguments_delta=delta
                ),
            )
        return

    if event_type in {"response.output_item.done", "response.output_item.completed"}:
        if isinstance(item, dict) and item.get("type") == "function_call":
            call_id = _resolve_call_id(event, tool_indexes) or str(
                item.get("call_id") or item.get("id") or "call_0"
            )
            current = tool_calls.setdefault(call_id, {"id": call_id, "name": "", "arguments": ""})
            current["name"] = str(item.get("name") or current["name"])
            current["arguments"] = str(item.get("arguments") or current["arguments"])
            try:
                arguments = json.loads(current["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw_arguments": current["arguments"]}
            if not isinstance(arguments, dict):
                arguments = {"_raw_arguments": arguments}
            yield StreamChunk(
                type="tool_call_end",
                tool_call=ToolCall(id=call_id, name=current["name"], arguments=arguments),
            )
        elif isinstance(item, dict) and item.get("type") == "message":
            text = _text_from_message(item)
            if text:
                yield StreamChunk(type="text_delta", delta=text)
        return

    if event_type in {"response.done", "response.completed", "response.incomplete"}:
        response = event.get("response")
        if isinstance(response, dict):
            response_usage = response.get("usage")
            if isinstance(response_usage, dict):
                usage.input_tokens = int(response_usage.get("input_tokens", 0) or 0)
                usage.output_tokens = int(response_usage.get("output_tokens", 0) or 0)
                usage.total_tokens = int(
                    response_usage.get("total_tokens", usage.input_tokens + usage.output_tokens)
                    or 0
                )
            reason = response.get("status") or "stop"
        else:
            reason = "stop"
        yield StreamChunk(type="finish", finish_reason=str(reason), usage=usage)


def _build_payload(
    model: str, messages: list[ChatMessage], tools: list[ToolDefinition], system: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "store": False,
        "stream": True,
        "instructions": system or "You are a helpful assistant.",
        "input": _messages_to_input(messages),
        "text": {"verbosity": "low"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": None,
            }
            for tool in tools
        ]
    return payload


def _messages_to_input(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    assistant_index = 0
    for message in messages:
        content = (
            message.content if isinstance(message.content, str) else json.dumps(message.content)
        )
        if message.role == "user":
            items.append({"role": "user", "content": [{"type": "input_text", "text": content}]})
        elif message.role == "assistant":
            if content:
                items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content, "annotations": []}],
                        "status": "completed",
                        "id": f"msg_{assistant_index}",
                    }
                )
                assistant_index += 1
            for call in message.tool_calls or []:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                )
        elif message.role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id or "",
                    "output": content,
                }
            )
    return items


def _parse_event(data: str) -> dict[str, Any] | None:
    try:
        event = json.loads(data)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _resolve_call_id(event: dict[str, Any], tool_indexes: dict[int, str]) -> str | None:
    output_index = event.get("output_index")
    if isinstance(output_index, int) and output_index in tool_indexes:
        return tool_indexes[output_index]
    call_id = event.get("call_id")
    if isinstance(call_id, str) and call_id:
        return call_id
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("call_id", "id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    item_id = event.get("item_id")
    return item_id if isinstance(item_id, str) and item_id else None


def _tool_index(call_id: str, tool_indexes: dict[int, str]) -> int:
    return next((index for index, value in tool_indexes.items() if value == call_id), 0)


def _text_from_message(item: dict[str, Any]) -> str:
    parts: list[str] = []
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    for part in content:
        if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)
