"""Unit and scenario tests for MiaREPL interactive stream harness."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall
from mia_cli.repl import MiaREPL, REPLCompleter


def test_repl_completer_and_slash_menu(tmp_path: Path) -> None:
    completer = REPLCompleter(
        [
            "/help",
            "/login",
            "/model",
            "/profile",
            "/diff",
            "/cost",
            "/compact",
            "/sessions",
            "/init",
            "/undo",
            "/clear",
            "/quit",
        ]
    )

    # Test prefix matching
    assert completer.complete("/l", 0) == "/login"
    assert completer.complete("/m", 0) == "/model"
    assert completer.complete("/p", 0) == "/profile"
    assert completer.complete("/d", 0) == "/diff"
    assert completer.complete("/c", 0) == "/cost"
    assert completer.complete("/c", 1) == "/compact"
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
    assert repl.handle_slash_command("/stats") is True
    assert repl.handle_slash_command("/diff") is True
    assert repl.handle_slash_command("/init") is True
    assert repl.handle_slash_command("/undo") is True
    assert repl.handle_slash_command("/clear") is True
    assert repl.handle_slash_command("/model mock-model") is True
    assert repl.model_name == "mock-model"
    assert repl.handle_slash_command("/profile architect") is True
    assert repl.profile_name == "architect"
    assert repl.handle_slash_command("/quit") is False


def test_repl_interactive_login_wizard(tmp_path: Path) -> None:
    """Test interactive login wizard saves credentials and updates model."""
    cred_file = tmp_path / "credentials.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file

    with (
        patch("builtins.input", side_effect=["1"]),
        patch("getpass.getpass", return_value="sk-test-opencode-key-123"),
    ):
        repl.interactive_login()

    saved_key = repl.cred_store.get_api_key("opencode-go")
    assert saved_key == "sk-test-opencode-key-123"
    assert repl.model_name == "mimo-v2.5"


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
