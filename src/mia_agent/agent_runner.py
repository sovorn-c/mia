"""Canonical Agent prompt runner."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from mia_agent.agents import AgentManager
from mia_agent.events import AgentErrorEvent, AssistantChunkEvent
from mia_agent.orchestration_events import envelope as _envelope
from mia_agent.orchestration_events import error_envelope as _error_envelope
from mia_agent.orchestration_models import AgentRuntime, OrchestrationEventEnvelope, RuntimeIdentity
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import ApprovalCallback


class AgentRunner:
    """Canonical headless prompt entry for one selected Agent."""

    def __init__(
        self,
        *,
        factory: AgentRuntimeFactory | None = None,
        agent_manager: AgentManager | None = None,
    ) -> None:
        self.agent_manager = agent_manager or AgentManager()
        self.factory = factory or AgentRuntimeFactory(agent_manager=self.agent_manager)
        self.last_runtime: AgentRuntime | None = None

    async def prompt(
        self,
        prompt_text: str,
        *,
        agent_id: str | None = None,
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        task_id: str = "root",
        cwd: Path | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool | None = None,
    ) -> AsyncIterator[OrchestrationEventEnvelope]:
        agent = self.agent_manager.get_agent(agent_id)
        resolved_run_id = run_id or f"run_{uuid.uuid4().hex}"
        root_session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        if agent.agent_id == "research":
            async for envelope in self._prompt_research(
                prompt_text=prompt_text,
                provider=provider,
                model_override=model_override,
                session_id=root_session_id,
                run_id=resolved_run_id,
                cwd=cwd,
                compaction_threshold=compaction_threshold,
                context_window=context_window,
                approval_callback=approval_callback,
                full_access_confirmed=full_access_confirmed,
            ):
                yield envelope
            return

        identity = RuntimeIdentity(
            run_id=resolved_run_id,
            task_id=task_id,
            agent_id=agent.agent_id,
            session_id=root_session_id,
        )
        try:
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
            self.last_runtime = runtime
            async for event in runtime.harness.prompt(prompt_text):
                yield _envelope(identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(identity, task_id, "prompt cancelled", cancelled=True)
        except Exception as exc:
            yield _error_envelope(identity, task_id, str(exc))

    async def _prompt_research(
        self,
        *,
        prompt_text: str,
        provider: LLMProvider | None,
        model_override: str | None,
        session_id: str,
        run_id: str,
        cwd: Path | None,
        compaction_threshold: float | None,
        context_window: int | None,
        approval_callback: ApprovalCallback | None,
        full_access_confirmed: bool | None,
    ) -> AsyncIterator[OrchestrationEventEnvelope]:
        specialist_identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id="specialist",
            agent_id="architect",
            session_id=f"{session_id}_specialist",
            parent_session_id=session_id,
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
        findings: list[str] = []
        try:
            async for event in specialist.harness.prompt(prompt_text):
                if isinstance(event, AssistantChunkEvent) and event.delta_text:
                    findings.append(event.delta_text)
                yield _envelope(specialist_identity, event)
                if isinstance(event, AgentErrorEvent):
                    return
        except asyncio.CancelledError:
            yield _error_envelope(
                specialist_identity, "specialist", "prompt cancelled", cancelled=True
            )
            return
        except Exception as exc:
            yield _error_envelope(specialist_identity, "specialist", str(exc))
            return

        coordinator_identity = RuntimeIdentity(
            run_id=run_id,
            task_id="root",
            agent_id="research",
            session_id=session_id,
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
        self.last_runtime = coordinator
        handoff = (
            f"{prompt_text}\n\n[Architect specialist result — reference only]\n"
            f"{''.join(findings)}\n[End architect specialist result]"
        )
        try:
            async for event in coordinator.harness.prompt(handoff):
                yield _envelope(coordinator_identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(
                coordinator_identity, "coordinator", "prompt cancelled", cancelled=True
            )
        except Exception as exc:
            yield _error_envelope(coordinator_identity, "coordinator", str(exc))
