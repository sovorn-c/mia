"""Core-owned local diagnostic records and recursive sanitation."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DiagnosticSource = Literal["tool", "run", "plugin"]
DiagnosticSeverity = Literal["info", "warning", "error"]

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "password",
    "credential",
    "cookie",
    "auth_token",
    "password_hash",
)

_SECRET_VALUE_RE = re.compile(r"(?i)(?:bearer\s+|sk-|ghp_|gho_|github_pat_|xoxb-|xoxp-)[^\s,;'\"]+")

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?P<key_quote>[\"']?)(?P<key>[A-Za-z0-9_-]*(?:api[-_]?key|"
    r"apikey|token|secret|authorization|password|credential|cookie))(?P=key_quote)"
    r"(?P<separator>\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|"
    r"(?:[A-Za-z]+\s+)?[^\s,;]+)"
)

_PATH_REDACT_PATTERNS = (
    (re.compile(r"(?:\.\.[/\\])+[^\s\"';]*"), "[REDACTED_PATH]"),
    (re.compile(r"/etc/(?:shadow|sudoers|master\.passwd)"), "[REDACTED_PATH]"),
    (re.compile(r"/dev/(?:mem|kmem)"), "[REDACTED_PATH]"),
    (re.compile(r"(?:^|/)\.env(?:$|[\s\"';])"), "[REDACTED_PATH]"),
)


def sanitize_diagnostic_path(path_str: str) -> str:
    """Redact directory traversal sequences or restricted system paths."""
    cleaned = path_str.strip()
    for pattern, replacement in _PATH_REDACT_PATTERNS:
        if pattern.search(cleaned):
            return replacement
    return cleaned


def sanitize_diagnostic_data(value: Any, key: str = "") -> Any:
    """Recursively redact secrets, credential assignments, and unsafe paths."""
    key_text = key.lower().replace("-", "_")
    if isinstance(value, dict):
        return {str(k): sanitize_diagnostic_data(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_diagnostic_data(item, "") for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_diagnostic_data(item, "") for item in value)

    if any(part in key_text for part in _SECRET_KEY_PARTS):
        return "[REDACTED]"

    if isinstance(value, str):
        for pattern, replacement in _PATH_REDACT_PATTERNS:
            value = pattern.sub(replacement, value)
        redacted = _SECRET_ASSIGNMENT_RE.sub(
            r"\g<key_quote>\g<key>\g<key_quote>\g<separator>[REDACTED]", value
        )
        return _SECRET_VALUE_RE.sub("[REDACTED]", redacted)
    return value


def sanitize_diagnostic_error(exc: Exception | str) -> str:
    """Redact secrets and unsafe paths from error messages without exposing tracebacks."""
    msg = f"{type(exc).__name__}: {str(exc)}" if isinstance(exc, Exception) else str(exc)
    sanitized = sanitize_diagnostic_data(msg)
    return str(sanitized)


class DiagnosticRecord(BaseModel):
    """Attributed, validated, and secret-free local operational diagnostic record."""

    model_config = ConfigDict(frozen=True)

    record_id: str = Field(default_factory=lambda: f"diag_{uuid.uuid4().hex[:12]}")
    timestamp: float = Field(default_factory=time.time)
    source: DiagnosticSource
    severity: DiagnosticSeverity = "info"

    agent_id: str = ""
    run_id: str = ""
    task_id: str = ""
    session_id: str = ""
    plugin_id: str | None = None
    tool_name: str | None = None

    action: str = ""
    outcome: str = ""
    duration_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        source: DiagnosticSource,
        agent_id: str = "",
        run_id: str = "",
        task_id: str = "",
        session_id: str = "",
        plugin_id: str | None = None,
        tool_name: str | None = None,
        action: str = "",
        outcome: str = "",
        duration_ms: float | None = None,
        severity: DiagnosticSeverity = "info",
        details: dict[str, Any] | None = None,
        error: Exception | str | None = None,
        timestamp: float | None = None,
        record_id: str | None = None,
    ) -> DiagnosticRecord:
        """Create a record with automatic recursive sanitation of details and error."""
        sanitized_details = sanitize_diagnostic_data(details or {})
        sanitized_error = sanitize_diagnostic_error(error) if error is not None else None
        kwargs: dict[str, Any] = {
            "source": source,
            "severity": severity,
            "agent_id": agent_id,
            "run_id": run_id,
            "task_id": task_id,
            "session_id": session_id,
            "plugin_id": plugin_id,
            "tool_name": tool_name,
            "action": action,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "details": sanitized_details if isinstance(sanitized_details, dict) else {},
            "error": sanitized_error,
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp
        if record_id is not None:
            kwargs["record_id"] = record_id
        return cls(**kwargs)


__all__ = [
    "DiagnosticRecord",
    "DiagnosticSeverity",
    "DiagnosticSource",
    "sanitize_diagnostic_data",
    "sanitize_diagnostic_error",
    "sanitize_diagnostic_path",
]
