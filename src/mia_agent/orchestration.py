"""Validated contracts for Mia's native orchestration runtime."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mia_agent.auth.config import ConfigManager
from mia_agent.events import AgentEvent, AssistantChunkEvent
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


class OrchestrationErrorEvent(BaseModel):
    """Terminal typed failure for a mode stage."""

    type: Literal["orchestration_error"] = "orchestration_error"
    stage: str
    error: str
    cancelled: bool = False


class OrchestrationEventEnvelope(BaseModel):
    """Attribution envelope retaining one unchanged inner AgentEvent."""

    mode: str
    run_id: str
    task_id: str
    agent_id: str
    profile: str
    event: AgentEvent | OrchestrationErrorEvent

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


class ModeRuntime:
    """Execute explicit modes and attribute each inner AgentEvent."""

    def __init__(
        self,
        *,
        factory: AgentRuntimeFactory | None = None,
        profile_manager: ProfileManager | None = None,
        catalog: ModeCatalog | None = None,
    ) -> None:
        self.profile_manager = profile_manager or ProfileManager()
        self.factory = factory or AgentRuntimeFactory(profile_manager=self.profile_manager)
        self.catalog = catalog or ModeCatalog(profile_manager=self.profile_manager)

    async def prompt(
        self,
        prompt_text: str,
        *,
        mode_name: str = "single",
        profile_name: str = "coding",
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        cwd: Path | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
        runtime: AgentRuntime | None = None,
    ) -> AsyncIterator[OrchestrationEventEnvelope]:
        mode = self.catalog.resolve(mode_name, profile_name)
        if mode.name == "research":
            if runtime is not None:
                raise ValueError("research mode cannot reuse a single-agent runtime")
            async for envelope in self._prompt_research(
                mode=mode,
                prompt_text=prompt_text,
                profile_name=profile_name,
                provider=provider,
                model_override=model_override,
                session_id=session_id,
                run_id=run_id,
                cwd=cwd,
                compaction_threshold=compaction_threshold,
                context_window=context_window,
            ):
                yield envelope
            return

        if runtime is None:
            resolved_run_id = run_id or f"run_{uuid.uuid4().hex}"
            identity = RuntimeIdentity(
                mode=mode.name,
                run_id=resolved_run_id,
                task_id="root",
                agent_id="coordinator",
                profile=mode.coordinator_profile,
                session_id=session_id or f"{resolved_run_id}_root",
            )
            runtime = self.factory.build(
                identity=identity,
                provider=provider,
                model_override=model_override,
                cwd=cwd,
                compaction_threshold=compaction_threshold,
                context_window=context_window,
            )
        else:
            identity = runtime.identity
            if identity.mode != mode.name or identity.profile != mode.coordinator_profile:
                raise ValueError("existing runtime does not match the selected mode and profile")

        try:
            async for event in runtime.harness.prompt(prompt_text):
                yield self._envelope(identity, event)
        except asyncio.CancelledError:
            yield self._error_envelope(identity, "root", "prompt cancelled", cancelled=True)
        except Exception as exc:
            yield self._error_envelope(identity, "root", str(exc))

    async def _prompt_research(
        self,
        *,
        mode: Mode,
        prompt_text: str,
        profile_name: str,
        provider: LLMProvider | None,
        model_override: str | None,
        session_id: str | None,
        run_id: str | None,
        cwd: Path | None,
        compaction_threshold: float | None,
        context_window: int | None,
    ) -> AsyncIterator[OrchestrationEventEnvelope]:
        resolved_run_id = run_id or f"run_{uuid.uuid4().hex}"
        root_session_id = session_id or f"{resolved_run_id}_root"
        specialist_identity = RuntimeIdentity(
            mode=mode.name,
            run_id=resolved_run_id,
            task_id="specialist",
            agent_id="specialist",
            profile="architect",
            session_id=f"{resolved_run_id}_specialist",
            parent_session_id=root_session_id,
        )
        specialist = self.factory.build(
            identity=specialist_identity,
            provider=provider,
            model_override=model_override,
            cwd=cwd,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
        )
        specialist_output: list[str] = []
        try:
            async for event in specialist.harness.prompt(prompt_text):
                if isinstance(event, AssistantChunkEvent) and event.delta_text:
                    specialist_output.append(event.delta_text)
                yield self._envelope(specialist_identity, event)
        except asyncio.CancelledError:
            yield self._error_envelope(
                specialist_identity,
                "specialist",
                "prompt cancelled",
                cancelled=True,
            )
            return
        except Exception as exc:
            yield self._error_envelope(specialist_identity, "specialist", str(exc))
            return

        coordinator_identity = RuntimeIdentity(
            mode=mode.name,
            run_id=resolved_run_id,
            task_id="root",
            agent_id="coordinator",
            profile=profile_name,
            session_id=root_session_id,
        )
        coordinator = self.factory.build(
            identity=coordinator_identity,
            provider=provider,
            model_override=model_override,
            cwd=cwd,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
        )
        handoff = (
            f"{prompt_text}\n\n"
            "[Architect specialist result — reference only]\n"
            f"{''.join(specialist_output)}\n"
            "[End architect specialist result]"
        )
        try:
            async for event in coordinator.harness.prompt(handoff):
                yield self._envelope(coordinator_identity, event)
        except asyncio.CancelledError:
            yield self._error_envelope(
                coordinator_identity,
                "coordinator",
                "prompt cancelled",
                cancelled=True,
            )
        except Exception as exc:
            yield self._error_envelope(coordinator_identity, "coordinator", str(exc))

    @staticmethod
    def _envelope(identity: RuntimeIdentity, event: AgentEvent) -> OrchestrationEventEnvelope:
        return OrchestrationEventEnvelope(
            mode=identity.mode,
            run_id=identity.run_id,
            task_id=identity.task_id,
            agent_id=identity.agent_id,
            profile=identity.profile,
            event=event,
        )

    @staticmethod
    def _error_envelope(
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
            event=OrchestrationErrorEvent(stage=stage, error=error, cancelled=cancelled),
        )


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
