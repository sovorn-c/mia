"""Public contract tests for Mia's native orchestration model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mia_agent.events import TurnStartEvent
from mia_agent.orchestration import (
    Mode,
    OrchestrationEventEnvelope,
    Workflow,
    WorkflowStage,
)


def test_models_single_mode_contract_validates_and_rejects_blank_names() -> None:
    workflow = Workflow(
        name="single-workflow",
        stages=[WorkflowStage(name="coordinator", profile="coding", kind="coordinator")],
    )
    mode = Mode(name="single", coordinator_profile="coding", workflow=workflow)

    assert mode.name == "single"
    assert mode.workflow.stages[-1].kind == "coordinator"

    with pytest.raises(ValidationError):
        Mode(name=" ", coordinator_profile="coding", workflow=workflow)


def test_models_workflow_requires_coordinator_as_final_stage() -> None:
    with pytest.raises(ValidationError, match="coordinator"):
        Workflow(
            name="invalid",
            stages=[
                WorkflowStage(name="coordinator", profile="coding", kind="coordinator"),
                WorkflowStage(name="specialist", profile="architect", kind="specialist"),
            ],
        )


def test_models_mode_validates_referenced_profiles() -> None:
    workflow = Workflow(
        name="research-workflow",
        stages=[
            WorkflowStage(name="specialist", profile="architect", kind="specialist"),
            WorkflowStage(name="coordinator", profile="coding", kind="coordinator"),
        ],
    )
    mode = Mode(name="research", coordinator_profile="coding", workflow=workflow)

    mode.validate_profiles({"architect", "coding"})
    with pytest.raises(ValueError, match="architect"):
        mode.validate_profiles({"coding"})


def test_orchestration_envelope_retains_inner_agent_event() -> None:
    inner = TurnStartEvent(turn_index=0, user_prompt="map the repository")
    envelope = OrchestrationEventEnvelope(
        mode="single",
        run_id="run-1",
        task_id="task-1",
        agent_id="agent-1",
        profile="coding",
        event=inner,
    )

    assert envelope.event is inner
    assert envelope.event.type == "turn_start"
    assert envelope.mode == "single"
