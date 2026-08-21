"""Unit and scenario tests for MiaREPL interactive stream harness with prompt_toolkit & Pi-style Auth and Model Scoper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.document import Document

from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall
from mia_cli.interactive_input import (
    LiveInteractivePrompt,
    LivePromptSession,
    SlashCompleter,
    format_status_toolbar,
    interactive_select,
)
from mia_cli.renderers.rich_stream import CarrotBounceSpinner
from mia_cli.repl import MiaREPL


def test_slash_completer_and_menu() -> None:
    completer = SlashCompleter()

    # When text is "/l"
    doc_l = Document(text="/l", cursor_position=2)
    completions = list(completer.get_completions(doc_l, complete_event=MagicMock()))
    cmd_names = [c.text for c in completions]
    assert "/login" in cmd_names
    assert "/logout" in cmd_names
    assert "/model" not in cmd_names

    # When text is not starting with /
    doc_text = Document(text="hello", cursor_position=5)
    completions_empty = list(completer.get_completions(doc_text, complete_event=MagicMock()))
    assert len(completions_empty) == 0


def test_format_status_toolbar() -> None:
    toolbar_html = format_status_toolbar(
        workspace_name="mia",
        model_name="mimo-v2.5",
        tokens=12500,
        window_tokens=128000,
        thinking_enabled=True,
    )
    assert "mia" in toolbar_html.value
    assert "mimo-v2.5" in toolbar_html.value
    assert "12.5k/128k" in toolbar_html.value
    assert "thinking: on" in toolbar_html.value


def test_carrot_bounce_spinner() -> None:
    frame0 = CarrotBounceSpinner.render_frame(0.0)
    assert "🥕" in frame0
    assert "Thinking (0.0s)..." in frame0

    frame1 = CarrotBounceSpinner.render_frame(1.5)
    assert "🥕" in frame1
    assert "Thinking (1.5s)..." in frame1


def test_repl_slash_commands_suite(tmp_path: Path) -> None:
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)

    assert repl.handle_slash_command("/") is True
    assert repl.handle_slash_command("/?") is True
    assert repl.handle_slash_command("/help") is True
    assert repl.handle_slash_command("/profile") is True
    assert repl.handle_slash_command("/cost") is True
    assert repl.handle_slash_command("/stats") is True
    assert repl.handle_slash_command("/diff") is True
    assert repl.handle_slash_command("/init") is True
    assert repl.handle_slash_command("/compact") is True
    assert repl.handle_slash_command("/sessions") is True
    assert repl.handle_slash_command("/tree") is True
    assert repl.handle_slash_command("/inspect") is True
    assert repl.handle_slash_command("/thinking") is True
    assert repl.show_thinking_trace is True
    assert repl.handle_slash_command("/thinking") is True
    assert repl.show_thinking_trace is False
    assert repl.handle_slash_command("/stop") is True
    assert repl.handle_slash_command("/clear") is True
    assert repl.handle_slash_command("/model mock-model") is True
    assert repl.model_name == "mock-model"
    assert repl.handle_slash_command("/profile architect") is True
    assert repl.profile_name == "architect"
    assert repl.handle_slash_command("/quit") is False


def test_repl_pi_style_auth_and_model_scoper(tmp_path: Path) -> None:
    """Test Pi-style provider authentication directly saves key and updates active provider."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    with (
        patch("builtins.input", side_effect=["api_key", "opencode-go"]),
        patch("getpass.getpass", return_value="sk-test-opencode-key-123"),
    ):
        repl.interactive_login()

    saved_key = repl.cred_store.get_api_key("opencode-go")
    assert saved_key == "sk-test-opencode-key-123"
    assert repl.model_name is None

    # Now pick model with /model
    with patch("builtins.input", return_value="1"):
        repl.interactive_model_picker()
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
    assert len(repl.stream_renderer.turn_audit_log) == 1
    assert repl.stream_renderer.turn_audit_log[0]["tool_name"] == "write_file"


def test_live_interactive_prompt_non_tty(tmp_path: Path) -> None:
    """Verify LiveInteractivePrompt correctly reads input in non-tty/test mode."""
    history_file = tmp_path / "history"
    prompt_reader = LiveInteractivePrompt(history_file=history_file)

    with patch("builtins.input", return_value="/help"):
        res = prompt_reader.read_prompt()
        assert res == "/help"


def test_live_prompt_session_non_tty(tmp_path: Path) -> None:
    """Verify LivePromptSession correctly reads input in non-tty/test mode."""
    history_file = tmp_path / "history"
    session = LivePromptSession(history_file=history_file)

    with patch("builtins.input", return_value="hello mia"):
        res = session.read_prompt()
        assert res == "hello mia"


@pytest.mark.asyncio
async def test_live_prompt_session_async_non_tty(tmp_path: Path) -> None:
    """Verify LivePromptSession correctly reads async input in non-tty/test mode."""
    history_file = tmp_path / "history"
    session = LivePromptSession(history_file=history_file)

    with patch("builtins.input", return_value="async hello"):
        res = await session.read_prompt_async()
        assert res == "async hello"


def test_interactive_select_non_tty() -> None:
    """Verify interactive_select selects by index or id in non-tty mode."""
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


def test_validate_api_key_rejection(tmp_path: Path) -> None:
    """Verify validate_api_key detects 401 Unauthorized responses."""
    from mia_agent.auth.config import validate_api_key

    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401)
        valid, msg = validate_api_key("opencode-go", "bad-key-12345")
        assert valid is False
        assert "401" in msg


def test_login_rejects_invalid_api_key(tmp_path: Path) -> None:
    """Verify login wizard does NOT save invalid API key."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    with (
        patch("mia_agent.auth.config.validate_api_key", return_value=(False, "Invalid Key")),
        patch("builtins.input", side_effect=["api_key", "opencode-go"]),
        patch("getpass.getpass", return_value="invalid-key-xyz"),
    ):
        repl.interactive_login()

    saved_key = repl.cred_store.get_api_key("opencode-go")
    assert saved_key is None


def test_logout_command(tmp_path: Path) -> None:
    """Verify /logout deletes stored credentials and resets model."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    repl.cred_store.set_api_key("openai", "sk-openai-key")
    repl.model_name = "gpt-4o"

    repl.handle_logout("openai")
    assert repl.cred_store.get_api_key("openai") is None
    assert repl.model_name is None


def test_openai_oauth_save_direct_token(tmp_path: Path) -> None:
    """Verify OpenAIOAuthManager saves valid token."""
    from mia_agent.auth.credentials import FileCredentialStore
    from mia_agent.auth.openai_auth import OpenAIOAuthManager

    cred_file = tmp_path / "credentials.json"
    cred_store = FileCredentialStore(path=cred_file)
    mgr = OpenAIOAuthManager(cred_store=cred_store)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        ok, msg = mgr.save_direct_token("oauth-test-token-123")
        assert ok is True
        assert cred_store.get_api_key("openai") == "oauth-test-token-123"
