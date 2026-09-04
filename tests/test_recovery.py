"""Tests for non-destructive recovery verification and corruption classification."""

from __future__ import annotations

from pathlib import Path

from mia_agent.agents import AgentManager
from mia_agent.recovery import RecoveryReport, RecoveryVerifier, verify_recovery


def test_clean_environment_reports_clean(tmp_path: Path) -> None:
    """A valid, uncorrupted store verifies with clean status and no findings."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia", "display_name": "Mia"}', encoding="utf-8")

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


def test_status_precedence_blocked_over_attention(tmp_path: Path) -> None:
    """When both attention and blocked conditions exist, blocked status takes precedence."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    # Attention condition: orphan temporary file
    orphan = agents_dir / "mia" / ".atomic_tmp_xyz"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("temp", encoding="utf-8")

    # Blocked condition: malformed interior session line
    session_file = agents_dir / "mia" / "sessions" / "s1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        '{"event": "start"}\nCORRUPT_INTERIOR\n{"event": "end"}\n', encoding="utf-8"
    )

    report = verify_recovery(manager)
    assert report.status == "blocked"
    categories = {f.category for f in report.findings}
    assert "atomic_write" in categories
    assert "session" in categories


def test_verify_recovery_helper_and_safe_relative_paths(tmp_path: Path) -> None:
    """Findings use safe relative paths and never expose host directory paths or secrets."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text("not json", encoding="utf-8")

    report = verify_recovery(manager)
    assert report.status == "blocked"
    assert len(report.findings) > 0
    for finding in report.findings:
        assert not finding.path.startswith("/")
        assert not finding.path.startswith("C:")
        assert ".." not in finding.path
        assert finding.path.startswith("agents/") or finding.path.startswith("diagnostics/")


def test_diagnostics_store_corruption_classification(tmp_path: Path) -> None:
    """Corrupt diagnostics.jsonl entries are classified with proper attention/blocked status."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    diag_file = diagnostics_dir / "diagnostics.jsonl"
    diag_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Truncated final line -> attention
    diag_file.write_text(
        '{"source": "run", "outcome": "success"}\n{"source": "to', encoding="utf-8"
    )
    report = verify_recovery(manager)
    assert report.status == "attention"
    assert any(f.category == "diagnostics" and f.status == "attention" for f in report.findings)

    # 2. Interior corrupt line -> blocked
    diag_file.write_text(
        '{"source": "run"}\nBOGUS_INTERIOR_LINE\n{"source": "plugin"}\n', encoding="utf-8"
    )
    report2 = verify_recovery(manager)
    assert report2.status == "blocked"
    assert any(f.category == "diagnostics" and f.status == "blocked" for f in report2.findings)


def test_recovery_verification_is_strictly_byte_preserving(tmp_path: Path) -> None:
    """Verification guarantees zero bytes are modified, truncated, or removed."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    files_and_contents = {
        agents_dir / "mia" / "agent.json": '{"agent_id": "mia", "display_name": "Mia"}',
        agents_dir / "mia" / "sessions" / "s1.jsonl": '{"event": "start"}\n{"event": "incomp',
        agents_dir / "mia" / ".atomic_tmp_1": "temporary artifact data",
        diagnostics_dir / "diagnostics.jsonl": '{"source": "run", "outcome": "success"}\n',
    }

    for p, content in files_and_contents.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # Run verification multiple times
    verifier = RecoveryVerifier(manager=manager)
    report1 = verifier.verify()
    report2 = verifier.verify()

    assert report1.status == report2.status
    assert len(report1.findings) == len(report2.findings)

    # Assert every single file has the exact same bytes as before
    for p, expected_content in files_and_contents.items():
        assert p.exists()
        assert p.read_text(encoding="utf-8") == expected_content
