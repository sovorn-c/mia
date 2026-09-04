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
    code: str = "runtime_error"
    cancelled: bool = False


class PluginDiagnosticEvent(BaseModel):
    """Sanitized diagnostic for Plugin observer or cleanup lifecycle events."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["plugin_diagnostic"] = "plugin_diagnostic"
    plugin_id: str
    phase: str
    message: str
    error: str | None = None


class AgentEventEnvelope(BaseModel):
    """Attribution envelope retaining one unchanged inner Agent event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    agent_id: str
    session_id: str
    parent_session_id: str | None = None
    event: AgentEvent | RunErrorEvent | PluginDiagnosticEvent


def envelope(
    identity: RuntimeIdentity, event: AgentEvent | RunErrorEvent | PluginDiagnosticEvent
) -> AgentEventEnvelope:
    return AgentEventEnvelope(**identity.model_dump(), event=event)


def error_envelope(
    identity: RuntimeIdentity,
    stage: str,
    error: str,
    *,
    code: str = "runtime_error",
    cancelled: bool = False,
) -> AgentEventEnvelope:
    effective_code = "cancelled" if (cancelled and code == "runtime_error") else code
    return AgentEventEnvelope(
        **identity.model_dump(),
        event=RunErrorEvent(
            stage=stage,
            error=str(sanitize_arguments(error)),
            code=effective_code,
            cancelled=cancelled,
        ),
    )


__all__ = [
    "AgentEventEnvelope",
    "PluginDiagnosticEvent",
    "RunErrorEvent",
    "envelope",
    "error_envelope",
]
