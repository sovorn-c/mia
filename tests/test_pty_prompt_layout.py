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


@pytest.mark.asyncio
async def test_compose_during_busy_run_blocks_enter_and_does_not_queue() -> None:
    """SC-e13s02-P0-01: User can edit draft during a run; Enter does not submit while busy."""
    import asyncio

    with create_pipe_input() as pipe:
        session = LivePromptSession(
            input=pipe,
            output=DummyOutput(),
        )
        session.is_busy = True

        prompt_task = asyncio.create_task(session.read_prompt_async("› "))
        pipe.send_text("draft during run\r")
        await asyncio.sleep(0.05)

        # Prompt must NOT have completed because session is busy
        assert not prompt_task.done()

        # Mark run finished, now pressing Enter submits the draft
        session.is_busy = False
        pipe.send_text("\r")
        await asyncio.sleep(0.05)

        assert prompt_task.done()
        assert await prompt_task == "draft during run"


def test_draft_preserved_across_cancellation() -> None:
    """SC-e13s02-P0-02: Cancelling an active run retains the draft."""
    from unittest.mock import MagicMock

    session = LivePromptSession()
    session.is_busy = True

    # Simulate keybinding handler for Ctrl+C while busy
    c_c_binding = session.bindings.get_bindings_for_keys(("c-c",))[-1]
    mock_buffer = MagicMock()
    mock_buffer.text = "unsent draft text"
    mock_event = MagicMock(current_buffer=mock_buffer)

    c_c_binding.handler(mock_event)

    # Buffer must NOT be reset when busy
    mock_buffer.reset.assert_not_called()
    assert session.get_draft() == "unsent draft text"

    # In contrast, when idle, Ctrl+C clears the buffer
    session.is_busy = False
    c_c_binding.handler(mock_event)
    mock_buffer.reset.assert_called_once()


def test_approval_focus_is_distinct_and_restores_draft() -> None:
    """SC-e13s02-P0-03: Approval input is separate and preserves existing draft."""
    from unittest.mock import patch
    from pathlib import Path
    from mia_cli.repl import MiaREPL
    from mia_middleware.access import ApprovalRequest
    from rich.console import Console

    repl = MiaREPL(cwd=Path("/tmp"))
    repl.console = Console(record=True, width=120)
    repl.prompt_session.set_draft("in-progress user prompt")

    req = ApprovalRequest(
        effect="side-effecting",
        tool_name="write_file",
        arguments={"path": "test.txt", "content": "hello"},
        agent_id="mia",
    )

    # User answers 'y' to approval
    with patch("builtins.input", return_value="y"):
        approved = repl._request_tool_approval(req)
        assert approved is True

    # Draft remains intact and was not consumed as approval
    assert repl.prompt_session.get_draft() == "in-progress user prompt"

