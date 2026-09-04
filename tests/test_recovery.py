"""Tests for non-destructive recovery verification and corruption classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.agents import AgentManager
from mia_agent.recovery import RecoveryFinding, RecoveryReport, RecoveryVerifier


def test_clean_environment_reports_clean(tmp_path: Path) -> None:
    """A valid, uncorrupted store verifies with clean status and no findings."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia", "name": "Mia"}', encoding="utf-8")

    session_file = agents_dir / "mia" / "sessions" / "s1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"event": "start"}\n{"event": "turn"}\n', encoding="utf-8")

    diag_file = diagnostics_dir / "diagnostics.jsonl"
    diag_file.parent.mkdir(parents=True, exist_ok=True)
    diag_file.write_text('{"source": "run", "outcome": "success"}\n', encoding="utf-8")

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert isinstance(report, RecoveryReport)
    assert report.status == "clean"
    assert len(report.findings) == 0
    assert report.files_scanned >= 3


def test_orphan_atomic_write_file_classified_as_attention(tmp_path: Path) -> None:
    """Orphan temporary atomic-write files are detected as attention and never deleted."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    orphan_file = agents_dir / "mia" / ".atomic_tmp_12345"
    orphan_file.parent.mkdir(parents=True, exist_ok=True)
    content = '{"partial": "write"}'
    orphan_file.write_text(content, encoding="utf-8")

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert report.status == "attention"
    assert any(f.category == "atomic_write" and f.status == "attention" for f in report.findings)

    # Verification MUST be strictly non-destructive: orphan file must still exist untouched
    assert orphan_file.exists()
    assert orphan_file.read_text(encoding="utf-8") == content


def test_truncated_final_session_line_classified_as_attention(tmp_path: Path) -> None:
    """An incomplete final JSONL append is classified as attention without data modification."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    session_file = agents_dir / "mia" / "sessions" / "s1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    raw_content = '{"event": "start"}\n{"event": "incomp'
    session_file.write_text(raw_content, encoding="utf-8")

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert report.status == "attention"
    finding = next(f for f in report.findings if f.category == "session")
    assert finding.status == "attention"
    assert "truncated" in finding.evidence.lower() or "incomplete" in finding.evidence.lower()

    # Original bytes must be preserved byte-for-byte
    assert session_file.read_text(encoding="utf-8") == raw_content


def test_interior_session_corruption_classified_as_blocked(tmp_path: Path) -> None:
    """Interior corrupt records in a session JSONL fail closed as blocked."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    session_file = agents_dir / "mia" / "sessions" / "s1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    raw_content = '{"event": "start"}\nNOT_VALID_JSON_INTERIOR\n{"event": "end"}\n'
    session_file.write_text(raw_content, encoding="utf-8")

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert report.status == "blocked"
    finding = next(f for f in report.findings if f.category == "session")
    assert finding.status == "blocked"
    assert "interior" in finding.evidence.lower() or "corrupt" in finding.evidence.lower()

    # Original bytes preserved
    assert session_file.read_text(encoding="utf-8") == raw_content


def test_malformed_agent_json_classified_as_blocked(tmp_path: Path) -> None:
    """Corrupt or invalid agent.json schema fails closed as blocked."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    raw_content = "definitely not json"
    agent_json.write_text(raw_content, encoding="utf-8")

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert report.status == "blocked"
    assert any(f.category == "schema" and f.status == "blocked" for f in report.findings)
    assert agent_json.read_text(encoding="utf-8") == raw_content


def test_symlink_escape_classified_as_blocked(tmp_path: Path) -> None:
    """Symlink escaping outside the supported root is classified as blocked."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_home = agents_dir / "mia"
    agent_home.mkdir(parents=True, exist_ok=True)

    sym_dir = agent_home / "plugins" / "notes"
    sym_dir.parent.mkdir(parents=True, exist_ok=True)
    sym_dir.symlink_to(outside_dir, target_is_directory=True)

    verifier = RecoveryVerifier(manager=manager)
    report = verifier.verify()

    assert report.status == "blocked"
    assert any(f.category == "path" and f.status == "blocked" for f in report.findings)
