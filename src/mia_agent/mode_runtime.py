"""Legacy Mode/Profile compatibility runtime."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from mia_agent.agent_runner import AgentRunner
from mia_agent.events import AssistantChunkEvent
from mia_agent.orchestration_events import envelope as _envelope
from mia_agent.orchestration_events import error_envelope as _error_envelope
from mia_agent.orchestration_models import (
    AgentRuntime,
    Mode,
    ModeCatalog,
    OrchestrationEventEnvelope,
    RuntimeIdentity,
)
from mia_agent.profiles.manager import ProfileManager
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import ApprovalCallback


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
        self.agent_runner = AgentRunner(
            factory=self.factory,
            agent_manager=self.factory.agent_manager,
        )
        self.catalog = catalog or ModeCatalog(profile_manager=self.profile_manager)

    async def prompt(
        self,
        prompt_text: str,
        *,
        mode_name: str = "single",
        profile_name: str = "coding",
        agent_id: str | None = None,
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        cwd: Path | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
        runtime: AgentRuntime | None = None,
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool | None = None,
    ) -> AsyncIterator[OrchestrationEventEnvelope]:
        if agent_id is not None:
            if runtime is not None:
                raise ValueError("canonical Agent prompts cannot reuse a legacy runtime")
            async for envelope in self.agent_runner.prompt(
                prompt_text,
                agent_id=agent_id,
                provider=provider,
                model_override=model_override,
                session_id=session_id,
                run_id=run_id,
                cwd=cwd,
                compaction_threshold=compaction_threshold,
                context_window=context_window,
                approval_callback=approval_callback,
                full_access_confirmed=full_access_confirmed,
            ):
                yield envelope
            return

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
                approval_callback=approval_callback,
                full_access_confirmed=full_access_confirmed,
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
                approval_callback=approval_callback,
                full_access_confirmed=full_access_confirmed,
            )
        else:
            identity = runtime.identity
            if identity.mode != mode.name or identity.profile != mode.coordinator_profile:
                raise ValueError("existing runtime does not match the selected mode and profile")

        try:
            async for event in runtime.harness.prompt(prompt_text):
                yield _envelope(identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(identity, "root", "prompt cancelled", cancelled=True)
        except Exception as exc:
            yield _error_envelope(identity, "root", str(exc))

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
        approval_callback: ApprovalCallback | None,
        full_access_confirmed: bool | None,
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
            approval_callback=approval_callback,
            full_access_confirmed=full_access_confirmed,
        )
        specialist_output: list[str] = []
        try:
            async for event in specialist.harness.prompt(prompt_text):
                if isinstance(event, AssistantChunkEvent) and event.delta_text:
                    specialist_output.append(event.delta_text)
                yield _envelope(specialist_identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(
                specialist_identity,
                "specialist",
                "prompt cancelled",
                cancelled=True,
            )
            return
        except Exception as exc:
            yield _error_envelope(specialist_identity, "specialist", str(exc))
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
            approval_callback=approval_callback,
            full_access_confirmed=full_access_confirmed,
        )
        handoff = (
            f"{prompt_text}\n\n"
            "[Architect specialist result — reference only]\n"
            f"{''.join(specialist_output)}\n"
            "[End architect specialist result]"
        )
        try:
            async for event in coordinator.harness.prompt(handoff):
                yield _envelope(coordinator_identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(
                coordinator_identity,
                "coordinator",
                "prompt cancelled",
                cancelled=True,
            )
        except Exception as exc:
            yield _error_envelope(coordinator_identity, "coordinator", str(exc))
