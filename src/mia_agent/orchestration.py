"""Validated contracts for Mia's native orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mia_agent.auth.config import ConfigManager
from mia_agent.events import AgentEvent
from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.profiles.model import AgentProfile
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.entries import CustomEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool


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


class RuntimeIdentity(BaseModel):
    """Durable identity assigned to one mode-run agent instance."""

    mode: str
    run_id: str
    task_id: str
    agent_id: str
    profile: str
    session_id: str
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
    """Constructed executor and persistence handles for one agent instance."""

    harness: AgentHarness
    identity: RuntimeIdentity
    profile: AgentProfile
    session_store: JsonlSessionStore


class AgentRuntimeFactory:
    """Build every Mia agent with the same profile and session invariants."""

    def __init__(
        self,
        *,
        profile_manager: ProfileManager | None = None,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self.profile_manager = profile_manager or ProfileManager()
        self.config_manager = config_manager or ConfigManager()

    def build(
        self,
        *,
        identity: RuntimeIdentity,
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        cwd: Path | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
    ) -> AgentRuntime:
        """Construct a profile-scoped harness, restoring and annotating its session."""
        profile = self.profile_manager.get_profile(identity.profile)
        work_dir = cwd or Path.cwd()
        target_model = model_override or profile.model or ("" if provider else "claude-3-5-sonnet")

        if provider is None:
            provider_name, model_name, api_key, base_url = self.config_manager.resolve_credentials(
                model=target_model
            )
            if provider_name == "anthropic":
                provider = AnthropicProvider(api_key=api_key, base_url=base_url)
            else:
                provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url)
        else:
            model_name = target_model

        tools = self.profile_manager.filter_tools(
            profile,
            [
                ReadFileTool(cwd=work_dir),
                WriteFileTool(cwd=work_dir),
                EditFileTool(cwd=work_dir),
                BashTool(cwd=work_dir),
            ],
        )
        pipeline = self._build_pipeline(profile.middlewares)
        session_dir = self.profile_manager.get_session_dir(profile.name)
        session_store = JsonlSessionStore(session_dir / f"{identity.session_id}.jsonl")
        initial_messages, last_entry_id = self._restore_session(session_store)
        last_entry_id = self._persist_identity(identity, session_store, last_entry_id)

        config = self.config_manager.config
        compaction_ratio = (
            compaction_threshold
            if compaction_threshold is not None
            else (
                profile.compaction_threshold_ratio
                if profile.compaction_threshold_ratio is not None
                else config.compaction_threshold_ratio
            )
        )
        window_tokens = (
            context_window
            if context_window is not None
            else (
                profile.context_window_tokens
                if profile.context_window_tokens is not None
                else config.context_window_tokens
            )
        )
        harness = AgentHarness(
            provider=provider,
            model=model_name,
            system_prompt=profile.system_prompt,
            tools=tools,
            pipeline=pipeline,
            max_steps_per_turn=profile.max_steps_per_turn,
            session_id=identity.session_id,
            messages=initial_messages,
            session_store=session_store,
            compactor=ContextCompactor(
                context_window_tokens=window_tokens,
                compaction_threshold_ratio=compaction_ratio,
            ),
            last_entry_id=last_entry_id,
        )
        return AgentRuntime(
            harness=harness,
            identity=identity,
            profile=profile,
            session_store=session_store,
        )

    @staticmethod
    def _build_pipeline(middlewares: list[str]) -> ToolPipeline:
        active: list[Any] = []
        if "security_guard" in middlewares:
            active.append(SecurityGuardMiddleware())
        if "audit_log" in middlewares:
            active.append(AuditLogMiddleware())
        if "cost_budget" in middlewares:
            active.append(CostBudgetMiddleware())
        return ToolPipeline(active)

    @staticmethod
    def _restore_session(
        session_store: JsonlSessionStore,
    ) -> tuple[list[Any], str | None]:
        if not session_store.path.exists():
            return [], None
        tree = SessionTree(session_store.load_entries())
        active_path = tree.get_active_path()
        return tree.extract_messages_from_path(active_path), active_path[
            -1
        ].id if active_path else None

    @staticmethod
    def _persist_identity(
        identity: RuntimeIdentity,
        session_store: JsonlSessionStore,
        parent_entry_id: str | None,
    ) -> str | None:
        data = identity.model_dump(exclude_none=True)
        for entry in session_store.load_entries():
            if (
                isinstance(entry, CustomEntry)
                and entry.namespace == "orchestration"
                and entry.data == data
            ):
                return parent_entry_id
        metadata = CustomEntry(
            parent_id=parent_entry_id,
            namespace="orchestration",
            data=data,
        )
        session_store.append_entry(metadata)
        return metadata.id


__all__ = [
    "AgentRuntime",
    "AgentRuntimeFactory",
    "Mode",
    "OrchestrationEventEnvelope",
    "RuntimeIdentity",
    "Workflow",
    "WorkflowStage",
]
