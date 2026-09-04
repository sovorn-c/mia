"""CLI tests for local diagnostic inspection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.diagnostics import DiagnosticRecord, DiagnosticStore
from mia_cli.main import app

runner = CliRunner()


def test_diagnostics_cli_empty_store_succeeds(tmp_path: Path) -> None:
    """Empty diagnostic store returns exit code 0."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["diagnostics"])
    assert res.exit_code == 0
    assert "no diagnostic records" in res.stdout.lower() or "records" in res.stdout.lower()


def test_diagnostics_cli_filters_by_source_and_agent(tmp_path: Path) -> None:
    """Filtering by source and agent returns matching records with exit code 0."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    store = DiagnosticStore(path=manager.get_diagnostics_path())

    r1 = DiagnosticRecord.create(
        source="tool",
        agent_id="mia",
        tool_name="read_file",
        action="execute",
        outcome="success",
    )
    r2 = DiagnosticRecord.create(
        source="run",
        agent_id="mia",
        action="finalize",
        outcome="success",
    )
    r3 = DiagnosticRecord.create(
        source="plugin",
        agent_id="other_agent",
        plugin_id="notes",
        action="cleanup",
        outcome="failed",
    )
    store.append(r1)
    store.append(r2)
    store.append(r3)

    with patch("mia_cli.main.AgentManager", return_value=manager):
        # Filter by source
        tool_res = runner.invoke(app, ["diagnostics", "--source", "tool"])
        assert tool_res.exit_code == 0
        assert "read_file" in tool_res.stdout
        assert "notes" not in tool_res.stdout

        # Filter by agent
        agent_res = runner.invoke(app, ["diagnostics", "--agent", "other_agent"])
        assert agent_res.exit_code == 0
        assert "other_agent" in agent_res.stdout
        assert "read_file" not in agent_res.stdout


def test_diagnostics_cli_invalid_source_filter_fails(tmp_path: Path) -> None:
    """Invalid source filter returns non-zero exit code."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["diagnostics", "--source", "invalid_source"])
    assert res.exit_code != 0
    assert "invalid" in res.stdout.lower() or "source" in res.stdout.lower()


def test_diagnostics_cli_malformed_store_fails(tmp_path: Path) -> None:
    """Corrupted diagnostic store returns non-zero exit code."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    diag_path = manager.get_diagnostics_path()
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    diag_path.write_text("not json\n", encoding="utf-8")

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["diagnostics"])
    assert res.exit_code != 0
    assert "malformed" in res.stdout.lower() or "error" in res.stdout.lower()


def test_diagnostics_cli_secret_free_output(tmp_path: Path) -> None:
    """Diagnostic CLI output does not display credential-like values."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    store = DiagnosticStore(path=manager.get_diagnostics_path())

    rec = DiagnosticRecord.create(
        source="tool",
        agent_id="mia",
        tool_name="bash",
        details={"api_key": "sk-secret12345"},
        error="Failed token: ghp_token12345",
    )
    store.append(rec)

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["diagnostics"])
    assert res.exit_code == 0
    assert "sk-secret12345" not in res.stdout
    assert "ghp_token12345" not in res.stdout
    assert "[REDACTED]" in res.stdout
