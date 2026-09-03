"""Canonical Agent prompt runner."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from mia_agent.agents import AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.events import AgentErrorEvent, AssistantChunkEvent
from mia_agent.runtime_events import (
    AgentEventEnvelope,
)
from mia_agent.runtime_events import (
    envelope as _envelope,
)
from mia_agent.runtime_events import (
    error_envelope as _error_envelope,
)
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import AgentRuntime, RuntimeIdentity
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import ApprovalCallback


def _identity_part(value: str | None, fallback: str) -> str:
    """Keep error attribution valid when a caller supplies a malformed ID."""
    if not isinstance(value, str) or not value.strip():
        return fallback
    return value.strip()


def _safe_error_identity(identity: RuntimeIdentity) -> RuntimeIdentity:
    """Keep error attribution printable and free of path/control characters."""

    def clean(value: str | None, fallback: str) -> str:
        candidate = _identity_part(value, fallback)
        result = "".join(char if char.isalnum() or char in "._-" else "-" for char in candidate)
        return result[:128] or fallback

    return identity.model_copy(
        update={
            "run_id": clean(identity.run_id, "run"),
            "task_id": clean(identity.task_id, "task"),
            "agent_id": clean(identity.agent_id, "unknown"),
            "session_id": clean(identity.session_id, "session"),
            "parent_session_id": (
                clean(identity.parent_session_id, "parent")
                if identity.parent_session_id is not None
                else None
            ),
        }
    )


class AgentRunner:
    """Canonical headless prompt entry for one selected Agent."""

    def __init__(
        self,
        *,
        factory: AgentRuntimeFactory | None = None,
        agent_manager: AgentManager | None = None,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self.agent_manager = agent_manager or AgentManager()
        self.factory = factory or AgentRuntimeFactory(
            agent_manager=self.agent_manager,
            config_manager=config_manager,
        )
        self.last_runtime: AgentRuntime | None = None

    def prepare_runtime(
        self,
        *,
        agent_id: str,
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        session_id: str = "default",
        cwd: Path | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> AgentRuntime:
        """Prepare an Agent runtime for Session inspection before a prompt."""
        agent = self.agent_manager.get_agent(agent_id)
        identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id="root",
            agent_id=agent.agent_id,
            session_id=session_id,
        )
        runtime = self.factory.build(
            identity=identity,
            provider=provider,
            model_override=model_override,
            cwd=cwd,
            approval_callback=approval_callback,
        )
        self.last_runtime = runtime
        return runtime

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
    ) -> AsyncIterator[AgentEventEnvelope]:
        identity = RuntimeIdentity(
            run_id=run_id or f"run_{uuid.uuid4().hex}",
            task_id=_identity_part(task_id, "root"),
            agent_id=_identity_part(agent_id, "unknown"),
            session_id=_identity_part(session_id, f"session_{uuid.uuid4().hex[:12]}"),
        )
        try:
            agent = self.agent_manager.get_agent(agent_id)
            identity = identity.model_copy(update={"agent_id": agent.agent_id})
            if agent.agent_id == "research":
                async for envelope in self._prompt_research(
                    prompt_text=prompt_text,
                    provider=provider,
                    model_override=model_override,
                    session_id=identity.session_id,
                    run_id=identity.run_id,
                    cwd=cwd,
                    compaction_threshold=compaction_threshold,
                    context_window=context_window,
                    approval_callback=approval_callback,
                    full_access_confirmed=full_access_confirmed,
                ):
                    yield envelope
                return

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
            if identity.agent_id == "research":
                raise
            yield _error_envelope(
                _safe_error_identity(identity), "prompt", "prompt cancelled", cancelled=True
            )
            raise
        except Exception as exc:
            yield _error_envelope(_safe_error_identity(identity), "prompt", str(exc))

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
    ) -> AsyncIterator[AgentEventEnvelope]:
        specialist_identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id="specialist",
            agent_id="architect",
            session_id=f"{session_id}_specialist",
            parent_session_id=session_id,
        )
        findings: list[str] = []
        try:
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
            async for event in specialist.harness.prompt(prompt_text):
                if isinstance(event, AssistantChunkEvent) and event.delta_text:
                    findings.append(event.delta_text)
                yield _envelope(specialist_identity, event)
                if isinstance(event, AgentErrorEvent):
                    return
        except asyncio.CancelledError:
            yield _error_envelope(
                _safe_error_identity(specialist_identity),
                "specialist",
                "prompt cancelled",
                cancelled=True,
            )
            raise
        except Exception as exc:
            yield _error_envelope(_safe_error_identity(specialist_identity), "specialist", str(exc))
            return

        coordinator_identity = RuntimeIdentity(
            run_id=run_id,
            task_id="root",
            agent_id="research",
            session_id=session_id,
        )
        handoff = (
            f"{prompt_text}\n\n[Architect specialist result — reference only]\n"
            f"{''.join(findings)}\n[End architect specialist result]"
        )
        try:
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
            async for event in coordinator.harness.prompt(handoff):
                yield _envelope(coordinator_identity, event)
        except asyncio.CancelledError:
            yield _error_envelope(
                _safe_error_identity(coordinator_identity),
                "coordinator",
                "prompt cancelled",
                cancelled=True,
            )
            raise
        except Exception as exc:
            yield _error_envelope(
                _safe_error_identity(coordinator_identity), "coordinator", str(exc)
            )
