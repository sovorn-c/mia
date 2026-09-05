"""Tests for Slice 8: Typer CLI and Rich Stream Renderer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.events import (
    AgentErrorEvent,
    AssistantChunkEvent,
    StepEndEvent,
    StepStartEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnCompleteEvent,
    TurnStartEvent,
)
from mia_cli.main import app
from mia_cli.renderers.rich_stream import RichStreamRenderer

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Mia" in result.stdout or "Usage" in result.stdout


def test_top_level_session_option_resumes_interactive_repl() -> None:
    with patch("mia_cli.repl.MiaREPL") as repl_class:
        result = runner.invoke(app, ["--session", "session_abc123"])

    assert result.exit_code == 0
    repl_class.assert_called_once_with(
        model=None,
        agent="mia",
        session_id="session_abc123",
    )
    repl_class.return_value.run.assert_called_once_with()


def test_top_level_repl_uses_selected_agent(tmp_path: Path) -> None:
    manager = AgentManager(agents_dir=tmp_path / "agents")
    manager.create_agent("researcher", display_name="Researcher")
    manager.set_default("researcher")
    with (
        patch("mia_cli.main.AgentManager", return_value=manager),
        patch("mia_cli.repl.MiaREPL") as repl_class,
    ):
        result = runner.invoke(app, [])

    assert result.exit_code == 0
    repl_class.assert_called_once_with(
        model=None,
        agent="researcher",
        session_id=None,
    )


def test_top_level_session_rejects_path_without_traceback() -> None:
    result = runner.invoke(app, ["--session", "../outside"])

    assert result.exit_code == 2
    assert "Invalid value for --session" in result.output
    assert "Traceback" not in result.output


def test_cli_run_exposes_agent_selection() -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--agent" in result.stdout


def test_cli_agent_lifecycle(tmp_path: Path) -> None:
    manager = AgentManager(
        agents_dir=tmp_path / "agents",
    )
    with patch("mia_cli.main.AgentManager", return_value=manager):
        created = runner.invoke(
            app,
            ["agent", "create", "researcher", "--name", "Researcher", "--tools", "read_file"],
        )
        listed = runner.invoke(app, ["agent", "list"])
        shown = runner.invoke(app, ["agent", "show", "researcher"])
        selected = runner.invoke(app, ["agent", "use", "researcher"])

    assert created.exit_code == 0
    assert "researcher" in listed.stdout
    assert "Researcher" in shown.stdout
    assert selected.exit_code == 0
    assert manager.default_agent().agent_id == "researcher"


def test_cli_login_flow(tmp_path: Path) -> None:
    cred_path = tmp_path / "credentials.json"
    with patch("mia_agent.auth.credentials.default_credentials_path", return_value=cred_path):
        result = runner.invoke(app, ["login", "anthropic", "--key", "sk-ant-test-cli-key"])
        assert result.exit_code == 0
        assert "Successfully stored" in result.stdout

        store = FileCredentialStore(path=cred_path)
        assert store.get_api_key("anthropic") == "sk-ant-test-cli-key"


def test_rich_stream_renderer_output() -> None:
    renderer = RichStreamRenderer()

    # Feed events
    renderer.on_event(TurnStartEvent(turn_index=1, user_prompt="Hello"))
    renderer.on_event(StepStartEvent(step_index=1))
    renderer.on_event(AssistantChunkEvent(thought_delta="Thinking about greeting..."))
    renderer.on_event(AssistantChunkEvent(delta_text="Hello world!"))
    renderer.on_event(
        ToolCallEvent(call_id="c1", tool_name="read_file", arguments={"path": "README.md"})
    )
    renderer.on_event(
        ToolResultEvent(
            call_id="c1",
            tool_name="read_file",
            output="File content",
            is_error=False,
            duration_ms=15.0,
        )
    )
    renderer.on_event(StepEndEvent(step_index=1, input_tokens=10, output_tokens=5))
    renderer.on_event(TurnCompleteEvent(total_steps=1, total_cost_usd=0.0001, stop_reason="stop"))

    assert renderer.turn_count == 1


def test_cli_run_agent_loop_uses_run_request_and_closeable_stream() -> None:
    import asyncio

    from mia_agent.runtime_events import AgentEventEnvelope
    from mia_agent.runtime_models import RunRequest
    from mia_cli.main import _run_agent_loop

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

    with patch("mia_cli.main.AgentRunner.run", side_effect=mock_run):
        ok = asyncio.run(_run_agent_loop("Hello CLI", agent_name="mia"))

    assert ok is True
    assert len(received_requests) == 1
    assert received_requests[0].prompt_text == "Hello CLI"
    assert received_requests[0].agent_id == "mia"
    assert closed is True


def test_presentation_mode_selection_contract() -> None:
    from rich.console import Console

    from mia_cli.renderers.rich_stream import resolve_plain_mode

    # Explicit --plain flag overrides everything
    assert resolve_plain_mode(plain_option=True, environ={}) is True
    assert resolve_plain_mode(plain_option=True, console=Console(force_terminal=True)) is True

    # NO_COLOR environment variable activates plain mode
    assert resolve_plain_mode(plain_option=False, environ={"NO_COLOR": "1"}) is True
    assert resolve_plain_mode(plain_option=False, environ={"NO_COLOR": "true"}) is True
    # Empty NO_COLOR string does not activate plain mode
    term_console = Console(force_terminal=True, color_system="truecolor")
    assert resolve_plain_mode(plain_option=False, console=term_console, environ={"NO_COLOR": ""}) is False

    # Non-terminal console activates plain mode
    non_term_console = Console(force_terminal=False)
    assert resolve_plain_mode(plain_option=False, console=non_term_console, environ={}) is True


def test_cli_run_help_exposes_plain_option() -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--plain" in result.stdout


def test_renderer_threads_plain_mode_and_suppresses_live_status() -> None:
    from rich.console import Console

    from mia_cli.renderers.rich_stream import RichStreamRenderer

    # Interactive renderer creates live status when terminal
    term_console = Console(force_terminal=True)
    interactive_renderer = RichStreamRenderer(console=term_console, plain_mode=False)
    assert interactive_renderer.plain_mode is False
    interactive_renderer.start_turn()
    assert interactive_renderer._active_status is not None
    interactive_renderer._stop_status()

    # Plain renderer suppresses live status completely
    plain_renderer = RichStreamRenderer(console=term_console, plain_mode=True)
    assert plain_renderer.plain_mode is True
    plain_renderer.start_turn()
    assert plain_renderer._active_status is None


def test_run_command_threads_plain_mode_flag(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    with patch("mia_cli.main._run_agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = True
        res = runner.invoke(app, ["run", "-p", "Check plain", "--plain"])
        assert res.exit_code == 0
        assert mock_loop.call_args is not None
        assert mock_loop.call_args.kwargs.get("plain") is True


def test_plain_mode_emits_semantic_status_labels_for_success_and_error() -> None:
    from rich.console import Console

    from mia_cli.renderers.rich_stream import RichStreamRenderer

    rec_console = Console(record=True, force_terminal=False, no_color=True, highlight=False)
    renderer = RichStreamRenderer(console=rec_console, plain_mode=True)

    renderer.on_event(TurnStartEvent(turn_index=1, user_prompt="Read and execute"))
    renderer.on_event(StepStartEvent(step_index=1))
    renderer.on_event(
        ToolCallEvent(call_id="c1", tool_name="read_file", arguments={"path": "README.md"})
    )
    renderer.on_event(
        ToolResultEvent(
            call_id="c1",
            tool_name="read_file",
            output="line 1\nline 2",
            is_error=False,
            duration_ms=10.0,
        )
    )
    renderer.on_event(
        ToolCallEvent(call_id="c2", tool_name="bash", arguments={"command": "cat non_existent"})
    )
    renderer.on_event(
        ToolResultEvent(
            call_id="c2",
            tool_name="bash",
            output="file not found",
            is_error=True,
            duration_ms=12.0,
        )
    )
    renderer.on_event(AgentErrorEvent(error="failed to complete step"))
    renderer.on_event(TurnCompleteEvent(total_steps=2, total_cost_usd=0.001, stop_reason="error"))

    output = rec_console.export_text()

    # Plain output must contain explicit semantic labels
    assert "[running] read_file" in output
    assert "[ok] read_file" in output
    assert "[running] bash" in output
    assert "[error] bash" in output
    assert "[error] Agent error: failed to complete step" in output
    assert "[ok] Turn completed" in output

    # Must contain no ANSI escape sequences
    assert "\x1b[" not in output


def test_run_command_plain_mode_preserves_exit_codes_on_failure_and_success() -> None:
    from unittest.mock import AsyncMock

    with patch("mia_cli.main._run_agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = False
        res_fail = runner.invoke(app, ["run", "-p", "Fail test", "--plain"])
        assert res_fail.exit_code == 1

        mock_loop.return_value = True
        res_ok = runner.invoke(app, ["run", "-p", "Ok test", "--plain"])
        assert res_ok.exit_code == 0



