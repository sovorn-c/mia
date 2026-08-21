"""Validated contracts for Mia's native orchestration runtime."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mia_agent.events import AgentEvent


class WorkflowStage(BaseModel):
    """One ordered profile-backed stage in a mode workflow."""

    name: str
    profile: str
    kind: Literal["specialist", "coordinator"]

    @field_validator("name", "profile")
    @classmethod
    def require_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workflow stage names and profiles must not be blank")
        return value


class Workflow(BaseModel):
    """Validated ordered stages supported by a native mode."""

    name: str
    stages: list[WorkflowStage] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workflow name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_stage_order(self) -> Workflow:
        coordinators = [stage for stage in self.stages if stage.kind == "coordinator"]
        if len(coordinators) != 1:
            raise ValueError("workflow must contain exactly one coordinator stage")
        if self.stages[-1].kind != "coordinator":
            raise ValueError("coordinator stage must be final")
        if any(stage.kind == "coordinator" for stage in self.stages[:-1]):
            raise ValueError("coordinator stage must be final")
        if sum(stage.kind == "specialist" for stage in self.stages) > 1:
            raise ValueError("workflow supports at most one specialist stage")
        return self


class Mode(BaseModel):
    """Named orchestration composition around one coordinator workflow."""

    name: str
    coordinator_profile: str
    workflow: Workflow

    @field_validator("name", "coordinator_profile")
    @classmethod
    def require_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("mode names and coordinator profiles must not be blank")
        return value

    @model_validator(mode="after")
    def validate_coordinator(self) -> Mode:
        final_stage = self.workflow.stages[-1]
        if final_stage.profile != self.coordinator_profile:
            raise ValueError("mode coordinator_profile must match the final coordinator stage")
        return self

    def validate_profiles(self, available_profiles: set[str]) -> None:
        """Reject a mode that references profiles unavailable to its runtime."""
        required = {self.coordinator_profile}
        required.update(stage.profile for stage in self.workflow.stages)
        missing = sorted(required - available_profiles)
        if missing:
            raise ValueError(f"Mode '{self.name}' references unknown profiles: {', '.join(missing)}")


class OrchestrationEventEnvelope(BaseModel):
    """Attribution envelope retaining one unchanged inner AgentEvent."""

    mode: str
    run_id: str
    task_id: str
    agent_id: str
    profile: str
    event: AgentEvent

    @field_validator("mode", "run_id", "task_id", "agent_id", "profile")
    @classmethod
    def require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("orchestration event identity fields must not be blank")
        return value


__all__ = [
    "Mode",
    "OrchestrationEventEnvelope",
    "Workflow",
    "WorkflowStage",
]
