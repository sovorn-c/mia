"""Tests for AI streaming providers and chunk parsers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.mock import MockProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_ai.types import ChatMessage, TokenUsage


@pytest.mark.asyncio
async def test_mock_provider_text_streaming() -> None:
    provider = MockProvider()
    provider.queue_text_response(
        "Hello from Mia!", thought="Thinking...", input_tokens=5, output_tokens=10
    )

    messages = [ChatMessage(role="user", content="Hi")]
    chunks = [c async for c in provider.stream(model="mock-model", messages=messages)]

    assert len(chunks) == 3
    assert chunks[0].type == "thought_delta"
    assert chunks[0].thought == "Thinking..."
    assert chunks[1].type == "text_delta"
    assert chunks[1].delta == "Hello from Mia!"
    assert chunks[2].type == "finish"
    assert chunks[2].finish_reason == "stop"
    assert chunks[2].usage is not None
    assert chunks[2].usage.input_tokens == 5
    assert chunks[2].usage.output_tokens == 10
    assert chunks[2].usage.total_tokens == 15

    assert len(provider.recorded_calls) == 1
    assert provider.recorded_calls[0]["model"] == "mock-model"


@pytest.mark.asyncio
async def test_mock_provider_complete_helper() -> None:
    provider = MockProvider()
    provider.queue_tool_call_response(
        tool_name="read_file",
        arguments={"path": "README.md"},
        call_id="call_123",
        pre_text="I will read the file.",
        input_tokens=12,
        output_tokens=18,
    )

    text, tool_calls, usage = await provider.complete(
        model="mock-model",
        messages=[ChatMessage(role="user", content="Read README.md")],
    )

    assert text == "I will read the file."
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_123"
    assert tool_calls[0].name == "read_file"
    assert tool_calls[0].arguments == {"path": "README.md"}
    assert usage.input_tokens == 12
    assert usage.output_tokens == 18


@pytest.mark.asyncio
async def test_token_usage_addition() -> None:
    u1 = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150, cost_usd=0.01)
    u2 = TokenUsage(input_tokens=200, output_tokens=80, total_tokens=280, cost_usd=0.02)
    u3 = u1.add(u2)

    assert u3.input_tokens == 300
    assert u3.output_tokens == 130
    assert u3.total_tokens == 430
    assert pytest.approx(u3.cost_usd) == 0.03


@pytest.mark.asyncio
async def test_openai_compatible_streaming() -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://mock.openai.com/v1")

    # Simulate SSE lines
    sse_lines = [
        b'data: {"choices": [{"delta": {"reasoning_content": "Thinking about math"}, "finish_reason": null}]}',
        b'data: {"choices": [{"delta": {"content": "2 + 2 = "}, "finish_reason": null}]}',
        b'data: {"choices": [{"delta": {"content": "4"}, "finish_reason": null}]}',
        b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}',
        b"data: [DONE]",
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line.decode("utf-8")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = mock_aiter_lines

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def stream(self, *args, **kwargs):
            return MockStreamContext()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    with patch("httpx.AsyncClient", return_value=MockClient()):
        chunks = [
            c
            async for c in provider.stream(
                model="gpt-4o",
                messages=[ChatMessage(role="user", content="What is 2+2?")],
            )
        ]

    assert len(chunks) == 4
    assert chunks[0].type == "thought_delta"
    assert chunks[0].thought == "Thinking about math"
    assert chunks[1].type == "text_delta"
    assert chunks[1].delta == "2 + 2 = "
    assert chunks[2].type == "text_delta"
    assert chunks[2].delta == "4"
    assert chunks[3].type == "finish"
    assert chunks[3].finish_reason == "stop"
    assert chunks[3].usage is not None
    assert chunks[3].usage.total_tokens == 15


@pytest.mark.asyncio
async def test_anthropic_streaming() -> None:
    provider = AnthropicProvider(api_key="test-key")

    sse_lines = [
        "event: message_start\n",
        'data: {"type": "message_start", "message": {"id": "msg_123", "usage": {"input_tokens": 25}}}\n',
        "event: content_block_start\n",
        'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}\n',
        "event: content_block_delta\n",
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello world"}}\n',
        "event: content_block_stop\n",
        'data: {"type": "content_block_stop", "index": 0}\n',
        "event: message_delta\n",
        'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 15}}\n',
        "event: message_stop\n",
        'data: {"type": "message_stop"}\n',
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = mock_aiter_lines

    class MockStreamContext:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def stream(self, *args, **kwargs):
            return MockStreamContext()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    with patch("httpx.AsyncClient", return_value=MockClient()):
        chunks = [
            c
            async for c in provider.stream(
                model="claude-3-5-sonnet",
                messages=[ChatMessage(role="user", content="Hello")],
            )
        ]

    assert len(chunks) == 2
    assert chunks[0].type == "text_delta"
    assert chunks[0].delta == "Hello world"
    assert chunks[1].type == "finish"
    assert chunks[1].finish_reason == "end_turn"
    assert chunks[1].usage is not None
    assert chunks[1].usage.input_tokens == 25
    assert chunks[1].usage.output_tokens == 15
