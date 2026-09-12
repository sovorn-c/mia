from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx
import pytest

from mia_agent.auth.credentials import FileCredentialStore, OAuthCredential
from mia_ai.providers.openai_codex import OpenAICodexProvider
from mia_ai.types import ChatMessage, ToolDefinition


def _jwt() -> str:
    payload = {
        "exp": int(time.time()) + 3600,
        "https://api.openai.com/auth": {"chatgpt_account_id": "acct_test"},
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


@pytest.mark.asyncio
async def test_codex_provider_uses_responses_endpoint_and_streams_events(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    sse = b"""data: {\"type\":\"response.output_text.delta\",\"delta\":\"hello\"}\n\ndata: {\"type\":\"response.completed\",\"response\":{\"status\":\"completed\",\"usage\":{\"input_tokens\":2,\"output_tokens\":1,\"total_tokens\":3}}}\n\n"""

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set_oauth(
        "openai-codex",
        OAuthCredential(
            access=_jwt(),
            refresh="refresh",
            expires=int(time.time() * 1000) + 3600_000,
            account_id="acct_test",
        ),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICodexProvider(credential_store=store, client=client)

    chunks = [
        chunk
        async for chunk in provider.stream(
            model="gpt-5.3-codex",
            system="Be concise.",
            messages=[ChatMessage(role="user", content="Hi")],
            tools=[
                ToolDefinition(
                    name="read", description="Read a file", parameters={"type": "object"}
                )
            ],
        )
    ]
    await client.aclose()

    assert requests[0].url == "https://chatgpt.com/backend-api/codex/responses"
    assert requests[0].headers["chatgpt-account-id"] == "acct_test"
    payload = json.loads(requests[0].content)
    assert payload["instructions"] == "Be concise."
    assert payload["input"][0]["role"] == "user"
    assert payload["tools"][0]["name"] == "read"
    assert [chunk.type for chunk in chunks] == ["text_delta", "finish"]
    assert chunks[0].delta == "hello"
    assert chunks[1].usage is not None
    assert chunks[1].usage.total_tokens == 3


@pytest.mark.asyncio
async def test_codex_provider_reconstructs_function_call_by_output_index(tmp_path: Path) -> None:
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "function_call", "call_id": "call_1", "name": "read"},
        },
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "delta": '{"path":"x"}',
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "read",
                "arguments": '{"path":"x"}',
            },
        },
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    sse = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set_oauth(
        "openai-codex",
        OAuthCredential(
            access=_jwt(),
            refresh="refresh",
            expires=int(time.time() * 1000) + 3600_000,
            account_id="acct_test",
        ),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICodexProvider(credential_store=store, client=client)
    chunks = [
        chunk
        async for chunk in provider.stream(
            model="gpt-5.3-codex",
            messages=[ChatMessage(role="user", content="Read x")],
        )
    ]
    await client.aclose()

    tool_end = next(chunk for chunk in chunks if chunk.type == "tool_call_end")
    assert tool_end.tool_call is not None
    assert tool_end.tool_call.name == "read"
    assert tool_end.tool_call.arguments == {"path": "x"}
