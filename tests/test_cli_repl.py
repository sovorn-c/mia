"""Unit and scenario tests for MiaREPL interactive stream harness with Pi-style Auth and Model Scoper."""

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


def test_repl_pi_style_auth_and_model_scoper(tmp_path: Path) -> None:
    """Test Pi-style provider authentication followed by model scoping."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    # Simulate: Pick Provider [1] (opencode-go), Enter API Key, then Pick Model [1] (mimo-v2.5)
    with (
        patch("builtins.input", side_effect=["1", "1"]),
        patch("getpass.getpass", return_value="sk-test-opencode-key-123"),
    ):
        repl.interactive_login()

    saved_key = repl.cred_store.get_api_key("opencode-go")
    assert saved_key == "sk-test-opencode-key-123"
    assert repl.model_name == "mimo-v2.5"


def test_repl_scoped_model_picker(tmp_path: Path) -> None:
    """Test interactive model picker lists authenticated models."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    repl.cred_store.set_api_key("deepseek", "sk-deepseek-test-key")

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("builtins.input", return_value="1"),
    ):
        repl.interactive_model_picker()

    assert repl.model_name == "deepseek-chat"


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


def test_live_interactive_prompt_non_tty(tmp_path: Path) -> None:
    """Verify LiveInteractivePrompt correctly reads input in non-tty/test mode."""
    from mia_cli.interactive_input import LiveInteractivePrompt

    history_file = tmp_path / "history"
    prompt_reader = LiveInteractivePrompt(history_file=history_file)

    with patch("builtins.input", return_value="/help"):
        res = prompt_reader.read_prompt()
        assert res == "/help"


def test_interactive_select_non_tty() -> None:
    """Verify interactive_select selects by index or id in non-tty mode."""
    from mia_cli.interactive_input import interactive_select

    options = [
        ("opt_1", "Option One", "First item"),
        ("opt_2", "Option Two", "Second item"),
    ]
    with patch("builtins.input", return_value="1"):
        res = interactive_select("Test Title", options)
        assert res == "opt_1"

    with patch("builtins.input", return_value="opt_2"):
        res2 = interactive_select("Test Title", options)
        assert res2 == "opt_2"
