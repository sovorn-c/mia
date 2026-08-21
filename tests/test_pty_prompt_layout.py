"""Rigorous tests verifying prompt layout and status container placement."""

from __future__ import annotations

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mia_cli.interactive_input import LivePromptSession, format_status_toolbar


def test_format_status_toolbar_output() -> None:
    """Verify format_status_toolbar generates clean, concise HTML badge without wrapping."""
    tb = format_status_toolbar(
        workspace_name="test_proj",
        model_name="mimo-v2.5",
        tokens=1200,
        window_tokens=128000,
        thinking_enabled=True,
    )
    assert "test_proj" in tb.value
    assert "mimo-v2.5" in tb.value
    assert "1.2k/128k" in tb.value
    assert "💭 on" in tb.value
    assert "/help" in tb.value


def test_prompt_session_initialization() -> None:
    """Verify that LivePromptSession initializes with visible completion space."""
    session = LivePromptSession()
    assert session.completer is not None
    assert session.session is not None
    assert session.session.reserve_space_for_menu == 8


@pytest.mark.asyncio
async def test_prompt_execution_with_pipe_input() -> None:
    """Verify that prompt execution completes cleanly without history errors."""
    with create_pipe_input() as pipe:
        session = LivePromptSession(
            input=pipe,
            output=DummyOutput(),
        )

        pipe.send_text("hello prompt\r")
        result = await session.read_prompt_async("› ")
        assert result == "hello prompt"
