"""Canonical Agent Run contracts."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    """Constructed executor and persistence handles for one Agent Run."""

    harness: AgentHarness
    identity: RuntimeIdentity
    session_store: JsonlSessionStore
    agent: Agent
