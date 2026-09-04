"""CLI tests for local data recovery verification command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_cli.main import app

runner = CliRunner()


def test_cli_data_verify_clean(tmp_path: Path) -> None:
    """CLI data verify exits 0 and reports clean when all files are valid."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["data", "verify"])

    assert res.exit_code == 0
    assert "clean" in res.stdout.lower()
    assert "0 issues" in res.stdout.lower() or "verified clean" in res.stdout.lower()


def test_cli_data_verify_attention_for_interrupted_writes(tmp_path: Path) -> None:
    """CLI data verify returns exit code 2 and attention status for orphan temp files."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    orphan_file = agents_dir / "mia" / ".atomic_tmp_scratch"
    orphan_bytes = b"partial atomic write content"
    orphan_file.write_bytes(orphan_bytes)

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["data", "verify"])

    assert res.exit_code == 2
    assert "attention" in res.stdout.lower()
    assert "atomic_write" in res.stdout.lower()
    # Read-only verification: orphan file must NOT be deleted or modified
    assert orphan_file.exists()
    assert orphan_file.read_bytes() == orphan_bytes


def test_cli_data_verify_blocked_for_corruption_and_guidance(tmp_path: Path) -> None:
    """CLI data verify returns exit code 1, blocked status, and restore guidance for corrupt data."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    bad_agent = agents_dir / "mia" / "agent.json"
    bad_agent.parent.mkdir(parents=True, exist_ok=True)
    bad_bytes = b'{"agent_id": "mia", INVALID JSON'
    bad_agent.write_bytes(bad_bytes)

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res = runner.invoke(app, ["data", "verify"])

    assert res.exit_code == 1
    assert "blocked" in res.stdout.lower()
    assert "restore" in res.stdout.lower()
    assert "mia data restore" in res.stdout.lower()
    # Read-only verification: file must remain unchanged
    assert bad_agent.read_bytes() == bad_bytes


def test_cli_data_verify_deterministic_and_byte_preserving(tmp_path: Path) -> None:
    """Repeated verification runs produce identical output and preserve all file bytes."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_dir = agents_dir / "mia"
    agent_dir.mkdir(parents=True, exist_ok=True)

    agent_json = agent_dir / "agent.json"
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    orphan_file = agent_dir / ".atomic_tmp_dummy"
    orphan_file.write_bytes(b"temp atomic artifact")

    session_file = agent_dir / "sessions" / "sess-1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_bytes(
        b'{"session_id": "sess-1"}\n{"invalid": interior\n{"valid": "entry"}\n'
    )

    # Snapshot all bytes before runs
    files = [agent_json, orphan_file, session_file]
    snapshots_before = {f: f.read_bytes() for f in files}

    with patch("mia_cli.main.AgentManager", return_value=manager):
        res1 = runner.invoke(app, ["data", "verify"])
        res2 = runner.invoke(app, ["data", "verify"])

    assert res1.exit_code == res2.exit_code == 1
    assert res1.stdout == res2.stdout

    # Verify byte preservation
    for f in files:
        assert f.read_bytes() == snapshots_before[f]


def test_cli_data_verify_does_not_leak_secrets(tmp_path: Path) -> None:
    """Verification output contains no credential values even if credentials file is present."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    cred_path = tmp_path / "credentials.json"

    secret_key = "sk-super-secret-do-not-leak-recovery-test"
    cred_store = FileCredentialStore(path=cred_path)
    cred_store.set_api_key("anthropic", secret_key)

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    with (
        patch("mia_cli.main.AgentManager", return_value=manager),
        patch("mia_agent.operations.default_credentials_path", return_value=cred_path),
    ):
        res = runner.invoke(app, ["data", "verify"])

    assert secret_key not in res.stdout
