"""Append-only session entry models."""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mia_ai.types import ChatMessage


def new_entry_id() -> str:
    """Return a unique session entry identifier."""
    return uuid.uuid4().hex


def current_timestamp() -> float:
    """Return the current Unix epoch timestamp in seconds."""
    return time.time()


class BaseSessionEntry(BaseModel):
    """Common fields shared by all append-only session entries."""

    id: str = Field(default_factory=new_entry_id)
    parent_id: str | None = None
    timestamp: float = Field(default_factory=current_timestamp)


class MessageEntry(BaseSessionEntry):
    """Transcript message entry."""

    type: Literal["message"] = "message"
    message: ChatMessage


class CompactionEntry(BaseSessionEntry):
    """Context summary entry that replaces older messages during replay."""

    type: Literal["compaction"] = "compaction"
    summary: str
    replaces_entry_ids: list[str] = Field(default_factory=list)


class SessionInfoEntry(BaseSessionEntry):
    """Basic session metadata entry."""

    type: Literal["session_info"] = "session_info"
    created_at: float = Field(default_factory=current_timestamp)
    cwd: str | None = None
    title: str | None = None
    profile: str = "coding"


class LeafEntry(BaseSessionEntry):
    """Active branch leaf pointer entry."""

    type: Literal["leaf"] = "leaf"
    entry_id: str | None = None


class CustomEntry(BaseSessionEntry):
    """Arbitrary extension/metadata entry."""

    type: Literal["custom"] = "custom"
    namespace: str
    data: dict[str, Any] = Field(default_factory=dict)


SessionEntry = Annotated[
    MessageEntry | CompactionEntry | SessionInfoEntry | LeafEntry | CustomEntry,
    Field(discriminator="type"),
]
