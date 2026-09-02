"""Shared orchestration event-envelope constructors."""

from __future__ import annotations

from mia_agent.events import AgentEvent
from mia_agent.orchestration_models import (
    OrchestrationErrorEvent,
    OrchestrationEventEnvelope,
    RuntimeIdentity,
)
from mia_middleware.access import sanitize_arguments


def envelope(identity: RuntimeIdentity, event: AgentEvent) -> OrchestrationEventEnvelope:
    return OrchestrationEventEnvelope(
        mode=identity.mode,
        run_id=identity.run_id,
        task_id=identity.task_id,
        agent_id=identity.agent_id,
        profile=identity.profile,
        session_id=identity.session_id,
        parent_session_id=identity.parent_session_id,
        event=event,
    )


def error_envelope(
    identity: RuntimeIdentity,
    stage: str,
    error: str,
    *,
    cancelled: bool = False,
) -> OrchestrationEventEnvelope:
    return OrchestrationEventEnvelope(
        mode=identity.mode,
        run_id=identity.run_id,
        task_id=identity.task_id,
        agent_id=identity.agent_id,
        profile=identity.profile,
        session_id=identity.session_id,
        parent_session_id=identity.parent_session_id,
        event=OrchestrationErrorEvent(
            stage=stage,
            error=str(sanitize_arguments(error)),
            cancelled=cancelled,
        ),
    )
