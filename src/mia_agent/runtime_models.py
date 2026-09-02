"""Canonical Agent Run contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class RuntimeIdentity(BaseModel):
    """Immutable attribution for one prompt-scoped Agent Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    agent_id: str
    session_id: str
    parent_session_id: str | None = None

    @field_validator("run_id", "task_id", "agent_id", "session_id", "parent_session_id")
    @classmethod
    def require_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("runtime identity fields must not be blank")
        return value
