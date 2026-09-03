"""JSONL serialization and persistence engine for durable session trees."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from mia_agent.session.entries import (
    BaseSessionEntry,
    SessionEntry,
)

_ENTRY_ADAPTER: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


class SessionJsonlError(ValueError):
    """Raised when a session JSONL entry fails decoding or schema validation."""


class JsonlSessionStore:
    """Append-only JSONL file storage for session entry trees."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().absolute()

    def append_entry(self, entry: BaseSessionEntry) -> None:
        """Append a single session entry as a JSON line to disk."""
        dumped = entry.model_dump_json(exclude_none=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(dumped + "\n")

    def load_entries(self) -> list[SessionEntry]:
        """Read and deserialize all session entries from disk in chronological order."""
        if not self.path.exists():
            return []

        entries: list[SessionEntry] = []
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags)
        with os.fdopen(fd, encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                clean = line.strip()
                if not clean:
                    continue
                try:
                    raw_obj = json.loads(clean)
                    validated = _ENTRY_ADAPTER.validate_python(raw_obj)
                    entries.append(validated)
                except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                    raise SessionJsonlError(
                        f"Failed parsing session entry at line {idx} in {self.path}: {exc}"
                    ) from exc
        return entries
