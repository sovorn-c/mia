"""Core-owned local diagnostic records and recursive sanitation."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
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


def default_diagnostics_path() -> Path:
    from mia_agent.agents.manager import default_diagnostics_dir

    return default_diagnostics_dir() / "diagnostics.jsonl"


class DiagnosticStoreError(RuntimeError):
    """Raised when reading or persisting diagnostic records fails."""


class DiagnosticHealth(BaseModel):
    """Sanitized diagnostic persistence health state."""

    model_config = ConfigDict(frozen=True)

    healthy: bool = True
    total_records: int = 0
    total_bytes: int = 0
    last_error: str | None = None
    path: str = ""


class DiagnosticStore:
    """Core-owned append-only local diagnostic record store with bounded retention."""

    def __init__(
        self,
        path: Path | None = None,
        max_records: int = 1000,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.path = (path or default_diagnostics_path()).expanduser().absolute()
        self.max_records = max_records
        self.max_bytes = max_bytes
        self._last_error: str | None = None
        self._healthy: bool = True

    def get_health(self) -> DiagnosticHealth:
        """Inspect the current health and metrics of the diagnostic store."""
        total_records = 0
        total_bytes = 0
        try:
            if self.path.exists():
                total_bytes = self.path.stat().st_size
                with self.path.open("r", encoding="utf-8") as f:
                    total_records = sum(1 for line in f if line.strip())
        except Exception as exc:
            self._healthy = False
            self._last_error = sanitize_diagnostic_error(exc)
        return DiagnosticHealth(
            healthy=self._healthy,
            total_records=total_records,
            total_bytes=total_bytes,
            last_error=self._last_error,
            path=str(self.path),
        )

    def append(self, record: DiagnosticRecord) -> bool:
        """Append one record to the store; enforce bounded retention and capture health."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            serialized = record.model_dump_json() + "\n"
            with self.path.open("a", encoding="utf-8") as f:
                f.write(serialized)
                f.flush()
                import os

                os.fsync(f.fileno())
            self._healthy = True
            self._last_error = None
            self._enforce_retention()
            return True
        except Exception as exc:
            self._healthy = False
            self._last_error = sanitize_diagnostic_error(exc)
            return False

    def _enforce_retention(self) -> None:
        """Deterministically trim oldest records if over count or byte bound."""
        try:
            if not self.path.exists():
                return
            stat = self.path.stat()
            with self.path.open("r", encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
            if len(lines) <= self.max_records and stat.st_size <= self.max_bytes:
                return

            trimmed = lines[-self.max_records :]
            total_bytes = sum(len(line.encode("utf-8")) for line in trimmed)
            while trimmed and total_bytes > self.max_bytes:
                removed = trimmed.pop(0)
                total_bytes -= len(removed.encode("utf-8"))

            from mia_agent.agents.storage import atomic_write_text

            atomic_write_text(self.path, "".join(trimmed))
        except Exception as exc:
            self._healthy = False
            self._last_error = sanitize_diagnostic_error(exc)

    def read_records(
        self,
        *,
        limit: int | None = None,
        source: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        plugin_id: str | None = None,
        reverse: bool = False,
    ) -> list[DiagnosticRecord]:
        """Read and filter diagnostic records in deterministic order."""
        if not self.path.exists():
            return []
        records: list[DiagnosticRecord] = []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line_no, raw_line in enumerate(f, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        import json

                        data = json.loads(line)
                        record = DiagnosticRecord.model_validate(data)
                    except Exception as exc:
                        raise DiagnosticStoreError(
                            f"Malformed diagnostic record at line {line_no} in '{self.path}': {exc}"
                        ) from exc

                    if source is not None and record.source != source:
                        continue
                    if agent_id is not None and record.agent_id != agent_id:
                        continue
                    if session_id is not None and record.session_id != session_id:
                        continue
                    if run_id is not None and record.run_id != run_id:
                        continue
                    if plugin_id is not None and record.plugin_id != plugin_id:
                        continue
                    records.append(record)
        except OSError as exc:
            raise DiagnosticStoreError(
                f"Failed to read diagnostic records from '{self.path}': {exc}"
            ) from exc

        if reverse:
            records.reverse()
        if limit is not None and limit > 0:
            records = records[:limit]
        return records


__all__ = [
    "DiagnosticHealth",
    "DiagnosticRecord",
    "DiagnosticSeverity",
    "DiagnosticSource",
    "DiagnosticStore",
    "DiagnosticStoreError",
    "default_diagnostics_path",
    "sanitize_diagnostic_data",
    "sanitize_diagnostic_error",
    "sanitize_diagnostic_path",
]
