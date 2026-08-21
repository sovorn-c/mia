"""Unit and scenario tests for MiaREPL interactive stream harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall
from mia_cli.repl import MiaREPL, REPLCompleter


def test_repl_completer_and_slash_menu(tmp_path: Path) -> None:
    completer = REPLCompleter(
        ["/help", "/model", "/profile", "/compact", "/cost", "/sessions", "/clear", "/quit"]
    )

    # Test prefix matching
    assert completer.complete("/m", 0) == "/model"
    assert completer.complete("/p", 0) == "/profile"
    assert completer.complete("/c", 0) == "/compact"
    assert completer.complete("/c", 1) == "/cost"
    assert completer.complete("/c", 2) == "/clear"

    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)

    # Test '/' prints menu
    assert repl.handle_slash_command("/") is True
    assert repl.handle_slash_command("/?") is True
    assert repl.handle_slash_command("/help") is True
    assert repl.handle_slash_command("/model") is True
    assert repl.handle_slash_command("/profile") is True
    assert repl.handle_slash_command("/cost") is True
    assert repl.handle_slash_command("/clear") is True
    assert repl.handle_slash_command("/model mock-model") is True
    assert repl.model_name == "mock-model"
    assert repl.handle_slash_command("/profile architect") is True
    assert repl.profile_name == "architect"
    assert repl.handle_slash_command("/quit") is False


@pytest.mark.asyncio
async def test_repl_execute_turn_with_tools(tmp_path: Path) -> None:
    mock = MockProvider()
    mock.queue_tool_call(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "hello.py", "content": "print('hello world')\n"},
        ),
        thought="Writing hello.py script.",
    )
    mock.queue_text_response("File hello.py written successfully.")

    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)

    # Run turn
    await repl.execute_turn("Create hello.py")

    assert (tmp_path / "hello.py").exists()
    assert (tmp_path / "hello.py").read_text() == "print('hello world')\n"
    assert repl.total_tokens > 0
