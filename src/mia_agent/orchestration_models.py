"""Validated contracts and legacy mode composition models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mia_agent.agents import Agent
from mia_agent.events import AgentEvent
from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.profiles.model import AgentProfile
from mia_agent.session.jsonl import JsonlSessionStore


def _profile_from_agent(agent: Agent) -> AgentProfile:
    """Project an Agent into the temporary Profile shape used by legacy callers."""
    execution_mode: Literal["native", "code"] = (
        "code" if agent.metadata.get("execution_mode") == "code" else "native"
    )
    return AgentProfile(
        name=agent.agent_id,
        description=agent.description,
        system_prompt=agent.instructions,
        model=agent.model,
        temperature=agent.temperature,
        max_steps_per_turn=agent.max_steps_per_turn,
        tools=agent.tools,
        execution_mode=execution_mode,
        permission=agent.permission,
        compaction_threshold_ratio=agent.compaction_threshold_ratio,
        context_window_tokens=agent.context_window_tokens,
        middlewares=list(agent.middlewares),
        metadata=dict(agent.metadata),
    )


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
            raise ValueError(
                f"Mode '{self.name}' references unknown profiles: {', '.join(missing)}"
            )


class OrchestrationErrorEvent(BaseModel):
    """Terminal typed failure for a mode stage."""

    type: Literal["orchestration_error"] = "orchestration_error"
    stage: str
    error: str
    cancelled: bool = False


class OrchestrationEventEnvelope(BaseModel):
    """Attribution envelope retaining one unchanged inner AgentEvent."""

    run_id: str
    task_id: str
    agent_id: str
    event: AgentEvent | OrchestrationErrorEvent
    mode: str = "single"
    profile: str | None = None
    session_id: str | None = None
    parent_session_id: str | None = None

    @field_validator(
        "mode", "run_id", "task_id", "agent_id", "profile", "session_id", "parent_session_id"
    )
    @classmethod
    def require_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("orchestration event identity fields must not be blank")
        return value


class RuntimeIdentity(BaseModel):
    """Immutable attribution for one prompt-scoped Agent Run."""

    run_id: str
    task_id: str
    agent_id: str
    session_id: str
    mode: str = "single"
    profile: str | None = None
    parent_session_id: str | None = None

    @field_validator(
        "mode", "run_id", "task_id", "agent_id", "profile", "session_id", "parent_session_id"
    )
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
    profile: AgentProfile
    session_store: JsonlSessionStore
    agent: Agent


class ModeCatalog:
    """Resolve the built-in mode composition for a selected coordinator profile."""

    def __init__(self, profile_manager: ProfileManager | None = None) -> None:
        self.profile_manager = profile_manager or ProfileManager()

    def available_modes(self) -> tuple[str, ...]:
        return ("single", "research")

    def resolve(self, name: str, coordinator_profile: str) -> Mode:
        key = name.strip().lower()
        if key not in self.available_modes():
            available = ", ".join(self.available_modes())
            raise ValueError(f"Mode '{name}' not found. Available modes: {available}")

        if key == "single":
            workflow = Workflow(
                name="single-workflow",
                stages=[
                    WorkflowStage(
                        name="coordinator",
                        profile=coordinator_profile,
                        kind="coordinator",
                    )
                ],
            )
        else:
            workflow = Workflow(
                name="research-workflow",
                stages=[
                    WorkflowStage(name="specialist", profile="architect", kind="specialist"),
                    WorkflowStage(
                        name="coordinator",
                        profile=coordinator_profile,
                        kind="coordinator",
                    ),
                ],
            )

        mode = Mode(name=key, coordinator_profile=coordinator_profile, workflow=workflow)
        mode.validate_profiles({profile.name for profile in self.profile_manager.list_profiles()})
        return mode
