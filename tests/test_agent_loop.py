"""Tests for AgentHarness loop, turn events, and step safeguards."""

from __future__ import annotations

import pytest

from mia_agent.harness import AgentHarness
from mia_ai.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_single_turn_text_response() -> None:
    mock = MockProvider()
    mock.queue_text_response(
        "Here is the answer!", thought="Thinking...", input_tokens=10, output_tokens=5
    )

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        system_prompt="Test system prompt",
    )

    events = [event async for event in harness.prompt("Hello Mia")]

    event_types = [e.type for e in events]
    assert event_types == [
        "turn_start",
        "step_start",
        "assistant_chunk",  # thought
        "assistant_chunk",  # text
        "step_end",
        "turn_complete",
    ]

    turn_start = events[0]
    assert turn_start.user_prompt == "Hello Mia"

    turn_complete = events[-1]
    assert turn_complete.total_steps == 1
    assert turn_complete.stop_reason == "stop"

    # Verify history in harness
    assert len(harness.messages) == 2
    assert harness.messages[0].role == "user"
    assert harness.messages[1].role == "assistant"
    assert harness.messages[1].content == "Here is the answer!"


@pytest.mark.asyncio
async def test_multi_step_tool_turn() -> None:
    mock = MockProvider()
    # Step 1: LLM issues a tool call
    mock.queue_tool_call_response(
        tool_name="read_file",
        arguments={"path": "main.py"},
        call_id="call_read_1",
        pre_text="Let me inspect main.py.",
        input_tokens=20,
        output_tokens=10,
    )
    # Step 2: LLM summarizes the tool output
    mock.queue_text_response(
        "The file contains main().",
        input_tokens=30,
        output_tokens=15,
    )

    class MockReadTool:
        name = "read_file"
        description = "Reads a file"
        parameters = {"type": "object", "properties": {"path": {"type": "string"}}}

        def execute(self, path: str) -> str:
            return "1: def main(): pass"

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        tools=[MockReadTool()],
    )

    events = [e async for e in harness.prompt("Check main.py")]

    event_types = [e.type for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types

    # Find tool call and result
    tool_call_event = next(e for e in events if e.type == "tool_call")
    assert tool_call_event.tool_name == "read_file"
    assert tool_call_event.arguments == {"path": "main.py"}

    tool_result_event = next(e for e in events if e.type == "tool_result")
    assert tool_result_event.output == "1: def main(): pass"
    assert tool_result_event.is_error is False

    turn_complete = events[-1]
    assert turn_complete.total_steps == 2
    assert turn_complete.stop_reason == "stop"

    # Messages history: user -> assistant(call) -> tool(result) -> assistant(text)
    assert len(harness.messages) == 4
    assert harness.messages[2].role == "tool"
    assert harness.messages[2].content == "1: def main(): pass"


@pytest.mark.asyncio
async def test_max_steps_safeguard() -> None:
    mock = MockProvider()
    # Infinite loop simulation: LLM always calls a tool
    for i in range(10):
        mock.queue_tool_call_response(
            tool_name="ping",
            arguments={"count": i},
            call_id=f"call_{i}",
        )

    def ping_tool(count: int) -> str:
        return f"pong {count}"

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        tool_executor=lambda name, args: ping_tool(**args),
        max_steps_per_turn=3,
    )

    events = [e async for e in harness.prompt("Infinite ping")]

    turn_complete = events[-1]
    assert turn_complete.type == "turn_complete"
    assert turn_complete.total_steps == 3
    assert turn_complete.stop_reason == "max_steps"


@pytest.mark.asyncio
async def test_tool_execution_error_handled_gracefully() -> None:
    mock = MockProvider()
    mock.queue_tool_call_response(
        tool_name="failing_tool",
        arguments={},
        call_id="call_fail",
    )
    mock.queue_text_response("Tool failed, handling error.")

    def failing_tool() -> str:
        raise RuntimeError("Disk corrupted")

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        tool_executor=lambda name, args: failing_tool(),
    )

    events = [e async for e in harness.prompt("Do risky work")]

    tool_result = next(e for e in events if e.type == "tool_result")
    assert tool_result.is_error is True
    assert "Disk corrupted" in str(tool_result.output)
