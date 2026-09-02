"""Tests for Slice 8: Typer CLI and Rich Stream Renderer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.events import (
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
        profile="coding",
        session_id="session_abc123",
    )
    repl_class.return_value.run.assert_called_once_with()


def test_top_level_session_rejects_path_without_traceback() -> None:
    result = runner.invoke(app, ["--session", "../outside"])

    assert result.exit_code == 2
    assert "Invalid value for --session" in result.output
    assert "Traceback" not in result.output


def test_cli_run_exposes_mode_selection() -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.stdout


def test_cli_agent_lifecycle(tmp_path: Path) -> None:
    manager = AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
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


def test_cli_profile_list() -> None:
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "coding" in result.stdout
    assert "architect" in result.stdout
    assert "minimal" in result.stdout


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
