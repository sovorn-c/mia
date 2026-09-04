"""Tests for local data layout, backup, and restore operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.operations import (
    BackupManifest,
    DataLayout,
    RestoreOutcome,
    create_backup,
    enumerate_supported_files,
    get_data_locations,
    is_supported_backup_file,
    restore_backup,
    validate_archive,
)


def test_data_locations_ownership_and_categories(tmp_path: Path) -> None:
    """Data locations distinguish Agent, Session, Plugin, Diagnostic, and Credential boundaries."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    credentials_path = tmp_path / "credentials.json"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    layout = get_data_locations(manager, credentials_path=credentials_path)

    assert isinstance(layout, DataLayout)
    locations = layout.locations
    assert len(locations) >= 5

    categories = {loc.category: loc for loc in locations}
    assert "agents" in categories
    assert "sessions" in categories
    assert "plugins" in categories
    assert "diagnostics" in categories
    assert "credentials" in categories

    # Verify ownership
    assert categories["agents"].ownership in {"core", "agent"}
    assert categories["sessions"].ownership == "agent"
    assert categories["plugins"].ownership == "plugin"
    assert categories["diagnostics"].ownership == "core"
    assert categories["credentials"].ownership == "core"

    # Verify sensitivity and backup eligibility
    assert categories["agents"].sensitive is False
    assert categories["agents"].included_in_backup is True

    assert categories["sessions"].sensitive is False
    assert categories["sessions"].included_in_backup is True

    assert categories["plugins"].sensitive is False
    assert categories["plugins"].included_in_backup is True

    assert categories["diagnostics"].sensitive is False
    assert categories["diagnostics"].included_in_backup is True

    assert categories["credentials"].sensitive is True
    assert categories["credentials"].included_in_backup is False


def test_data_locations_never_exposes_credentials(tmp_path: Path) -> None:
    """Data location inspection never leaks credential content or tokens."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    cred_path = tmp_path / "credentials.json"

    secret_key = "sk-live-super-secret-token-xyz123"
    cred_store = FileCredentialStore(path=cred_path)
    cred_store.set_api_key("openai", secret_key)

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    layout = get_data_locations(manager, credentials_path=cred_path)

    # Convert to dict, string, and json
    layout_str = str(layout)
    layout_repr = repr(layout)
    layout_json = layout.model_dump_json()

    assert secret_key not in layout_str
    assert secret_key not in layout_repr
    assert secret_key not in layout_json

    cred_loc = next(loc for loc in layout.locations if loc.category == "credentials")
    assert cred_loc.sensitive is True
    assert cred_loc.included_in_backup is False


def test_supported_and_excluded_file_classification(tmp_path: Path) -> None:
    """Classification distinguishes supported files from credentials, temporary files, and symlinks."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    cred_path = tmp_path / "credentials.json"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    # 1. Supported files
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    session_file = agents_dir / "mia" / "sessions" / "session_1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"event": "start"}\n', encoding="utf-8")

    plugin_data = agents_dir / "mia" / "plugins" / "notes" / "note.txt"
    plugin_data.parent.mkdir(parents=True, exist_ok=True)
    plugin_data.write_text("my notes", encoding="utf-8")

    diag_file = diagnostics_dir / "diagnostics.jsonl"
    diag_file.parent.mkdir(parents=True, exist_ok=True)
    diag_file.write_text('{"source": "run"}\n', encoding="utf-8")

    default_file = agents_dir / ".default-agent"
    default_file.write_text("mia\n", encoding="utf-8")

    # 2. Excluded files
    cred_path.write_text('{"openai": "secret"}', encoding="utf-8")
    temp_file1 = agents_dir / "mia" / "sessions" / "temp.tmp"
    temp_file1.write_text("temp", encoding="utf-8")
    temp_file2 = agents_dir / ".atomic_tmp_xyz"
    temp_file2.write_text("atomic", encoding="utf-8")
    unsupported_file = tmp_path / "external.txt"
    unsupported_file.write_text("outside", encoding="utf-8")

    # 3. Symlinks
    symlink_target = tmp_path / "target.txt"
    symlink_target.write_text("target", encoding="utf-8")
    symlink_file = agents_dir / "mia" / "symlink_file.txt"
    symlink_file.symlink_to(symlink_target)

    # Check individual file classifier
    assert is_supported_backup_file(agent_json, manager=manager) is True
    assert is_supported_backup_file(session_file, manager=manager) is True
    assert is_supported_backup_file(plugin_data, manager=manager) is True
    assert is_supported_backup_file(diag_file, manager=manager) is True
    assert is_supported_backup_file(default_file, manager=manager) is True

    assert is_supported_backup_file(cred_path, manager=manager) is False
    assert is_supported_backup_file(temp_file1, manager=manager) is False
    assert is_supported_backup_file(temp_file2, manager=manager) is False
    assert is_supported_backup_file(symlink_file, manager=manager) is False
    assert is_supported_backup_file(unsupported_file, manager=manager) is False

    # Check enumeration
    supported = enumerate_supported_files(manager)
    supported_paths = {p.resolve() for p in supported}

    assert agent_json.resolve() in supported_paths
    assert session_file.resolve() in supported_paths
    assert plugin_data.resolve() in supported_paths
    assert diag_file.resolve() in supported_paths
    assert default_file.resolve() in supported_paths

    assert cred_path.resolve() not in supported_paths
    assert temp_file1.resolve() not in supported_paths
    assert temp_file2.resolve() not in supported_paths
    assert symlink_file.resolve() not in supported_paths
    assert unsupported_file.resolve() not in supported_paths


def test_symlink_directory_and_traversal_rejected(tmp_path: Path) -> None:
    """Symlinked directories and files traversing outside configured roots are rejected."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    sensitive_file = outside_dir / "sensitive_external.txt"
    sensitive_file.write_text("should_not_leak", encoding="utf-8")

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_home = agents_dir / "mia"
    agent_home.mkdir(parents=True, exist_ok=True)

    # Symlink directory inside agent home pointing outside
    sym_dir = agent_home / "sym_dir"
    sym_dir.symlink_to(outside_dir, target_is_directory=True)

    nested_file = sym_dir / "sensitive_external.txt"
    assert is_supported_backup_file(nested_file, manager=manager) is False

    supported = enumerate_supported_files(manager)
    for p in supported:
        assert "outside_dir" not in str(p)
        assert "sym_dir" not in str(p)
        assert p.name != "sensitive_external.txt"


def test_agent_manager_data_layout_integration(tmp_path: Path) -> None:
    """AgentManager exposes get_data_layout directly as a Core contract."""
    manager = AgentManager(agents_dir=tmp_path / "agents", diagnostics_dir=tmp_path / "diagnostics")
    layout = manager.get_data_layout()
    assert isinstance(layout, DataLayout)
    assert any(loc.category == "agents" for loc in layout.locations)
    assert any(loc.category == "credentials" for loc in layout.locations)
    assert any(loc.category == "diagnostics" for loc in layout.locations)


def test_deterministic_enumeration_order(tmp_path: Path) -> None:
    """Supported file enumeration is strictly deterministic and sorted."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    for agent_id in ["zebra", "alpha", "beta"]:
        p = agents_dir / agent_id / "agent.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")

    files = enumerate_supported_files(manager)
    file_strs = [str(f) for f in files]
    assert file_strs == sorted(file_strs)


def test_create_backup_creates_valid_archive_and_manifest(tmp_path: Path) -> None:
    """Backup archives contain only supported non-credential data with a versioned manifest."""
    import zipfile

    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    cred_path = tmp_path / "credentials.json"
    archive_path = tmp_path / "backup.zip"

    secret_sentinel = "SUPER_SECRET_TOKEN_XYZ_DO_NOT_LEAK"
    cred_store = FileCredentialStore(path=cred_path)
    cred_store.set_api_key("anthropic", secret_sentinel)

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    # Valid supported files
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    session_file = agents_dir / "mia" / "sessions" / "s1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"event": "turn"}\n', encoding="utf-8")

    plugin_file = agents_dir / "mia" / "plugins" / "notes" / "note.txt"
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text("user note", encoding="utf-8")

    diag_file = diagnostics_dir / "diagnostics.jsonl"
    diag_file.parent.mkdir(parents=True, exist_ok=True)
    diag_file.write_text('{"source": "run"}\n', encoding="utf-8")

    manifest = create_backup(manager, archive_path=archive_path, credentials_path=cred_path)

    assert archive_path.exists()
    assert isinstance(manifest, BackupManifest)
    assert manifest.version == "1.0"
    assert len(manifest.files) >= 4

    manifest_paths = {f.path for f in manifest.files}
    assert "agents/mia/agent.json" in manifest_paths
    assert "agents/mia/sessions/s1.jsonl" in manifest_paths
    assert "agents/mia/plugins/notes/note.txt" in manifest_paths
    assert "diagnostics/diagnostics.jsonl" in manifest_paths

    # Read archive
    with zipfile.ZipFile(archive_path, "r") as zf:
        namelist = zf.namelist()
        assert "backup_manifest.json" in namelist
        assert "agents/mia/agent.json" in namelist
        assert "agents/mia/sessions/s1.jsonl" in namelist
        assert "agents/mia/plugins/notes/note.txt" in namelist
        assert "diagnostics/diagnostics.jsonl" in namelist

        # Credential file must NOT be in archive
        assert not any("credentials" in name.lower() for name in namelist)

        # Raw content must not contain secrets
        for name in namelist:
            content = zf.read(name)
            assert secret_sentinel.encode("utf-8") not in content


def test_create_backup_preserves_source_files_on_failure(tmp_path: Path) -> None:
    """Backup failure never modifies or deletes source data."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    # Invalid archive path (directory instead of file)
    bad_archive_path = tmp_path / "a_dir"
    bad_archive_path.mkdir()

    with pytest.raises(IsADirectoryError):
        create_backup(manager, archive_path=bad_archive_path)

    # Source files remain intact
    assert agent_json.exists()
    assert agent_json.read_text(encoding="utf-8") == '{"agent_id": "mia"}'


def test_create_backup_rejects_overwrite_existing_destination(tmp_path: Path) -> None:
    """Backup creation rejects overwriting an existing archive file unless overwrite=True."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    archive_path = tmp_path / "existing.zip"
    archive_path.write_text("existing content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_backup(manager, archive_path=archive_path, overwrite=False)

    assert archive_path.read_text(encoding="utf-8") == "existing content"


def test_restore_valid_archive_succeeds(tmp_path: Path) -> None:
    """Restore successfully unpacks valid archives byte-for-byte into fresh destinations."""
    agents_dir = tmp_path / "src_agents"
    diagnostics_dir = tmp_path / "src_diagnostics"
    archive_path = tmp_path / "backup.zip"
    dest_dir = tmp_path / "dest"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)

    # Set up source files
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia", "name": "Mia"}', encoding="utf-8")

    session_file = agents_dir / "mia" / "sessions" / "session_1.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_content = '{"event": "start", "seq": 1}\n{"event": "turn", "seq": 2}\n'
    session_file.write_text(session_content, encoding="utf-8")

    plugin_file = agents_dir / "mia" / "plugins" / "notes" / "note_1.txt"
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text("important note content", encoding="utf-8")

    diag_file = diagnostics_dir / "diagnostics.jsonl"
    diag_file.parent.mkdir(parents=True, exist_ok=True)
    diag_file.write_text('{"source": "run", "outcome": "success"}\n', encoding="utf-8")

    create_backup(manager, archive_path=archive_path)

    # Restore into fresh destination
    outcome = restore_backup(archive_path=archive_path, destination_dir=dest_dir)
    assert isinstance(outcome, RestoreOutcome)
    assert outcome.status == "restored"
    assert outcome.files_restored >= 4
    assert not outcome.errors

    # Verify restored files match byte-for-byte
    restored_agent_json = dest_dir / "agents" / "mia" / "agent.json"
    assert restored_agent_json.exists()
    assert restored_agent_json.read_bytes() == agent_json.read_bytes()

    restored_session = dest_dir / "agents" / "mia" / "sessions" / "session_1.jsonl"
    assert restored_session.exists()
    assert restored_session.read_bytes() == session_file.read_bytes()

    restored_plugin = dest_dir / "agents" / "mia" / "plugins" / "notes" / "note_1.txt"
    assert restored_plugin.exists()
    assert restored_plugin.read_bytes() == plugin_file.read_bytes()

    restored_diag = dest_dir / "diagnostics" / "diagnostics.jsonl"
    assert restored_diag.exists()
    assert restored_diag.read_bytes() == diag_file.read_bytes()


def test_restore_rejects_checksum_mismatch(tmp_path: Path) -> None:
    """Tampered archive files with mismatched sha256 are rejected without destination commit."""
    import zipfile

    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    archive_path = tmp_path / "backup.zip"
    dest_dir = tmp_path / "dest"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    create_backup(manager, archive_path=archive_path)

    # Tamper with archive: rewrite member with modified content
    tampered_archive = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(archive_path, "r") as zf_in,
        zipfile.ZipFile(tampered_archive, "w") as zf_out,
    ):
        for item in zf_in.infolist():
            if item.filename == "agents/mia/agent.json":
                zf_out.writestr(item.filename, b'{"agent_id": "tampered"}')
            else:
                zf_out.writestr(item.filename, zf_in.read(item.filename))

    outcome = restore_backup(archive_path=tampered_archive, destination_dir=dest_dir)
    assert outcome.status == "rejected"
    assert any(
        "checksum" in err.lower() or "digest" in err.lower() or "mismatch" in err.lower()
        for err in outcome.errors
    )
    assert not dest_dir.exists() or not any(dest_dir.iterdir())


def test_restore_rejects_traversal_archive(tmp_path: Path) -> None:
    """Archives containing path traversal or absolute member paths fail closed."""
    import zipfile

    bad_archive = tmp_path / "traversal.zip"
    dest_dir = tmp_path / "dest"

    manifest_json = '{"version": "1.0", "created_at": 0, "files": [{"path": "../evil.txt", "size": 4, "sha256": "bogus"}]}'
    with zipfile.ZipFile(bad_archive, "w") as zf:
        zf.writestr("backup_manifest.json", manifest_json)
        zf.writestr("../evil.txt", b"evil")

    outcome = restore_backup(archive_path=bad_archive, destination_dir=dest_dir)
    assert outcome.status == "rejected"
    assert any("traversal" in err.lower() or "path" in err.lower() for err in outcome.errors)
    assert not (tmp_path / "evil.txt").exists()


def test_restore_rejects_non_empty_destination_without_overwrite(tmp_path: Path) -> None:
    """Restore rejects non-empty destinations unless overwrite=True."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    archive_path = tmp_path / "backup.zip"
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_file = dest_dir / "existing.txt"
    existing_file.write_text("keep me safe", encoding="utf-8")

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    create_backup(manager, archive_path=archive_path)

    outcome = restore_backup(archive_path=archive_path, destination_dir=dest_dir, overwrite=False)
    assert outcome.status == "rejected"
    assert any("not empty" in err.lower() or "destination" in err.lower() for err in outcome.errors)
    assert existing_file.exists()
    assert existing_file.read_text(encoding="utf-8") == "keep me safe"


def test_restore_dry_run_validates_without_writing(tmp_path: Path) -> None:
    """Dry run validates archive integrity and returns success without touching destination."""
    agents_dir = tmp_path / "agents"
    diagnostics_dir = tmp_path / "diagnostics"
    archive_path = tmp_path / "backup.zip"
    dest_dir = tmp_path / "dest"

    manager = AgentManager(agents_dir=agents_dir, diagnostics_dir=diagnostics_dir)
    agent_json = agents_dir / "mia" / "agent.json"
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text('{"agent_id": "mia"}', encoding="utf-8")

    create_backup(manager, archive_path=archive_path)

    outcome = restore_backup(archive_path=archive_path, destination_dir=dest_dir, dry_run=True)
    assert outcome.status == "restored"
    assert not dest_dir.exists()


def test_validate_archive_rejects_duplicate_manifest_entries(tmp_path: Path) -> None:
    """validate_archive fails closed with an actionable error when manifest lists the same path twice."""
    import hashlib
    import json
    import zipfile

    archive_path = tmp_path / "dup_manifest.zip"
    content = b'{"agent_id": "mia"}'
    c_sha = hashlib.sha256(content).hexdigest()

    manifest_dict = {
        "version": "1.0",
        "created_at": 1700000000.0,
        "files": [
            {"path": "agents/mia/agent.json", "size": len(content), "sha256": c_sha},
            {"path": "agents/mia/agent.json", "size": len(content), "sha256": c_sha},
        ],
        "total_bytes": len(content) * 2,
    }

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps(manifest_dict))
        zf.writestr("agents/mia/agent.json", content)

    valid, manifest, errors = validate_archive(archive_path)
    assert valid is False
    assert any("duplicate" in err.lower() and "manifest" in err.lower() for err in errors)

    # restore_backup must also reject it
    dest_dir = tmp_path / "dest"
    outcome = restore_backup(archive_path=archive_path, destination_dir=dest_dir)
    assert outcome.status == "rejected"
    assert any("duplicate" in err.lower() for err in outcome.errors)
    assert not dest_dir.exists()
