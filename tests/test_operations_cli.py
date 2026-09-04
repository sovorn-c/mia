"""CLI tests for local data locations, backup, and restore commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.operations import create_backup
from mia_cli.main import app

runner = CliRunner()


def test_cli_data_locations_displays_table_and_no_secrets(tmp_path: Path) -> None:
    """CLI data locations command prints data boundaries without exposing credentials."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    cred_path = tmp_path / "credentials.json"

    secret_key = "sk-super-secret-key-do-not-leak"
    cred_store = FileCredentialStore(path=cred_path)
    cred_store.set_api_key("openai", secret_key)

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    with (
        patch("mia_cli.main.AgentManager", return_value=manager),
        patch("mia_agent.operations.default_credentials_path", return_value=cred_path),
    ):
        res = runner.invoke(app, ["data", "locations"])

    assert res.exit_code == 0
    assert "agents" in res.stdout.lower()
    assert "credentials" in res.stdout.lower()
    assert "diagnostics" in res.stdout.lower()
    assert secret_key not in res.stdout


def test_cli_data_backup_creates_archive(tmp_path: Path) -> None:
    """CLI data backup creates a valid archive and outputs summary."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    archive_path = tmp_path / "out_backup.zip"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["data", "backup", "--output", str(archive_path)])

    assert res.exit_code == 0
    assert archive_path.exists()
    assert "backup" in res.stdout.lower() or "created" in res.stdout.lower()


def test_cli_data_backup_rejects_overwrite_without_flag(tmp_path: Path) -> None:
    """CLI data backup rejects overwriting existing file unless --overwrite is supplied."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    archive_path = tmp_path / "existing.zip"
    archive_path.write_text("already here", encoding="utf-8")

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["data", "backup", "--output", str(archive_path)])

    assert res.exit_code != 0
    assert "exists" in res.stdout.lower() or "error" in res.stdout.lower()
    assert archive_path.read_text(encoding="utf-8") == "already here"


def test_cli_data_restore_dry_run_and_execution(tmp_path: Path) -> None:
    """CLI data restore supports dry-run validation and atomic non-destructive commit."""
    agents_dir = tmp_path / "src_agents"
    diagnostics_dir = tmp_path / "src_diagnostics"
    archive_path = tmp_path / "backup.zip"
    dest_dir = tmp_path / "dest"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    create_backup(manager, archive_path=archive_path)

    # Dry run
    res_dry = runner.invoke(
        app, ["data", "restore", str(archive_path), "--destination", str(dest_dir), "--dry-run"]
    )
    assert res_dry.exit_code == 0
    assert "dry run" in res_dry.stdout.lower() or "valid" in res_dry.stdout.lower()
    assert not dest_dir.exists()

    # Actual restore
    res_real = runner.invoke(
        app, ["data", "restore", str(archive_path), "--destination", str(dest_dir)]
    )
    assert res_real.exit_code == 0
    assert "restored" in res_real.stdout.lower() or "success" in res_real.stdout.lower()
    assert (dest_dir / "agents" / "mia" / "agent.json").exists()


def test_cli_data_restore_invalid_archive_fails(tmp_path: Path) -> None:
    """CLI data restore with corrupt or non-existent archive reports truthful error."""
    dest_dir = tmp_path / "dest"
    bad_archive = tmp_path / "corrupt.zip"
    bad_archive.write_text("not a zip file", encoding="utf-8")

    res = runner.invoke(app, ["data", "restore", str(bad_archive), "--destination", str(dest_dir)])
    assert res.exit_code != 0
    assert (
        "error" in res.stdout.lower()
        or "invalid" in res.stdout.lower()
        or "corrupt" in res.stdout.lower()
    )
