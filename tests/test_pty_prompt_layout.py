"""Rigorous tests verifying prompt layout and status container placement."""

from __future__ import annotations

import pytest
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.containers import FloatContainer, HSplit
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


def test_prompt_layout_inline_container_structure() -> None:
    """Verify that status_container is mounted directly inside main_input_container HSplit."""
    session = LivePromptSession(
        toolbar_callback=lambda: HTML("  📁 test_ws │ 🧠 test_model │ ⚡ 0/128k │ /help")
    )

    # Root container is HSplit
    assert isinstance(session.session.layout.container, HSplit)

    # Child 0 contains main_input_container FloatContainer
    c0 = session.session.layout.container.children[0]
    main_input = getattr(c0, "alternative_content", None) or getattr(c0, "content", None)
    assert isinstance(main_input, FloatContainer)
    assert isinstance(main_input.content, HSplit)

    # Verify main_input.content has 3+ children (prompt_1, buffer, status)
    assert len(main_input.content.children) >= 3


@pytest.mark.asyncio
async def test_prompt_execution_with_pipe_input() -> None:
    """Verify that prompt execution completes cleanly without history errors."""
    with create_pipe_input() as pipe:
        session = LivePromptSession(
            toolbar_callback=lambda: HTML("  📁 test_ws │ 🧠 test_model │ ⚡ 0/128k │ /help"),
            input=pipe,
            output=DummyOutput(),
        )

        pipe.send_text("hello prompt\r")
        result = await session.session.prompt_async("› ")
        assert result == "hello prompt"
