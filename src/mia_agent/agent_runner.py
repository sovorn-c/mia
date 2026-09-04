"""Canonical Agent prompt runner."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

from mia_agent.agents import AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.events import AgentErrorEvent, AssistantChunkEvent, TurnCompleteEvent
from mia_agent.plugins import PluginManager
from mia_agent.runtime_events import (
    AgentEventEnvelope,
    PluginDiagnosticEvent,
    RunErrorEvent,
)
from mia_agent.runtime_events import (
    envelope as _envelope,
)
from mia_agent.runtime_events import (
    error_envelope as _error_envelope,
)
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import AgentRuntime, RunRequest, RuntimeIdentity
from mia_agent.session import SessionAdmission
from mia_ai.providers.base import LLMProvider
from mia_middleware.access import ApprovalCallback, sanitize_arguments


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


class _RunLifecycle:
    """Core-owned atomic idempotent finalizer and terminal guard for one Run."""

    def __init__(self, identity: RuntimeIdentity) -> None:
        self.identity = identity
        self.finalized: bool = False
        self.outcome: str | None = None
        self.terminal_envelope: AgentEventEnvelope | None = None
        self.terminal_delivered: bool = False

    def finalize(
        self,
        outcome: str,
        envelope: AgentEventEnvelope | None = None,
    ) -> bool:
        """Atomically finalize exactly once."""
        if self.finalized:
            return False
        self.finalized = True
        self.outcome = outcome
        self.terminal_envelope = envelope
        return True


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

    async def _run_cooperative_cleanup(
        self,
        runtime: AgentRuntime | None,
        identity: RuntimeIdentity,
        timeout: float = 2.0,
    ) -> list[AgentEventEnvelope]:
        if runtime is None or not getattr(runtime, "disposers", None):
            return []
        diagnostics: list[AgentEventEnvelope] = []
        disposers = runtime.disposers
        object.__setattr__(runtime, "disposers", ())
        for disposer in reversed(disposers):
            plugin_id = getattr(disposer, "plugin_id", "plugin")
            try:
                async with asyncio.timeout(timeout):
                    res = disposer()
                    if res is not None:
                        await res
            except TimeoutError:
                PluginManager.quarantine_plugin(plugin_id)
                diag = PluginDiagnosticEvent(
                    plugin_id=plugin_id,
                    phase="cleanup",
                    message="cooperative cleanup timed out",
                    error=f"Plugin '{plugin_id}' exceeded {timeout:g}s cleanup timeout",
                )
                diagnostics.append(_envelope(identity, diag))
            except Exception as exc:
                diag = PluginDiagnosticEvent(
                    plugin_id=plugin_id,
                    phase="cleanup",
                    message="cooperative cleanup failed",
                    error=str(sanitize_arguments(str(exc))),
                )
                diagnostics.append(_envelope(identity, diag))
        return diagnostics

    async def run(
        self,
        request: RunRequest,
        *,
        provider: LLMProvider | None = None,
        approval_callback: ApprovalCallback | None = None,
        cwd: Path | None = None,
    ) -> AsyncGenerator[AgentEventEnvelope, None]:
        """Execute one validated Agent Run using the canonical closeable stream."""
        effective_cwd = request.cwd if request.cwd is not None else cwd
        target_agent_id = request.agent_id or "mia"
        identity = RuntimeIdentity(
            run_id=request.run_id or f"run_{uuid.uuid4().hex}",
            task_id=request.task_id or "root",
            agent_id=target_agent_id,
            session_id=request.session_id or f"session_{uuid.uuid4().hex[:12]}",
        )
        lifecycle = _RunLifecycle(identity)

        try:
            agent = self.agent_manager.get_agent(target_agent_id)
            identity = identity.model_copy(update={"agent_id": agent.agent_id})
            lifecycle.identity = identity
        except Exception as exc:
            err_env = _error_envelope(
                _safe_error_identity(identity),
                stage="agent",
                error=str(exc),
                code="agent_not_found",
            )
            if lifecycle.finalize("agent_not_found", err_env):
                lifecycle.terminal_delivered = True
                yield err_env
            return

        if not SessionAdmission.acquire(identity.agent_id, identity.session_id):
            err_env = _error_envelope(
                _safe_error_identity(identity),
                stage="admission",
                error=f"Session '{identity.session_id}' is already active for Agent '{identity.agent_id}'",
                code="session_busy",
            )
            if lifecycle.finalize("session_busy", err_env):
                lifecycle.terminal_delivered = True
                yield err_env
            return

        runtime: AgentRuntime | None = None
        try:
            if agent.agent_id == "research":
                async for envelope in self._run_research(
                    request=request,
                    lifecycle=lifecycle,
                    provider=provider,
                    cwd=effective_cwd,
                    approval_callback=approval_callback,
                ):
                    yield envelope
                return

            runtime = self.factory.build(
                identity=identity,
                provider=provider,
                model_override=request.model_override,
                cwd=effective_cwd,
                compaction_threshold=request.compaction_threshold,
                context_window=request.context_window,
                approval_callback=approval_callback,
                full_access_confirmed=request.full_access_confirmed,
            )
            self.last_runtime = runtime

            async for event in runtime.harness.prompt(request.prompt_text):
                if lifecycle.terminal_delivered:
                    break

                if isinstance(event, TurnCompleteEvent):
                    for diag_env in await self._run_cooperative_cleanup(runtime, identity):
                        yield diag_env
                    env = _envelope(identity, event)
                    if lifecycle.finalize("success", env):
                        lifecycle.terminal_delivered = True
                        yield env
                    break
                elif isinstance(event, AgentErrorEvent):
                    for diag_env in await self._run_cooperative_cleanup(runtime, identity):
                        yield diag_env
                    err_env = _error_envelope(
                        _safe_error_identity(identity),
                        stage="agent",
                        error=event.error,
                        code="agent_error",
                    )
                    if lifecycle.finalize("agent_error", err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    break
                elif isinstance(event, RunErrorEvent):
                    for diag_env in await self._run_cooperative_cleanup(runtime, identity):
                        yield diag_env
                    err_env = AgentEventEnvelope(**identity.model_dump(), event=event)
                    if lifecycle.finalize(event.code, err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    break
                else:
                    yield _envelope(identity, event)

            if not lifecycle.finalized:
                for diag_env in await self._run_cooperative_cleanup(runtime, identity):
                    yield diag_env
                missing_env = _error_envelope(
                    _safe_error_identity(identity),
                    stage="runtime",
                    error="missing terminal event from agent harness",
                    code="missing_terminal",
                )
                if lifecycle.finalize("missing_terminal", missing_env):
                    lifecycle.terminal_delivered = True
                    yield missing_env

        except asyncio.CancelledError:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
                raise
            else:
                if not lifecycle.terminal_delivered and lifecycle.terminal_envelope is not None:
                    lifecycle.terminal_delivered = True
                    yield lifecycle.terminal_envelope
                return
        except GeneratorExit:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
            return
        except Exception as exc:
            if not lifecycle.finalized:
                for diag_env in await self._run_cooperative_cleanup(runtime, identity):
                    yield diag_env
                err_text = str(exc)
                code = (
                    "invalid_configuration"
                    if "cannot" in err_text.lower()
                    or "broaden" in err_text.lower()
                    or "escalate" in err_text.lower()
                    else (
                        "agent_not_found" if "not found" in err_text.lower() else "provider_error"
                    )
                )
                stage = (
                    "configuration"
                    if code == "invalid_configuration"
                    else ("agent" if code == "agent_not_found" else "provider")
                )
                err_env = _error_envelope(
                    _safe_error_identity(identity),
                    stage=stage,
                    error=err_text,
                    code=code,
                )
                if lifecycle.finalize(code, err_env):
                    lifecycle.terminal_delivered = True
                    yield err_env
        finally:
            try:
                if runtime is not None:
                    await self._run_cooperative_cleanup(runtime, identity)
            finally:
                SessionAdmission.release(identity.agent_id, identity.session_id)

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
        runtime: AgentRuntime | None = None
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
        finally:
            if runtime is not None:
                await self._run_cooperative_cleanup(runtime, identity)

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

    async def _run_research(
        self,
        *,
        request: RunRequest,
        lifecycle: _RunLifecycle,
        provider: LLMProvider | None,
        cwd: Path | None,
        approval_callback: ApprovalCallback | None,
    ) -> AsyncGenerator[AgentEventEnvelope, None]:
        specialist_identity = RuntimeIdentity(
            run_id=f"run_{uuid.uuid4().hex}",
            task_id="specialist",
            agent_id="architect",
            session_id=f"{lifecycle.identity.session_id}_specialist",
            parent_session_id=lifecycle.identity.session_id,
        )
        specialist: AgentRuntime | None = None
        coordinator: AgentRuntime | None = None
        findings: list[str] = []
        try:
            specialist = self.factory.build(
                identity=specialist_identity,
                provider=provider,
                model_override=request.model_override,
                cwd=cwd,
                compaction_threshold=request.compaction_threshold,
                context_window=request.context_window,
                approval_callback=approval_callback,
                full_access_confirmed=request.full_access_confirmed,
            )
            async for event in specialist.harness.prompt(request.prompt_text):
                if isinstance(event, AssistantChunkEvent) and event.delta_text:
                    findings.append(event.delta_text)
                if isinstance(event, AgentErrorEvent):
                    err_env = _error_envelope(
                        _safe_error_identity(specialist_identity),
                        stage="specialist",
                        error=event.error,
                        code="agent_error",
                    )
                    if lifecycle.finalize("agent_error", err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    return
                elif isinstance(event, RunErrorEvent):
                    err_env = AgentEventEnvelope(**specialist_identity.model_dump(), event=event)
                    if lifecycle.finalize(event.code, err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    return
                elif isinstance(event, TurnCompleteEvent):
                    yield _envelope(specialist_identity, event)
                else:
                    yield _envelope(specialist_identity, event)
        except asyncio.CancelledError:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
            raise
        except GeneratorExit:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
            return
        except Exception as exc:
            err_env = _error_envelope(
                _safe_error_identity(specialist_identity),
                stage="specialist",
                error=str(exc),
                code="provider_error",
            )
            if lifecycle.finalize("provider_error", err_env):
                lifecycle.terminal_delivered = True
                yield err_env
            return
        finally:
            if specialist is not None:
                await self._run_cooperative_cleanup(specialist, specialist_identity)

        coordinator_identity = RuntimeIdentity(
            run_id=lifecycle.identity.run_id,
            task_id="root",
            agent_id="research",
            session_id=lifecycle.identity.session_id,
        )
        handoff = (
            f"{request.prompt_text}\n\n[Architect specialist result — reference only]\n"
            f"{''.join(findings)}\n[End architect specialist result]"
        )
        try:
            coordinator = self.factory.build(
                identity=coordinator_identity,
                provider=provider,
                model_override=request.model_override,
                cwd=cwd,
                compaction_threshold=request.compaction_threshold,
                context_window=request.context_window,
                approval_callback=approval_callback,
                full_access_confirmed=request.full_access_confirmed,
            )
            self.last_runtime = coordinator
            async for event in coordinator.harness.prompt(handoff):
                if lifecycle.terminal_delivered:
                    break
                if isinstance(event, TurnCompleteEvent):
                    for diag_env in await self._run_cooperative_cleanup(
                        coordinator, coordinator_identity
                    ):
                        yield diag_env
                    env = _envelope(coordinator_identity, event)
                    if lifecycle.finalize("success", env):
                        lifecycle.terminal_delivered = True
                        yield env
                    break
                elif isinstance(event, AgentErrorEvent):
                    for diag_env in await self._run_cooperative_cleanup(
                        coordinator, coordinator_identity
                    ):
                        yield diag_env
                    err_env = _error_envelope(
                        _safe_error_identity(coordinator_identity),
                        stage="coordinator",
                        error=event.error,
                        code="agent_error",
                    )
                    if lifecycle.finalize("agent_error", err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    break
                elif isinstance(event, RunErrorEvent):
                    for diag_env in await self._run_cooperative_cleanup(
                        coordinator, coordinator_identity
                    ):
                        yield diag_env
                    err_env = AgentEventEnvelope(**coordinator_identity.model_dump(), event=event)
                    if lifecycle.finalize(event.code, err_env):
                        lifecycle.terminal_delivered = True
                        yield err_env
                    break
                else:
                    yield _envelope(coordinator_identity, event)

            if not lifecycle.finalized:
                for diag_env in await self._run_cooperative_cleanup(
                    coordinator, coordinator_identity
                ):
                    yield diag_env
                missing_env = _error_envelope(
                    _safe_error_identity(coordinator_identity),
                    stage="runtime",
                    error="missing terminal event from agent harness",
                    code="missing_terminal",
                )
                if lifecycle.finalize("missing_terminal", missing_env):
                    lifecycle.terminal_delivered = True
                    yield missing_env

        except asyncio.CancelledError:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
            raise
        except GeneratorExit:
            if not lifecycle.finalized:
                lifecycle.finalize("cancelled")
            return
        except Exception as exc:
            if not lifecycle.finalized:
                if coordinator is not None:
                    for diag_env in await self._run_cooperative_cleanup(
                        coordinator, coordinator_identity
                    ):
                        yield diag_env
                err_env = _error_envelope(
                    _safe_error_identity(coordinator_identity),
                    stage="coordinator",
                    error=str(exc),
                    code="provider_error",
                )
                if lifecycle.finalize("provider_error", err_env):
                    lifecycle.terminal_delivered = True
                    yield err_env
        finally:
            if coordinator is not None:
                await self._run_cooperative_cleanup(coordinator, coordinator_identity)
