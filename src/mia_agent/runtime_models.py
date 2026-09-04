"""Canonical Agent Run contracts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from mia_agent.agents import Agent
from mia_agent.harness import AgentHarness
from mia_agent.session.jsonl import JsonlSessionStore


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


_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _validate_safe_id(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{field_name} must not be blank")
    if "/" in candidate or "\\" in candidate or candidate in {".", ".."}:
        raise ValueError(
            f"Unsafe {field_name} '{value}': path separators and traversal are not allowed"
        )
    if not _SAFE_ID_RE.fullmatch(candidate):
        raise ValueError(
            f"Unsafe {field_name} '{value}': use letters, numbers, hyphens, underscores, dots"
        )
    return candidate


class RunRequest(BaseModel):
    """Immutable validated input for one Agent Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_text: str
    agent_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    task_id: str = "root"
    model_override: str | None = None
    cwd: Path | None = None
    compaction_threshold: float | None = None
    context_window: int | None = None
    full_access_confirmed: bool | None = None

    @field_validator("prompt_text")
    @classmethod
    def validate_prompt_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("prompt_text must not be blank")
        return value

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str | None) -> str | None:
        return _validate_safe_id(value, "agent_id")

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        return _validate_safe_id(value, "session_id")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str | None) -> str | None:
        return _validate_safe_id(value, "run_id")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        res = _validate_safe_id(value, "task_id")
        if res is None:
            raise ValueError("task_id must not be blank")
        return res

    @field_validator("compaction_threshold")
    @classmethod
    def validate_compaction_threshold(cls, value: float | None) -> float | None:
        if value is not None and (value <= 0.0 or value > 1.0):
            raise ValueError("compaction_threshold must be in the range (0.0, 1.0]")
        return value

    @field_validator("context_window")
    @classmethod
    def validate_context_window(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("context_window must be a positive integer")
        return value


class EffectiveSettings(BaseModel):
    """Immutable snapshot of resolved runtime settings for one Agent Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    context_window: int
    compaction_threshold: float
    max_steps_per_turn: int
    access_policy: str
    capabilities: tuple[str, ...] | None = None
    full_access_confirmed: bool = False

    @field_validator("context_window")
    @classmethod
    def validate_context_window(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("context_window must be a positive integer")
        return value

    @field_validator("compaction_threshold")
    @classmethod
    def validate_compaction_threshold(cls, value: float) -> float:
        if value <= 0.0 or value > 1.0:
            raise ValueError("compaction_threshold must be in the range (0.0, 1.0]")
        return value


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    """Constructed executor and persistence handles for one Agent Run."""

    harness: AgentHarness
    identity: RuntimeIdentity
    session_store: JsonlSessionStore
    agent: Agent
    effective_settings: EffectiveSettings | None = None
    disposers: tuple[Callable[[], Awaitable[None] | None], ...] = ()


__all__ = ["AgentRuntime", "EffectiveSettings", "RunRequest", "RuntimeIdentity"]
