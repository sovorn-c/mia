"""Unit and scenario tests for MiaREPL interactive stream harness with prompt_toolkit & Pi-style Auth and Model Scoper."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from mia_agent.agents import AgentManager
from mia_agent.session.entries import MessageEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_ai.providers.mock import MockProvider
from mia_ai.types import ToolCall
from mia_cli.interactive_input import (
    COMMAND_HINTS,
    LiveInteractivePrompt,
    LivePromptSession,
    SlashCompleter,
    format_status_toolbar,
    interactive_multi_select,
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


def test_follow_up_queue_is_explicit_single_slot_and_preserves_text(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120, force_terminal=False, no_color=True)
    repl.prompt_session.is_busy = True
    repl.prompt_session.set_draft("follow-up exactly")

    assert repl.queue_follow_up() is True
    assert repl.queued_follow_up == "follow-up exactly"
    assert repl.prompt_session.get_draft() == ""
    assert repl.queue_follow_up("replacement") is False
    assert repl.queued_follow_up == "follow-up exactly"


def test_command_discovery_has_one_truthful_canonical_list() -> None:
    from mia_cli.repl import COMMAND_ALIASES, COMMAND_DESCRIPTIONS, SLASH_COMMANDS

    canonical = [command for command, _ in COMMAND_HINTS]

    assert len(canonical) == 17
    assert "/scoped-models" in canonical
    assert "/stop" not in canonical
    assert canonical == SLASH_COMMANDS
    assert canonical == list(COMMAND_DESCRIPTIONS)
    assert "/abort" not in COMMAND_ALIASES


def test_help_contract_describes_only_implemented_behavior(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)

    repl.handle_slash_command("/help")
    help_output = repl.console.export_text()
    assert "17 Canonical Slash Commands" in help_output
    assert "shortcuts" not in help_output
    assert "/stop" not in help_output

    repl.console = Console(record=True, width=120)
    repl.handle_slash_command("/init")
    init_output = repl.console.export_text()
    assert "Basic Repository Context" in init_output
    assert "architecture" not in init_output.lower()


def test_adaptive_toolbar_labels_provider_usage_and_context() -> None:
    full = format_status_toolbar(
        workspace_name="mia",
        model_name="gpt-5",
        provider_name="openai-codex",
        tokens=12500,
        current_context_tokens=3200,
        window_tokens=128000,
        run_state="responding",
        width=120,
    )
    assert "Provider" in full.value
    assert "openai-codex" in full.value
    assert "Lifetime usage" in full.value
    assert "Current context" in full.value
    assert "3.2k" in full.value
    assert "[responding]" in full.value

    narrow = format_status_toolbar(
        workspace_name="mia",
        model_name="gpt-5",
        provider_name="openai-codex",
        tokens=12500,
        current_context_tokens=3200,
        window_tokens=128000,
        run_state="tool",
        width=50,
    )
    assert "gpt-5" in narrow.value
    assert "[tool]" in narrow.value
    assert "Current context" not in narrow.value


@pytest.mark.asyncio
async def test_follow_up_auto_runs_only_after_success_and_restores_on_failure(
    tmp_path: Path,
) -> None:
    from mia_agent.events import TurnCompleteEvent, TurnStartEvent
    from mia_agent.runtime_events import AgentEventEnvelope, RunErrorEvent

    successful_requests: list[str] = []
    active_runs = 0
    max_active_runs = 0

    async def successful_run(request: object, **kwargs: object):
        nonlocal active_runs, max_active_runs
        successful_requests.append(request.prompt_text)  # type: ignore[attr-defined]
        active_runs += 1
        max_active_runs = max(max_active_runs, active_runs)
        try:
            yield AgentEventEnvelope(
                run_id="run",
                task_id="root",
                agent_id="mia",
                session_id="session",
                event=TurnStartEvent(user_prompt=request.prompt_text),  # type: ignore[attr-defined]
            )
            yield AgentEventEnvelope(
                run_id="run",
                task_id="root",
                agent_id="mia",
                session_id="session",
                event=TurnCompleteEvent(total_steps=1, stop_reason="stop"),
            )
        finally:
            active_runs -= 1

    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.agent_runner.run = successful_run  # type: ignore[method-assign]
    repl.prompt_session.is_busy = True
    repl.prompt_session.set_draft("follow-up")
    assert repl.queue_follow_up() is True
    await repl.execute_turn("first")

    assert successful_requests == ["first", "follow-up"]
    assert max_active_runs == 1
    assert repl.queued_follow_up is None

    async def failed_run(*args: object, **kwargs: object):
        yield AgentEventEnvelope(
            run_id="run",
            task_id="root",
            agent_id="mia",
            session_id="session",
            event=RunErrorEvent(stage="agent", error="failed", code="agent_error"),
        )

    repl.agent_runner.run = failed_run  # type: ignore[method-assign]
    repl.prompt_session.is_busy = True
    repl.prompt_session.set_draft("restore me")
    assert repl.queue_follow_up() is True
    await repl.execute_turn("second")

    assert repl.queued_follow_up is None
    assert repl.prompt_session.get_draft() == "restore me"


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
    assert "💭 on" in toolbar_html.value

    escaped = format_status_toolbar(workspace_name="<mia>", model_name="model&name")
    assert "&lt;mia&gt;" in escaped.value
    assert "model&amp;name" in escaped.value


def test_carrot_bounce_spinner() -> None:
    frame0 = CarrotBounceSpinner.render_frame(0.0)
    assert "🥕" in frame0
    assert "Thinking (0.0s)..." in frame0

    frame1 = CarrotBounceSpinner.render_frame(1.5)
    assert "🥕" in frame1
    assert "Thinking (1.5s)..." in frame1


def test_model_and_thinking_keybindings_dispatch_pi_commands() -> None:
    from prompt_toolkit.keys import Keys

    session = LivePromptSession()
    expected = {
        Keys.ControlL: "/model",
        Keys.ControlP: "/model next",
        Keys.BackTab: "/thinking",
    }

    for key, command in expected.items():
        binding = session.bindings.get_bindings_for_keys((key,))[-1]
        buffer = MagicMock()
        event = MagicMock(current_buffer=buffer)
        binding.handler(event)
        assert buffer.text == command
        buffer.validate_and_handle.assert_called_once_with()


def test_scoped_model_cycle_switches_and_wraps(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.available_model_sources = {
        "openai::shared-model": "openai",
        "openrouter::shared-model": "openrouter",
    }
    repl.scoped_models = ["openai::shared-model", "openrouter::shared-model"]
    repl.model_name = "shared-model"
    repl._save_model_selection("openai", "shared-model")

    assert repl.handle_slash_command("/model next") is True
    assert repl.model_name == "shared-model"
    assert repl.config_mgr.config.default_provider == "openrouter"

    assert repl.handle_slash_command("/model next") is True
    assert repl.model_name == "shared-model"
    assert repl.config_mgr.config.default_provider == "openai"


def test_double_escape_opens_tree_only_on_second_press() -> None:
    session = LivePromptSession()
    buffer = MagicMock()
    buffer.complete_state = None
    buffer.text = ""
    event = MagicMock()
    event.current_buffer = buffer

    with patch("mia_cli.interactive_input.time.monotonic", side_effect=[10.0, 10.2]):
        session._handle_escape(event)
        buffer.validate_and_handle.assert_not_called()
        session._handle_escape(event)

    assert buffer.text == "/tree"
    buffer.validate_and_handle.assert_called_once_with()


def test_searchable_agent_and_command_pickers_preserve_draft(tmp_path: Path) -> None:
    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent("researcher", display_name="Researcher", tools=[])
    repl = MiaREPL(
        agent="mia",
        agent_manager=manager,
        cwd=tmp_path,
        custom_provider=MockProvider(),
    )
    repl.prompt_session.set_draft("keep this draft")

    with patch("mia_cli.repl.interactive_select", return_value="researcher") as select:
        repl.interactive_agent_picker()
    assert select.call_args.args[0] == "🤖 Switch Agent"
    assert repl.agent_id == "researcher"
    assert repl.prompt_session.get_draft() == "keep this draft"

    with patch("mia_cli.repl.interactive_select", return_value="/cost"):
        repl.interactive_command_picker()
    assert repl.prompt_session.get_draft() == "keep this draft"


def test_repl_agent_command_selects_named_agent(tmp_path: Path) -> None:
    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent("researcher", display_name="Researcher", tools=[])
    repl = MiaREPL(
        agent="mia",
        agent_manager=manager,
        cwd=tmp_path,
        custom_provider=MockProvider(),
    )
    repl.console = Console(record=True, width=120)

    assert repl.handle_slash_command("/agent") is True
    assert "Mia" in repl.console.export_text()
    assert repl.handle_slash_command("/agent researcher") is True
    assert repl.agent_id == "researcher"


def test_repl_slash_commands_suite(tmp_path: Path) -> None:
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)

    assert repl.handle_slash_command("/") is True
    assert repl.handle_slash_command("/?") is True
    assert repl.handle_slash_command("/help") is True
    assert repl.handle_slash_command("/cost") is True
    assert repl.handle_slash_command("/stats") is True
    assert repl.handle_slash_command("/diff") is True
    assert repl.handle_slash_command("/init") is True
    assert repl.handle_slash_command("/compact") is True
    assert repl.handle_slash_command("/sessions") is True
    assert repl.handle_slash_command("/resume") is True
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
    assert repl.handle_slash_command("/quit") is False


def test_session_resume_hint_is_shown_on_quit_and_eof(tmp_path: Path) -> None:
    repl = MiaREPL(
        cwd=tmp_path,
        custom_provider=MockProvider(),
        session_id="session_resume_me",
    )
    repl.console = Console(record=True, width=120)

    assert repl.handle_slash_command("/quit") is False
    quit_output = repl.console.export_text()
    assert "session_resume_me" in quit_output
    assert "mia --session session_resume_me" in quit_output

    repl.console = Console(record=True, width=120)
    repl.prompt_session.read_prompt_async = AsyncMock(side_effect=EOFError)
    asyncio.run(repl.run_async())
    eof_output = repl.console.export_text()
    assert "session_resume_me" in eof_output
    assert "mia --session session_resume_me" in eof_output


def test_diff_reports_git_failure_instead_of_clean_tree(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)
    failed_diff = subprocess.CompletedProcess(
        args=["git", "diff"],
        returncode=128,
        stdout="",
        stderr="fatal: not a git repository",
    )

    with patch("mia_cli.repl.subprocess.run", return_value=failed_diff):
        assert repl.handle_slash_command("/diff") is True

    output = repl.console.export_text()
    assert "not a git repository" in output
    assert "Working tree clean" not in output


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

    # Discover and save the scope first, then /model only selects from it.
    with patch("mia_cli.repl.interactive_multi_select", return_value=["opencode-go::mimo-v2.5"]):
        repl.handle_slash_command("/scoped-models")
    with patch("builtins.input", return_value="1"):
        repl.interactive_model_picker()
    assert repl.model_name == "mimo-v2.5"


def test_model_picker_loads_persisted_scope_sources_on_startup(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.cred_store.set_api_key("openai", "sk-test-openai")
    repl.config_mgr.save_config(
        repl.config_mgr.config.model_copy(
            update={
                "default_provider": "openai",
                "default_model": "stored-model",
                "model_catalog": {"openai": ["stored-model"]},
                "scoped_models": ["openai::stored-model"],
            }
        )
    )
    repl.scoped_models = ["openai::stored-model"]
    repl.model_name = "stored-model"

    with (
        patch("mia_cli.repl.discover_provider_models") as discover,
        patch("mia_cli.repl.interactive_select", return_value="openai::stored-model") as select,
    ):
        repl.interactive_model_picker()

    discover.assert_not_called()
    assert select.call_args.args[1] == [
        ("openai::stored-model", "openai: stored-model (Active)", "")
    ]
    assert repl.model_name == "stored-model"


def test_connected_provider_models_use_stored_catalog_without_environment(
    tmp_path: Path,
) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.cred_store.set_api_key("openai", "sk-test-openai")
    repl.cred_store.set_api_key("deepseek", "sk-test-deepseek")
    repl.config_mgr.save_config(
        repl.config_mgr.config.model_copy(
            update={
                "model_catalog": {
                    "openai": ["openai-model"],
                    "deepseek": ["deepseek-model"],
                    "gemini": ["gemini-model"],
                }
            }
        )
    )

    with patch(
        "mia_cli.repl.interactive_multi_select",
        return_value=["deepseek::deepseek-model", "openai::openai-model"],
    ):
        repl.handle_slash_command("/scoped-models")

    assert repl.scoped_models == [
        "deepseek::deepseek-model",
        "openai::openai-model",
    ]
    assert set(repl.available_model_sources.values()) == {"deepseek", "openai"}
    assert "gemini" not in repl.available_model_sources.values()

    repl.cred_store.delete("openai")
    repl.handle_slash_command("/scoped-models")
    assert repl.available_model_sources == {"deepseek::deepseek-model": "deepseek"}


def test_scoped_models_prunes_logged_out_provider_from_saved_scope(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.cred_store.set_api_key("openai", "sk-test-openai")
    repl.cred_store.set_api_key("deepseek", "sk-test-deepseek")
    repl.scoped_models = ["openai::gpt-4o", "deepseek::deepseek-chat"]
    repl._save_scoped_models()
    repl.cred_store.delete("openai")

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("mia_cli.repl.discover_provider_models", return_value=["deepseek-chat"]),
        patch("mia_cli.repl.interactive_multi_select", return_value=["deepseek::deepseek-chat"]),
    ):
        repl.handle_slash_command("/scoped-models")

    assert repl.available_model_sources == {"deepseek::deepseek-chat": "deepseek"}
    assert repl.scoped_models == ["deepseek::deepseek-chat"]
    assert repl.config_mgr.config.scoped_models == ["deepseek::deepseek-chat"]

    repl.cred_store.delete("deepseek")
    with patch("mia_cli.repl.interactive_select") as select:
        repl.interactive_model_picker()
    select.assert_not_called()
    assert repl.scoped_models == []
    assert repl.config_mgr.config.scoped_models == []


def test_custom_connected_model_is_in_model_picker(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.config_mgr.save_config(
        repl.config_mgr.config.model_copy(
            update={
                "default_provider": "custom",
                "default_model": "local-model",
                "base_urls": {"custom": "http://localhost:11434/v1"},
            }
        )
    )
    repl.model_name = "local-model"

    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "mia_cli.repl.discover_provider_models",
            return_value=["local-model", "other-local-model"],
        ),
        patch(
            "mia_cli.repl.interactive_multi_select",
            return_value=["custom::local-model"],
        ),
    ):
        repl.handle_slash_command("/scoped-models")

    with patch("mia_cli.repl.interactive_select", return_value="custom::local-model") as select:
        repl.interactive_model_picker()

    assert select.call_args.args[1][0][0] == "custom::local-model"
    assert repl.model_name == "local-model"


def test_scoped_models_opens_selector_and_saves_selected_scope(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.cred_store.set_api_key("openai", "sk-test-openai")
    repl.cred_store.set_api_key("deepseek", "sk-test-deepseek")

    models = {"openai": ["gpt-4o"], "deepseek": ["deepseek-chat"]}
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "mia_cli.repl.discover_provider_models",
            side_effect=lambda provider, **_: models[provider],
        ),
        patch(
            "mia_cli.repl.interactive_multi_select",
            return_value=["openai::gpt-4o"],
        ) as selector,
    ):
        assert repl.handle_slash_command("/scoped-models") is True

    selector.assert_called_once()
    assert selector.call_args.kwargs["selected_ids"] == []
    assert repl.scoped_models == ["openai::gpt-4o"]
    assert repl.config_mgr.config.scoped_models == ["openai::gpt-4o"]


def test_login_preserves_saved_scoped_models(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    repl.scoped_models = ["openai::gpt-4o"]
    repl._save_scoped_models()

    with (
        patch("mia_cli.repl.interactive_select", side_effect=["api_key", "openai"]),
        patch("getpass.getpass", return_value="sk-test-openai"),
    ):
        repl.interactive_login()

    assert repl.config_mgr.config.scoped_models == ["openai::gpt-4o"]


def test_scoped_models_command_discovers_and_sets_cycle_scope(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.cred_store.path = tmp_path / "credentials.json"
    repl.config_mgr.config_path = tmp_path / "config.json"
    for provider in ("openai", "deepseek", "gemini"):
        repl.cred_store.set_api_key(provider, f"sk-test-{provider}")

    models = {
        "openai": ["gpt-4o"],
        "deepseek": ["deepseek-chat"],
        "gemini": ["gemini-pro"],
    }
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "mia_cli.repl.discover_provider_models",
            side_effect=lambda provider, **_: models[provider],
        ),
    ):
        with patch(
            "mia_cli.repl.interactive_multi_select",
            return_value=["openai::gpt-4o", "deepseek::deepseek-chat"],
        ):
            assert (
                repl.handle_slash_command("/scoped-models openai: gpt-4o, deepseek: deepseek-chat")
                is True
            )
        assert repl.scoped_models == ["openai::gpt-4o", "deepseek::deepseek-chat"]

        with patch(
            "mia_cli.repl.interactive_multi_select",
            return_value=[
                "openai::gpt-4o",
                "deepseek::deepseek-chat",
                "gemini::gemini-pro",
            ],
        ):
            assert repl.handle_slash_command("/scoped-models all") is True

    assert repl.scoped_models == [
        "openai::gpt-4o",
        "deepseek::deepseek-chat",
        "gemini::gemini-pro",
    ]


def test_repl_scoped_model_picker(tmp_path: Path) -> None:
    """Test interactive model picker lists authenticated models."""
    cred_file = tmp_path / "credentials.json"
    cfg_file = tmp_path / "config.json"
    mock = MockProvider()
    repl = MiaREPL(cwd=tmp_path, custom_provider=mock)
    repl.cred_store.path = cred_file
    repl.config_mgr.config_path = cfg_file

    repl.cred_store.set_api_key("deepseek", "sk-test-deepseek")

    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "mia_cli.repl.interactive_multi_select",
            return_value=["deepseek::deepseek-v4-pro"],
        ),
    ):
        repl.handle_slash_command("/scoped-models")
    with patch("builtins.input", return_value="1"):
        repl.interactive_model_picker()

    assert repl.model_name == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_repl_resume_and_tree_fork(tmp_path: Path) -> None:
    session_dir = tmp_path / "agents" / "mia" / "sessions"
    mock = MockProvider()
    repl = MiaREPL(
        cwd=tmp_path,
        custom_provider=mock,
        agent_manager=AgentManager(agents_dir=tmp_path / "agents"),
    )

    repl.session_id = "saved-session"
    repl._init_harness()
    assert repl.harness is not None
    mock.queue_text_response("Root answer")
    await repl.execute_turn("Root question")
    mock.queue_text_response("Second answer")
    await repl.execute_turn("Second question")

    entries = JsonlSessionStore(session_dir / "saved-session.jsonl").load_entries()
    first_user = next(entry for entry in entries if isinstance(entry, MessageEntry))

    repl.session_id = "new-session"
    repl._init_harness()
    with patch("mia_cli.repl.interactive_select", return_value="saved-session"):
        assert repl.handle_slash_command("/resume") is True
    assert repl.session_id == "saved-session"
    assert repl.harness is not None
    assert [message.content for message in repl.harness.messages] == [
        "Root question",
        "Root answer",
        "Second question",
        "Second answer",
    ]

    with patch("mia_cli.repl.interactive_select", return_value=first_user.id):
        assert repl.handle_slash_command("/tree") is True
    assert [message.content for message in repl.harness.messages] == ["Root question"]

    mock.queue_text_response("Fork answer")
    await repl.execute_turn("Fork question")
    assert repl.harness.messages[-1].content == "Fork answer"

    (session_dir / "old-session.jsonl").write_text("", encoding="utf-8")
    repl.delete_session("old-session")
    assert not (session_dir / "old-session.jsonl").exists()
    with pytest.raises(ValueError, match="active session"):
        repl.delete_session("saved-session")


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

    # Run turn with explicit approval for the side-effecting Tool.
    with patch("builtins.input", return_value="y"):
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


def test_interactive_multi_select_non_tty() -> None:
    options = [
        ("openai::gpt-4o", "openai: gpt-4o", ""),
        ("deepseek::deepseek-chat", "deepseek: deepseek-chat", ""),
    ]
    with patch("builtins.input", return_value="2,1"):
        assert interactive_multi_select("Select models", options) == [
            "deepseek::deepseek-chat",
            "openai::gpt-4o",
        ]

    with patch("builtins.input", return_value=""):
        assert interactive_multi_select("Select models", options) is None


def test_interactive_multi_select_tty_navigation_and_scroll() -> None:
    options = [(f"model-{index}", f"model-{index}", "") for index in range(30)]
    with create_pipe_input() as pipe_input:
        pipe_input.send_bytes(b"\x1b[B" * 22 + b"\r")
        assert (
            interactive_multi_select(
                "Select models",
                options,
                _input=pipe_input,
                _output=DummyOutput(),
            )
            == []
        )


def test_interactive_select_search_and_cancel() -> None:
    options = [
        ("opt_1", "Option One", "First item"),
        ("opt_2", "Option Two", "Second item"),
    ]
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("scond\r")
        assert (
            interactive_select(
                "Test Title",
                options,
                _input=pipe_input,
                _output=DummyOutput(),
            )
            == "opt_2"
        )

    with create_pipe_input() as pipe_input:
        pipe_input.send_bytes(b"\x1b")
        assert (
            interactive_select(
                "Test Title",
                options,
                _input=pipe_input,
                _output=DummyOutput(),
            )
            is None
        )


def test_interactive_select_delete_requires_list_focus() -> None:
    deleted: list[str] = []
    with create_pipe_input() as pipe_input:
        pipe_input.send_bytes(b"\td\r\x1b")
        assert (
            interactive_select(
                "Test Title",
                [("opt_1", "Option One", ""), ("opt_2", "Option Two", "")],
                on_delete=deleted.append,
                _input=pipe_input,
                _output=DummyOutput(),
            )
            is None
        )
    assert deleted == ["opt_1"]


@pytest.mark.asyncio
async def test_interactive_select_works_inside_async_loop() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("two\r")
        assert (
            interactive_select(
                "Test Title",
                [("one", "One", ""), ("two", "Two", "")],
                _input=pipe_input,
                _output=DummyOutput(),
            )
            == "two"
        )


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


def test_discover_gemini_models_uses_native_api_contract() -> None:
    from mia_agent.auth.config import discover_provider_models

    response = MagicMock(
        status_code=200,
        json=lambda: {
            "models": [
                {"name": "models/gemini-live", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-embed", "supportedGenerationMethods": ["embedContent"]},
            ]
        },
    )
    with patch("httpx.get", return_value=response) as get:
        models = discover_provider_models("gemini", api_key="gemini-key")

    assert models == ["gemini-live"]
    args = get.call_args
    assert args.args[0] == "https://generativelanguage.googleapis.com/v1beta/models"
    assert args.kwargs["params"]["key"] == "gemini-key"


def test_discover_rejected_credentials_do_not_show_static_models() -> None:
    from mia_agent.auth.config import discover_provider_models

    with patch("httpx.get", return_value=MagicMock(status_code=401)):
        assert discover_provider_models("openai", api_key="revoked-key") == []


def test_discover_provider_models_live_and_fallback() -> None:
    """Verify discover_provider_models parses /models response and falls back when offline."""
    from mia_agent.auth.config import discover_provider_models

    # 1. Successful HTTP GET /models discovery
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"id": "live-model-alpha"}, {"id": "live-model-beta"}]},
        )
        models = discover_provider_models("openrouter", api_key="sk-live-test")
        assert "live-model-alpha" in models
        assert "live-model-beta" in models

    # 2. Offline / error fallback
    with patch("httpx.get", side_effect=Exception("offline")):
        fallback = discover_provider_models("openai")
        assert "gpt-4o" in fallback


def test_rich_stream_status_transitions() -> None:
    """Verify RichStreamRenderer correctly starts and stops status indicators during turns."""
    from rich.console import Console

    from mia_agent.events import (
        AssistantChunkEvent,
        ToolCallEvent,
        ToolResultEvent,
        TurnCompleteEvent,
        TurnStartEvent,
    )
    from mia_cli.renderers.rich_stream import RichStreamRenderer

    console = Console(force_terminal=True)
    renderer = RichStreamRenderer(console=console)

    # Turn Start
    renderer.on_event(TurnStartEvent(turn_id="turn_1", user_input="hello"))
    assert renderer._active_status is not None

    # Thinking Chunk
    renderer.on_event(AssistantChunkEvent(thought_delta="pondering problem"))
    assert renderer._active_status is not None

    # Text Chunk (clears status)
    renderer.on_event(AssistantChunkEvent(delta_text="Hello world!"))
    assert renderer._active_status is None

    # Tool Call
    renderer.on_event(
        ToolCallEvent(call_id="call_1", tool_name="read_file", arguments={"path": "main.py"})
    )
    assert renderer._active_status is not None

    # Tool Result
    renderer.on_event(
        ToolResultEvent(
            call_id="call_1", tool_name="read_file", output="code content", duration_ms=10.0
        )
    )
    # Returns to thinking status
    assert renderer._active_status is not None

    # Turn Complete
    renderer.on_event(TurnCompleteEvent(total_steps=1, total_cost_usd=0.001))
    assert renderer._active_status is None


@pytest.mark.asyncio
async def test_repl_handles_cancellation_truthfully(tmp_path: Path) -> None:
    from mia_ai.providers.base import LLMProvider
    from mia_ai.types import ChatMessage, StreamChunk, ToolDefinition

    started = asyncio.Event()

    class BlockingProvider(LLMProvider):
        async def stream(
            self,
            *,
            model: str,
            messages: list[ChatMessage],
            tools: list[ToolDefinition] | None = None,
            system: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ):
            started.set()
            await asyncio.Event().wait()
            yield StreamChunk(type="finish")

    repl = MiaREPL(cwd=tmp_path, custom_provider=BlockingProvider())
    repl.console = Console(record=True, width=120)

    task = asyncio.create_task(repl.execute_turn("block me"))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    task.cancel()

    await task
    output = repl.console.export_text()
    assert "Turn halted by user (Ctrl+C)" in output


@pytest.mark.asyncio
async def test_repl_uses_run_request_and_closeable_stream(tmp_path: Path) -> None:
    from mia_agent.events import TurnCompleteEvent
    from mia_agent.runtime_events import AgentEventEnvelope
    from mia_agent.runtime_models import RunRequest

    received_requests: list[RunRequest] = []
    closed = False

    async def mock_run(req: RunRequest, **kwargs: object):
        nonlocal closed
        received_requests.append(req)
        try:
            yield AgentEventEnvelope(
                run_id="r1",
                task_id="root",
                agent_id="mia",
                session_id="s1",
                event=TurnCompleteEvent(total_steps=1, total_cost_usd=0.0, stop_reason="stop"),
            )
        finally:
            closed = True

    repl = MiaREPL(cwd=tmp_path)
    repl.agent_runner.run = mock_run  # type: ignore[method-assign]
    await repl.execute_turn("Test prompt")
    assert len(received_requests) == 1
    assert received_requests[0].prompt_text == "Test prompt"
    assert closed is True


def test_essential_repl_interaction_matrix_keybindings_and_shortcuts() -> None:
    from prompt_toolkit.keys import Keys

    session = LivePromptSession()

    # Essential shortcuts map to expected commands
    expected_shortcuts = {
        Keys.ControlO: "/inspect",
        Keys.ControlT: "/thinking",
        Keys.BackTab: "/thinking",
        Keys.ControlL: "/model",
        Keys.ControlP: "/model next",
    }
    for key, expected_command in expected_shortcuts.items():
        binding = session.bindings.get_bindings_for_keys((key,))[-1]
        buffer = MagicMock()
        event = MagicMock(current_buffer=buffer)
        binding.handler(event)
        assert buffer.text == expected_command
        buffer.validate_and_handle.assert_called_once()

    # Clear/cancel: Ctrl+C resets current buffer
    c_c_binding = session.bindings.get_bindings_for_keys((Keys.ControlC,))[-1]
    buf_c = MagicMock()
    c_c_binding.handler(MagicMock(current_buffer=buf_c))
    buf_c.reset.assert_called_once()

    # Newline: Ctrl+J and Escape+Enter insert literal newline
    c_j_binding = session.bindings.get_bindings_for_keys((Keys.ControlJ,))[-1]
    buf_j = MagicMock()
    c_j_binding.handler(MagicMock(current_buffer=buf_j))
    buf_j.insert_text.assert_called_once_with("\n")

    esc_enter_binding = session.bindings.get_bindings_for_keys((Keys.Escape, Keys.Enter))[-1]
    buf_esc_enter = MagicMock()
    esc_enter_binding.handler(MagicMock(current_buffer=buf_esc_enter))
    buf_esc_enter.insert_text.assert_called_once_with("\n")


def test_essential_repl_non_tty_prompt_and_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    session = LivePromptSession()

    # 1. Non-TTY read_prompt returns stripped input without hanging
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "  my non-tty prompt  \n")
    assert session.read_prompt("› ") == "my non-tty prompt"

    # 2. Non-TTY read_prompt propagates EOFError
    def raise_eof(prompt=""):
        raise EOFError()

    monkeypatch.setattr("builtins.input", raise_eof)
    with pytest.raises(EOFError):
        session.read_prompt("› ")

    # 3. Non-TTY read_prompt handles KeyboardInterrupt cleanly
    def raise_sigint(prompt=""):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", raise_sigint)
    assert session.read_prompt("› ") == ""

    # 4. Non-TTY interactive_select supports default, selection by number/name, and explicit cancellation
    options = [("opt_1", "First Option", "Desc 1"), ("opt_2", "Second Option", "Desc 2")]

    # Default on empty Enter
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert interactive_select("Choose", options, default_idx=0) == "opt_1"

    # Number selection
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")
    assert interactive_select("Choose", options, default_idx=0) == "opt_2"

    # Name selection
    monkeypatch.setattr("builtins.input", lambda prompt="": "second option")
    assert interactive_select("Choose", options, default_idx=0) == "opt_2"

    # Explicit cancel with 'q' or 'cancel' returns None
    monkeypatch.setattr("builtins.input", lambda prompt="": "q")
    assert interactive_select("Choose", options, default_idx=0) is None

    monkeypatch.setattr("builtins.input", lambda prompt="": "cancel")
    assert interactive_select("Choose", options, default_idx=0) is None


def test_essential_repl_commands_and_quit_contract(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)

    # Help and aliases return True and do not exit
    assert repl.handle_slash_command("/help") is True
    assert repl.handle_slash_command("/?") is True

    # Quit and aliases return False (signals exit)
    assert repl.handle_slash_command("/quit") is False
    assert repl.handle_slash_command("/exit") is False

    # Inspect calls audit log renderer
    with patch.object(repl.stream_renderer, "render_audit_log") as mock_render:
        assert repl.handle_slash_command("/inspect") is True
        mock_render.assert_called_once()


def test_queue_help_documents_portable_fallback(tmp_path: Path) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)

    repl.handle_slash_command("/help")
    output = repl.console.export_text()
    assert "/queue" in output
    assert "Ctrl+Q" in output
    assert "Enter" in output


def test_help_discovery_exposes_essential_keyboard_and_command_alternatives(
    tmp_path: Path,
) -> None:
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)

    repl.handle_slash_command("/help")
    output = repl.console.export_text()

    # Canonical command table is present
    assert "17 Canonical Slash Commands" in output

    # Essential keyboard actions and command equivalents are visible in text without color/icons
    assert "Essential Actions & Keyboard Equivalents" in output
    assert "Submit prompt" in output
    assert "Enter" in output
    assert "Clear prompt / Cancel" in output
    assert "Ctrl+C" in output
    assert "Switch Agent" in output
    assert "/agent" in output
    assert "Switch model" in output
    assert "Ctrl+L" in output
    assert "Cycle scoped models" in output
    assert "Ctrl+P" in output
    assert "Inspect audit details" in output
    assert "Ctrl+O" in output
    assert "Session tree navigator" in output
    assert "Esc Esc" in output
    assert "Quit / Exit" in output
    assert "/quit" in output


def test_truthful_state_presentation_and_measured_metrics() -> None:
    # 1. Unavailable window_tokens is not presented as measured capacity
    tb_no_window = format_status_toolbar(
        workspace_name="mia_proj",
        model_name="mimo-v2.5",
        tokens=12500,
        window_tokens=None,
        thinking_enabled=False,
        agent_id="mia",
        session_id="session_test123",
        run_state="idle",
    )
    val = tb_no_window.value
    assert "128k" not in val
    assert "%" not in val
    assert "12.5k" in val
    assert "mia" in val
    assert "session_test123" in val
    assert "[idle]" in val

    # 2. When window_tokens IS provided, capacity and percentage are shown
    tb_with_window = format_status_toolbar(
        workspace_name="mia_proj",
        model_name="mimo-v2.5",
        tokens=12500,
        window_tokens=128000,
        thinking_enabled=False,
        agent_id="mia",
        session_id="session_test123",
        run_state="running",
    )
    val2 = tb_with_window.value
    assert "12.5k/128k" in val2
    assert "9.8%" in val2
    assert "[running]" in val2


@pytest.mark.asyncio
async def test_stream_and_tool_grouping_readable_in_scrollback_without_duplicates(
    tmp_path: Path,
) -> None:
    from mia_agent.events import (
        AssistantChunkEvent,
        StepEndEvent,
        StepStartEvent,
        ToolCallEvent,
        ToolResultEvent,
        TurnCompleteEvent,
        TurnStartEvent,
    )
    from mia_agent.runtime_events import AgentEventEnvelope

    async def mock_run(*args: object, **kwargs: object):
        events = [
            TurnStartEvent(turn_index=1, user_prompt="test prompt"),
            StepStartEvent(step_index=1),
            AssistantChunkEvent(delta_text="Thinking through task. "),
            ToolCallEvent(call_id="c1", tool_name="read_file", arguments={"path": "doc.txt"}),
            ToolResultEvent(
                call_id="c1",
                tool_name="read_file",
                output="file content",
                is_error=False,
                duration_ms=5.0,
            ),
            AssistantChunkEvent(delta_text="Finished reading doc."),
            StepEndEvent(step_index=1, input_tokens=10, output_tokens=20),
            TurnCompleteEvent(total_steps=1, total_cost_usd=0.0001, stop_reason="stop"),
        ]
        for ev in events:
            yield AgentEventEnvelope(
                run_id="r1",
                task_id="root",
                agent_id="mia",
                session_id="s1",
                event=ev,
            )

    repl = MiaREPL(cwd=tmp_path)
    repl.console = Console(record=True, width=120)
    repl.stream_renderer.console = repl.console
    repl.agent_runner.run = mock_run  # type: ignore[method-assign]

    await repl.execute_turn("test prompt")
    output = repl.console.export_text()

    assert "Thinking through task." in output
    assert "read_file" in output
    assert "Finished reading doc." in output
    assert "Turn completed" in output
    # Ensure no duplicate message replay
    assert output.count("Finished reading doc.") == 1


@pytest.mark.asyncio
async def test_terminal_truth_preserves_error_and_cancellation_outcomes(
    tmp_path: Path,
) -> None:
    from mia_agent.runtime_events import AgentEventEnvelope, RunErrorEvent
    from mia_cli.renderers.rich_stream import RichStreamRenderer

    # Case A: RunErrorEvent with failure
    async def mock_fail_run(*args: object, **kwargs: object):
        yield AgentEventEnvelope(
            run_id="r1",
            task_id="root",
            agent_id="mia",
            session_id="s1",
            event=RunErrorEvent(
                stage="agent", error="rate limit hit", code="agent_error", cancelled=False
            ),
        )

    repl_fail = MiaREPL(cwd=tmp_path)
    rec_console_fail = Console(
        record=True, width=120, force_terminal=False, no_color=True, highlight=False
    )
    repl_fail.console = rec_console_fail
    repl_fail.stream_renderer = RichStreamRenderer(console=rec_console_fail, plain_mode=True)
    repl_fail.agent_runner.run = mock_fail_run  # type: ignore[method-assign]

    await repl_fail.execute_turn("trigger fail")
    fail_output = rec_console_fail.export_text()
    assert "[error] Run error (agent): rate limit hit" in fail_output
    assert "Turn completed" not in fail_output

    # Case B: RunErrorEvent with cancelled=True
    async def mock_cancel_run(*args: object, **kwargs: object):
        yield AgentEventEnvelope(
            run_id="r2",
            task_id="root",
            agent_id="mia",
            session_id="s1",
            event=RunErrorEvent(
                stage="runtime", error="user cancelled", code="cancelled", cancelled=True
            ),
        )

    repl_cancel = MiaREPL(cwd=tmp_path)
    rec_console_cancel = Console(
        record=True, width=120, force_terminal=False, no_color=True, highlight=False
    )
    repl_cancel.console = rec_console_cancel
    repl_cancel.stream_renderer = RichStreamRenderer(console=rec_console_cancel, plain_mode=True)
    repl_cancel.agent_runner.run = mock_cancel_run  # type: ignore[method-assign]

    await repl_cancel.execute_turn("trigger cancel")
    cancel_output = rec_console_cancel.export_text()
    assert "[cancelled] Run cancelled (runtime): user cancelled" in cancel_output
    assert "Turn completed" not in cancel_output
    assert "Run error" not in cancel_output

    # Case C: Tool approval request has non-color semantic cue
    from mia_middleware.access import ApprovalRequest

    req = ApprovalRequest(
        effect="side-effecting",
        tool_name="bash",
        arguments={"command": "rm -rf /"},
        agent_id="mia",
    )
    with patch("builtins.input", return_value="n"):
        rec_console_approval = Console(record=True, width=120)
        repl_fail.console = rec_console_approval
        repl_fail._request_tool_approval(req)
        appr_output = rec_console_approval.export_text()
        assert "[approval-required]" in appr_output


def test_help_and_command_discovery_distinguishes_busy_availability(
    tmp_path: Path,
) -> None:
    """SC-e13s03-P1-01: Help distinguishes actions unavailable while busy."""
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)

    repl.handle_slash_command("/help")
    output = repl.console.export_text()

    assert "Availability" in output
    assert "Idle only" in output
    assert "Always" in output


def test_selectors_and_session_inspection_preserve_draft(tmp_path: Path) -> None:
    """SC-e13s03-P1-02: Selectors and session inspection preserve the prompt draft."""
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)
    repl.prompt_session.set_draft("persisted draft text")

    # 1. Model picker preserves draft
    repl.scoped_models = ["openai::gpt-4o"]
    repl.available_model_sources = {"openai::gpt-4o": "openai"}
    with patch("mia_cli.repl.interactive_select", return_value=None):
        repl.interactive_model_picker()
    assert repl.prompt_session.get_draft() == "persisted draft text"

    # 2. Inspect preserves draft
    with patch.object(repl.stream_renderer, "render_audit_log"):
        repl.handle_slash_command("/inspect")
    assert repl.prompt_session.get_draft() == "persisted draft text"

    # 3. Session resumer preserves draft
    with patch("mia_cli.repl.interactive_select", return_value=None):
        repl.interactive_session_resumer()
    assert repl.prompt_session.get_draft() == "persisted draft text"


def test_busy_state_retargeting_rejected_and_cannot_mutate_active_run(
    tmp_path: Path,
) -> None:
    """SC-e13s03-P1-03: Active Run cannot be retargeted by Agent, model, or Session changes."""
    repl = MiaREPL(cwd=tmp_path, custom_provider=MockProvider())
    repl.console = Console(record=True, width=120)
    repl.agent_id = "mia"
    repl.model_name = "mimo-v2.5"
    orig_session = repl.session_id

    # Mark REPL busy (active run)
    repl.prompt_session.is_busy = True

    # 1. Reject /agent change
    repl.handle_slash_command("/agent researcher")
    out = repl.console.export_text()
    assert "Cannot change /agent while a Run is active" in out
    assert repl.agent_id == "mia"

    # 2. Reject /model change
    repl.console = Console(record=True, width=120)
    repl.handle_slash_command("/model gpt-4o")
    out = repl.console.export_text()
    assert "Cannot change /model while a Run is active" in out
    assert repl.model_name == "mimo-v2.5"

    # 3. Reject /resume change
    repl.console = Console(record=True, width=120)
    repl.handle_slash_command("/resume other_session")
    out = repl.console.export_text()
    assert "Cannot change /resume while a Run is active" in out
    assert repl.session_id == orig_session

    # 4. Reject /tree change
    repl.console = Console(record=True, width=120)
    repl.handle_slash_command("/tree")
    out = repl.console.export_text()
    assert "Cannot change /tree while a Run is active" in out


@pytest.mark.asyncio
async def test_repl_loop_concurrent_draft_composition_and_explicit_later_submission(
    tmp_path: Path,
) -> None:
    """SC-e13s02 end-to-end: User composes draft during active Run; Enter does not submit while busy; explicit Enter submits after completion."""
    from collections.abc import AsyncIterator

    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from mia_ai.types import ChatMessage, StreamChunk, ToolDefinition

    class ControlledProvider(MockProvider):
        def __init__(self) -> None:
            super().__init__()
            self.turn1_started = asyncio.Event()
            self.turn1_release = asyncio.Event()
            self.turn2_started = asyncio.Event()

        async def stream(
            self,
            *,
            model: str,
            messages: list[ChatMessage],
            tools: list[ToolDefinition] | None = None,
            system: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> AsyncIterator[StreamChunk]:
            if not self.turn1_started.is_set():
                self.turn1_started.set()
                await self.turn1_release.wait()
            else:
                self.turn2_started.set()
            async for chunk in super().stream(
                model=model,
                messages=messages,
                tools=tools,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk

    provider = ControlledProvider()
    provider.queue_text_response("Turn 1 complete")
    provider.queue_text_response("Turn 2 complete")

    with create_pipe_input() as pipe:
        repl = MiaREPL(
            cwd=tmp_path,
            custom_provider=provider,
            prompt_input=pipe,
            prompt_output=DummyOutput(),
        )
        repl.console = Console(record=True, width=120)

        loop_task = asyncio.create_task(repl.run_async())

        # 1. Send first prompt to start Turn 1
        pipe.send_text("first prompt\r")
        await asyncio.wait_for(provider.turn1_started.wait(), timeout=3.0)

        # Active turn is running and busy
        assert repl.prompt_session.is_busy is True
        assert repl._run_state == "running"

        # 2. While Turn 1 is running, compose draft prompt and press Enter
        pipe.send_text("draft prompt\r")
        await asyncio.sleep(0.05)

        # Draft is captured, but NOT submitted (no queue, no concurrent turn started)
        assert repl.prompt_session.get_draft() == "draft prompt"
        assert not provider.turn2_started.is_set()

        # 3. Release Turn 1 to complete
        provider.turn1_release.set()
        await asyncio.sleep(0.1)

        # Turn 1 finished; REPL is now idle and draft is preserved
        assert repl.prompt_session.is_busy is False
        assert repl._run_state == "idle"
        assert repl.prompt_session.get_draft() == "draft prompt"
        assert not provider.turn2_started.is_set()

        # 4. Now press Enter to explicitly submit the composed draft
        pipe.send_text("\r")
        await asyncio.wait_for(provider.turn2_started.wait(), timeout=3.0)

        # Cleanly exit REPL loop
        pipe.send_text("/quit\r")
        await asyncio.wait_for(loop_task, timeout=3.0)


@pytest.mark.asyncio
async def test_repl_loop_ctrl_c_cancels_active_run_and_preserves_draft(
    tmp_path: Path,
) -> None:
    """SC-e13s02 end-to-end: Ctrl+C during active Run cancels the execution and preserves the composed draft."""
    from collections.abc import AsyncIterator

    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from mia_ai.types import ChatMessage, StreamChunk, ToolDefinition

    class CancellableProvider(MockProvider):
        def __init__(self) -> None:
            super().__init__()
            self.turn_started = asyncio.Event()

        async def stream(
            self,
            *,
            model: str,
            messages: list[ChatMessage],
            tools: list[ToolDefinition] | None = None,
            system: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> AsyncIterator[StreamChunk]:
            self.turn_started.set()
            # Wait until cancelled
            await asyncio.sleep(30.0)
            async for chunk in super().stream(
                model=model,
                messages=messages,
                tools=tools,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk

    provider = CancellableProvider()
    provider.queue_text_response("Will not finish")

    with create_pipe_input() as pipe:
        repl = MiaREPL(
            model="mimo-v2.5",
            cwd=tmp_path,
            custom_provider=provider,
            prompt_input=pipe,
            prompt_output=DummyOutput(),
        )
        repl.console = Console(record=True, width=120)

        loop_task = asyncio.create_task(repl.run_async())

        # Start active turn
        pipe.send_text("slow turn prompt\r")
        await asyncio.wait_for(provider.turn_started.wait(), timeout=3.0)

        assert repl.prompt_session.is_busy is True

        # Compose draft during active run
        pipe.send_text("in-progress draft\r")
        await asyncio.sleep(0.05)
        assert repl.prompt_session.get_draft() == "in-progress draft"

        # Send Ctrl+C to cancel the active turn
        pipe.send_text("\x03")
        await asyncio.sleep(0.1)

        # Run halted, cancellation reached active run, REPL is back to idle
        assert repl.prompt_session.is_busy is False
        assert repl._run_state == "idle"

        # Draft remains intact
        assert repl.prompt_session.get_draft() == "in-progress draft"
        output = repl.console.export_text()
        assert "Turn halted by user (Ctrl+C)" in output

        # Exit loop
        pipe.send_text("\x03/quit\r")
        await asyncio.wait_for(loop_task, timeout=3.0)


@pytest.mark.asyncio
async def test_repl_loop_approval_remains_distinct_and_preserves_draft(
    tmp_path: Path,
) -> None:
    """SC-e13s02 end-to-end: Tool approval prompt does not consume the composed draft."""
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from mia_middleware.access import ApprovalRequest

    with create_pipe_input() as pipe:
        repl = MiaREPL(
            cwd=tmp_path,
            custom_provider=MockProvider(),
            prompt_input=pipe,
            prompt_output=DummyOutput(),
        )
        repl.console = Console(record=True, width=120)
        repl.prompt_session.set_draft("composed user draft")

        req = ApprovalRequest(
            effect="side-effecting",
            tool_name="write_file",
            arguments={"path": "test.txt", "content": "hello"},
            agent_id="mia",
        )

        with patch("builtins.input", return_value="y"):
            approved = repl._request_tool_approval(req)
            assert approved is True

        # Draft text was NOT consumed as the approval answer
        assert repl.prompt_session.get_draft() == "composed user draft"
