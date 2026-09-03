"""Canonical Agent Run event envelopes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from mia_agent.events import AgentEvent
from mia_agent.runtime_models import RuntimeIdentity
from mia_middleware.access import sanitize_arguments


class RunErrorEvent(BaseModel):
    """Sanitized terminal failure for one Run stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["run_error"] = "run_error"
    stage: str
    error: str
    cancelled: bool = False


class AgentEventEnvelope(BaseModel):
    """Attribution envelope retaining one unchanged inner Agent event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    agent_id: str
    session_id: str
    parent_session_id: str | None = None
    event: AgentEvent | RunErrorEvent


def envelope(identity: RuntimeIdentity, event: AgentEvent) -> AgentEventEnvelope:
    return AgentEventEnvelope(**identity.model_dump(), event=event)


def error_envelope(
    identity: RuntimeIdentity,
    stage: str,
    error: str,
    *,
    cancelled: bool = False,
) -> AgentEventEnvelope:
    return AgentEventEnvelope(
        **identity.model_dump(),
        event=RunErrorEvent(
            stage=stage,
            error=str(sanitize_arguments(error)),
            cancelled=cancelled,
        ),
    )


__all__ = ["AgentEventEnvelope", "RunErrorEvent", "envelope", "error_envelope"]
