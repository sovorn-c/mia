"""Agent-owned local note Tools contributed by the bundled Notes Plugin."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pydantic import BaseModel, ConfigDict

from mia_tools.base import BaseTool

_NOTE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_TITLE_LENGTH = 200
_MAX_CONTENT_LENGTH = 1_000_000


class Note(BaseModel):
    """Persisted private note owned by one Agent."""

    model_config = ConfigDict(extra="forbid")

    note_id: str
    title: str
    content: str
    created_at: datetime


class _NotesTool(BaseTool):
    plugin_id = "notes"

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()

    def _note_path(self, note_id: str) -> Path:
        if not isinstance(note_id, str) or not _NOTE_ID_RE.fullmatch(note_id):
            raise ValueError("note ID must be a generated 32-character hexadecimal ID")
        target = (self.data_dir / f"{note_id}.json").resolve()
        try:
            target.relative_to(self.data_dir)
        except ValueError as exc:
            raise ValueError("note ID must stay inside the Agent note data root") from exc
        return target

    @staticmethod
    def _load(path: Path) -> Note:
        try:
            return Note.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("stored note is invalid") from exc


class NoteCreateTool(_NotesTool):
    """Create one note using an Agent-owned generated identity."""

    name = "note_create"
    effect = "side-effecting"
    description = "Create a private note for this Agent."
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short note title."},
            "content": {"type": "string", "description": "Note body."},
        },
        "required": ["title", "content"],
    }

    async def execute(self, title: str, content: str, **kwargs: Any) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("note title must not be blank")
        if len(title.strip()) > _MAX_TITLE_LENGTH:
            raise ValueError("note title is too long")
        if not isinstance(content, str):
            raise ValueError("note content must be text")
        if len(content) > _MAX_CONTENT_LENGTH:
            raise ValueError("note content is too long")

        note = Note(
            note_id=uuid.uuid4().hex,
            title=title.strip(),
            content=content,
            created_at=datetime.now(UTC),
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        target = self._note_path(note.note_id)
        with NamedTemporaryFile(
            "w", dir=self.data_dir, prefix=".note-", suffix=".tmp", encoding="utf-8", delete=False
        ) as temp:
            json.dump(note.model_dump(mode="json"), temp, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
            temporary_path = Path(temp.name)
        temporary_path.replace(target)
        return note.model_dump(mode="json")


class NoteListTool(_NotesTool):
    """List notes from exactly one Agent-owned data root."""

    name = "note_list"
    effect = "non-mutating"
    description = "List private notes owned by this Agent."
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> list[dict[str, Any]]:
        if not self.data_dir.exists():
            return []
        notes: list[Note] = []
        for path in sorted(self.data_dir.glob("*.json")):
            if path.is_symlink():
                raise ValueError("note data contains an unsafe symbolic link")
            notes.append(self._load(path))
        return [note.model_dump(mode="json") for note in notes]


class NoteReadTool(_NotesTool):
    """Read one note from exactly one Agent-owned data root."""

    name = "note_read"
    effect = "non-mutating"
    description = "Read one private note owned by this Agent."
    parameters = {
        "type": "object",
        "properties": {"note_id": {"type": "string", "description": "Generated note ID."}},
        "required": ["note_id"],
    }

    async def execute(self, note_id: str, **kwargs: Any) -> dict[str, Any]:
        target = self._note_path(note_id)
        if not target.exists():
            raise FileNotFoundError("note was not found")
        if target.is_symlink():
            raise ValueError("note data contains an unsafe symbolic link")
        return self._load(target).model_dump(mode="json")


__all__ = ["Note", "NoteCreateTool", "NoteListTool", "NoteReadTool"]
