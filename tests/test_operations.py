"""Tests for local data layout, backup, and restore operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mia_agent.agents import AgentManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.operations import (
    DataLayout,
    DataLocation,
    enumerate_supported_files,
    get_data_locations,
    is_supported_backup_file,
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
