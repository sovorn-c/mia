"""Tests for diagnostic records, attribution, and recursive sanitation."""

from __future__ import annotations

import time
from typing import Any

import pytest
from pydantic import ValidationError

from mia_agent.diagnostics import (
    DiagnosticRecord,
    DiagnosticSource,
    sanitize_diagnostic_data,
    sanitize_diagnostic_error,
    sanitize_diagnostic_path,
)


def test_diagnostic_record_attribution_fields() -> None:
    """Tool, Run, and Plugin source records preserve all Core attribution fields."""
    # 1. Tool source record
    tool_rec = DiagnosticRecord(
        source="tool",
        agent_id="test-agent",
        run_id="run-123",
        task_id="task-456",
        session_id="session-789",
        tool_name="read_file",
        plugin_id="core",
        action="execute",
        outcome="success",
        duration_ms=12.5,
        details={"path": "safe.txt"},
    )
    assert tool_rec.source == "tool"
    assert tool_rec.agent_id == "test-agent"
    assert tool_rec.run_id == "run-123"
    assert tool_rec.task_id == "task-456"
    assert tool_rec.session_id == "session-789"
    assert tool_rec.tool_name == "read_file"
    assert tool_rec.plugin_id == "core"
    assert tool_rec.outcome == "success"
    assert tool_rec.duration_ms == 12.5
    assert tool_rec.record_id.startswith("diag_")

    # 2. Run source record
    run_rec = DiagnosticRecord(
        source="run",
        agent_id="mia",
        run_id="run-abc",
        task_id="root",
        session_id="session-xyz",
        action="finalize",
        outcome="success",
        details={"terminal_code": "success"},
    )
    assert run_rec.source == "run"
    assert run_rec.agent_id == "mia"
    assert run_rec.run_id == "run-abc"
    assert run_rec.tool_name is None
    assert run_rec.plugin_id is None

    # 3. Plugin source record
    plugin_rec = DiagnosticRecord(
        source="plugin",
        agent_id="mia",
        run_id="run-abc",
        session_id="session-xyz",
        plugin_id="notes_plugin",
        action="cleanup",
        outcome="failed",
        error="disposal error",
    )
    assert plugin_rec.source == "plugin"
    assert plugin_rec.plugin_id == "notes_plugin"
    assert plugin_rec.outcome == "failed"
    assert plugin_rec.error == "disposal error"


def test_diagnostic_record_invalid_source() -> None:
    """DiagnosticRecord rejects invalid sources."""
    with pytest.raises(ValidationError):
        DiagnosticRecord(source="unknown_source")  # type: ignore[arg-type]


def test_diagnostic_record_immutability() -> None:
    """DiagnosticRecord instances are immutable to preserve evidence."""
    rec = DiagnosticRecord(
        source="run",
        agent_id="mia",
        run_id="run-1",
        session_id="session-1",
        action="start",
        outcome="started",
    )
    with pytest.raises(ValidationError):
        rec.outcome = "mutated"  # type: ignore[misc]


def test_sanitize_diagnostic_data_recursive_secrets() -> None:
    """Credentials, authorization headers, and token-shaped values are recursively redacted."""
    raw_payload: dict[str, Any] = {
        "api_key": "sk-live-1234567890abcdef",
        "authorization": "Bearer secret-token-value",
        "nested": {
            "auth_token": "ghp_xxxxxxxxxxxxxxxxxxxx",
            "safe_key": "safe_value",
            "password_hash": "supersecret",
            "list_of_secrets": [
                {"token": "xoxb-1234-5678"},
                "Authorization: Bearer secret-in-string",
                "normal string",
            ],
        },
        "query": "SELECT * FROM users WHERE apikey = 'sk-123456'",
        "user_secret": "my-secret-val",
    }

    sanitized = sanitize_diagnostic_data(raw_payload)

    # Key-based redaction
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["user_secret"] == "[REDACTED]"
    assert sanitized["nested"]["auth_token"] == "[REDACTED]"
    assert sanitized["nested"]["password_hash"] == "[REDACTED]"
    assert sanitized["nested"]["safe_key"] == "safe_value"
    assert sanitized["nested"]["list_of_secrets"][0]["token"] == "[REDACTED]"
    assert "secret-token-value" not in str(sanitized)
    assert "sk-live-1234567890abcdef" not in str(sanitized)
    assert "ghp_xxxxxxxxxxxxxxxxxxxx" not in str(sanitized)
    assert "xoxb-1234-5678" not in str(sanitized)


def test_sanitize_diagnostic_path_traversal() -> None:
    """Unsafe path traversal sequences are redacted from diagnostic data."""
    assert sanitize_diagnostic_path("../etc/passwd") == "[REDACTED_PATH]"
    assert sanitize_diagnostic_path("/safe/dir/file.txt") == "/safe/dir/file.txt"
    assert sanitize_diagnostic_path("relative/path/ok.json") == "relative/path/ok.json"
    assert sanitize_diagnostic_path("../../secret.key") == "[REDACTED_PATH]"
    assert sanitize_diagnostic_path("/etc/shadow") == "[REDACTED_PATH]"


def test_sanitize_diagnostic_error_exception_sanitation() -> None:
    """Raw exceptions with secrets or tracebacks are sanitized before persistence."""
    # Exception containing a secret
    exc = ValueError("Failed connection with api_key=sk-ant-1234567890abcdef and token=ghp_abc123")
    sanitized_msg = sanitize_diagnostic_error(exc)
    assert "sk-ant-1234567890abcdef" not in sanitized_msg
    assert "ghp_abc123" not in sanitized_msg
    assert "[REDACTED]" in sanitized_msg
    assert "ValueError" in sanitized_msg or "Failed connection" in sanitized_msg

    # Unsafe path in error
    path_exc = FileNotFoundError("Cannot access /etc/shadow: permission denied")
    sanitized_path_msg = sanitize_diagnostic_error(path_exc)
    assert "/etc/shadow" not in sanitized_path_msg
    assert "[REDACTED_PATH]" in sanitized_path_msg


def test_diagnostic_record_auto_sanitization() -> None:
    """DiagnosticRecord automatically sanitizes its details and error upon creation."""
    rec = DiagnosticRecord.create(
        source="tool",
        agent_id="mia",
        run_id="run-1",
        tool_name="bash",
        details={
            "api_key": "sk-123456789",
            "path": "../../../etc/shadow",
            "normal": "value",
        },
        error="Connection failed with auth token: ghp_123456789",
    )
    assert rec.details["api_key"] == "[REDACTED]"
    assert rec.details["path"] == "[REDACTED_PATH]"
    assert rec.details["normal"] == "value"
    assert "ghp_123456789" not in (rec.error or "")
    assert "[REDACTED]" in (rec.error or "")
