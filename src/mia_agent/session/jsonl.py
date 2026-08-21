"""JSONL serialization and persistence engine for durable session trees."""

from __future__ import annotations

import json
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
        self.path = Path(path).resolve()

    def append_entry(self, entry: BaseSessionEntry) -> None:
        """Append a single session entry as a JSON line to disk."""
        import contextlib

        dumped = entry.model_dump_json(exclude_none=True)
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(dumped + "\n")

    def load_entries(self) -> list[SessionEntry]:
        """Read and deserialize all session entries from disk in chronological order."""
        if not self.path.exists():
            return []

        entries: list[SessionEntry] = []
        with open(self.path, encoding="utf-8") as f:
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
