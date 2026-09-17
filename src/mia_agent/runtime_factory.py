"""Agent runtime construction and policy wiring."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from collections.abc import Awaitable, Callable, Collection, Sequence
from pathlib import Path
from typing import Any

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.harness import AgentHarness
from mia_agent.plugin_host import PluginActivation, PluginHost
from mia_agent.plugins import PluginManager
from mia_agent.runtime_models import AgentRuntime, EffectiveSettings, RuntimeIdentity
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.entries import CustomEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_codex import OpenAICodexProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.access import (
    AccessPolicyMiddleware,
    ApprovalCallback,
    FinalCoreToolValidator,
    tool_effect,
)
from mia_middleware.pipeline import ToolCallContext, ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool

POLICY_RANK: dict[str, int] = {
    "read-only": 0,
    "approval-required": 1,
    "full-access": 2,
}


def _wrap_plugin_middleware(middleware: Any) -> Any:
    if callable(middleware) and not (
        hasattr(middleware, "pre_tool") or hasattr(middleware, "post_tool")
    ):
        try:
            sig = inspect.signature(middleware)
            if len(sig.parameters) >= 2 or any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
            ):
                return middleware
        except (ValueError, TypeError):
            return middleware

    async def _wrapped(ctx: ToolCallContext, next_fn: Callable[[], Awaitable[Any]]) -> Any:
        if hasattr(middleware, "pre_tool"):
            res = middleware.pre_tool(ctx)
            if inspect.isawaitable(res):
                await res
        result = await next_fn()
        if hasattr(middleware, "post_tool"):
            post_res = middleware.post_tool(ctx, result)
            if inspect.isawaitable(post_res):
                return await post_res
            elif post_res is not None:
                return post_res
        return result

    return _wrapped


def _attributed_disposer(
    fn: Callable[[], Any], plugin_id: str
) -> Callable[[], Awaitable[None] | None]:
    def _wrapper() -> Any:
        return fn()

    _wrapper.plugin_id = plugin_id  # type: ignore[attr-defined]
    return _wrapper


def _resolve_awaitable(awaitable: Awaitable[Any]) -> Any:
    """Resolve an awaitable in either sync or running event loop context."""

    async def _await(target: Awaitable[Any]) -> Any:
        return await target

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await(awaitable))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_await(awaitable))).result()


class AgentRuntimeFactory:
    """Build every Agent with the same Tool, provider, and Session invariants."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        config_manager: ConfigManager | None = None,
        delegation_service: Any | None = None,
        plugin_manager: PluginManager | None = None,
        plugin_host: PluginHost | None = None,
        diagnostic_store: Any | None = None,
    ) -> None:
        self.agent_manager = agent_manager or AgentManager()
        self.config_manager = config_manager or ConfigManager()
        self.delegation_service = delegation_service
        self.plugin_manager = plugin_manager or PluginManager(agent_manager=self.agent_manager)
        self.plugin_host = plugin_host or PluginHost()
        from mia_agent.diagnostics import DiagnosticStore

        self.diagnostic_store = (
            diagnostic_store
            if diagnostic_store is not None
            else DiagnosticStore(path=self.agent_manager.get_diagnostics_path())
        )

    def resolve_effective_settings(
        self,
        agent: Agent,
        *,
        model_override: str | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
        access_policy_override: str | None = None,
        capabilities_override: Collection[str] | None = None,
        full_access_confirmed: bool | None = None,
        has_custom_provider: bool = False,
    ) -> EffectiveSettings:
        """Resolve and validate effective runtime settings with documented precedence."""
        config = self.config_manager.config

        # 1. Access policy narrowing check
        if access_policy_override is not None:
            if access_policy_override not in POLICY_RANK:
                raise ValueError(f"Unknown access policy: '{access_policy_override}'")
            current_rank = POLICY_RANK.get(agent.access_policy, 1)
            override_rank = POLICY_RANK[access_policy_override]
            if override_rank > current_rank:
                raise ValueError(
                    f"Cannot escalate Agent access policy from '{agent.access_policy}' to '{access_policy_override}'"
                )
            effective_policy = access_policy_override
        else:
            effective_policy = agent.access_policy

        # 2. Capabilities narrowing check
        effective_capabilities: tuple[str, ...] | None
        if capabilities_override is not None:
            if agent.tools is not None:
                override_set = set(capabilities_override)
                agent_tools_set = set(agent.tools)
                if not override_set.issubset(agent_tools_set):
                    extra = override_set - agent_tools_set
                    raise ValueError(
                        f"Cannot broaden Agent capabilities: extra tools {sorted(extra)} not allowed for Agent '{agent.agent_id}'"
                    )
            effective_capabilities = tuple(capabilities_override)
        else:
            effective_capabilities = tuple(agent.tools) if agent.tools is not None else None

        # 3. Model precedence
        target_model = (
            model_override
            or agent.model
            or config.default_model
            or ("" if has_custom_provider else "claude-3-5-sonnet")
        )
        target_provider = (
            agent.provider
            or config.default_provider
            or self.config_manager.infer_provider(target_model)
        )

        # 4. Context window precedence: explicit Agent settings beat model metadata.
        model_window = self.config_manager.model_context_window(target_provider, target_model)
        window_tokens = (
            context_window
            if context_window is not None
            else (
                agent.context_window_tokens
                if agent.context_window_tokens is not None
                else model_window or config.context_window_tokens
            )
        )

        # 5. Compaction threshold precedence
        compaction_ratio = (
            compaction_threshold
            if compaction_threshold is not None
            else (
                agent.compaction_threshold_ratio
                if agent.compaction_threshold_ratio is not None
                else config.compaction_threshold_ratio
            )
        )

        # 6. Full access confirmed
        effective_full_access = (
            agent.full_access_confirmed
            if full_access_confirmed is None
            else (agent.full_access_confirmed and full_access_confirmed)
        )

        return EffectiveSettings(
            model=target_model,
            context_window=window_tokens,
            compaction_threshold=compaction_ratio,
            max_steps_per_turn=agent.max_steps_per_turn,
            access_policy=effective_policy,
            capabilities=effective_capabilities,
            full_access_confirmed=effective_full_access,
        )

    def build(
        self,
        *,
        identity: RuntimeIdentity,
        provider: LLMProvider | None = None,
        model_override: str | None = None,
        cwd: Path | None = None,
        compaction_threshold: float | None = None,
        context_window: int | None = None,
        reasoning_level: str | None = None,
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool | None = None,
        access_policy_override: str | None = None,
        capabilities_override: Collection[str] | None = None,
        delegation_service: Any | None = None,
        delegation_depth: int = 0,
        disposers: Sequence[Callable[[], Awaitable[None] | None]] | None = None,
        activation: PluginActivation | None = None,
    ) -> AgentRuntime:
        """Construct an Agent-scoped harness, restoring and annotating its Session."""
        agent = self.agent_manager.get_agent(identity.agent_id)
        namespace = "agent"

        work_dir = cwd or Path.cwd()

        # Stage and validate complete current Plugin Tool set before settings/provider/harness
        if activation is not None:
            plugin_tools = list(activation.tools)
        else:
            plugin_tools = self.plugin_manager.resolve_tools(agent)
        plugin_names = [tool.name for tool in plugin_tools]

        available_tools = [
            ReadFileTool(cwd=work_dir),
            WriteFileTool(cwd=work_dir),
            EditFileTool(cwd=work_dir),
            BashTool(cwd=work_dir),
            *plugin_tools,
        ]
        tool_names = [getattr(tool, "name", "") for tool in available_tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("Plugin activation failed: duplicate Tool names are not allowed")

        if agent.tools is not None and capabilities_override is None:
            agent = agent.model_copy(update={"tools": [*agent.tools, *plugin_names]})

        settings = self.resolve_effective_settings(
            agent,
            model_override=model_override,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
            access_policy_override=access_policy_override,
            capabilities_override=capabilities_override,
            full_access_confirmed=full_access_confirmed,
            has_custom_provider=(provider is not None),
        )

        agent = agent.model_copy(
            update={
                "access_policy": settings.access_policy,
                "tools": list(settings.capabilities) if settings.capabilities is not None else None,
                "full_access_confirmed": settings.full_access_confirmed,
                "compaction_threshold_ratio": settings.compaction_threshold,
                "context_window_tokens": settings.context_window,
                "model": settings.model,
            }
        )

        target_model = settings.model

        if provider is None:
            provider_name, model_name, api_key, base_url = self.config_manager.resolve_credentials(
                model=target_model
            )
            thinking_level_map = self.config_manager.model_thinking_level_map(
                provider_name, model_name
            )
            if provider_name == "anthropic":
                provider = AnthropicProvider(
                    api_key=api_key, base_url=base_url, reasoning_level=reasoning_level
                )
            elif provider_name == "openai-codex":
                provider = OpenAICodexProvider(
                    credential_store=self.config_manager.credential_store,
                    base_url=base_url or "https://chatgpt.com/backend-api",
                    reasoning_level=reasoning_level,
                )
            else:
                provider = OpenAICompatibleProvider(
                    api_key=api_key, base_url=base_url, reasoning_level=reasoning_level
                )
            provider.extra_config["thinking_level_map"] = thinking_level_map
        else:
            model_name = target_model
            provider.extra_config["reasoning_level"] = reasoning_level
            provider.extra_config["thinking_level_map"] = (
                self.config_manager.model_thinking_level_map("custom", model_name)
            )

        tools = self.agent_manager.filter_tools(agent, available_tools)
        active_delegation_service = delegation_service or self.delegation_service
        if (
            active_delegation_service is not None
            and delegation_depth == 0
            and agent.delegation_targets
        ):
            from mia_tools.delegate import DelegateTaskTool

            tools.append(DelegateTaskTool(active_delegation_service.for_caller(identity)))
            if agent.tools is not None:
                agent = agent.model_copy(update={"tools": [*agent.tools, "delegate_task"]})
        if agent.access_policy == "read-only":
            tools = [
                tool
                for tool in tools
                if tool_effect(tool.name, {"effect": tool.effect}) == "non-mutating"
            ]
            agent = agent.model_copy(update={"tools": [tool.name for tool in tools]})
        plugin_middleware = activation.tool_middleware if activation is not None else ()
        pipeline = self._build_pipeline(
            agent.middlewares,
            agent=agent,
            identity=identity,
            approval_callback=approval_callback,
            full_access_confirmed=settings.full_access_confirmed,
            tool_effects={
                tool.name: tool_effect(tool.name, {"effect": tool.effect}) for tool in tools
            },
            plugin_middleware=plugin_middleware,
            diagnostic_store=self.diagnostic_store,
        )
        session_store = JsonlSessionStore(
            self.agent_manager.get_session_path(agent.agent_id, identity.session_id)
        )
        initial_messages, last_entry_id = self._restore_session(session_store)
        last_entry_id = self._persist_identity(
            identity, session_store, last_entry_id, namespace=namespace
        )

        system_prompt = agent.instructions
        if activation is not None and activation.context_contributors:
            context_additions: list[str] = []
            for contributor in activation.context_contributors:
                try:
                    res = contributor()
                    if inspect.isawaitable(res):
                        res = _resolve_awaitable(res)
                    if isinstance(res, str) and res.strip():
                        context_additions.append(res.strip())
                except Exception:
                    pass
            if context_additions:
                system_prompt = (
                    f"{system_prompt}\n\n" + "\n\n".join(context_additions)
                    if system_prompt
                    else "\n\n".join(context_additions)
                )

        harness = AgentHarness(
            provider=provider,
            model=model_name,
            system_prompt=system_prompt,
            tools=tools,
            pipeline=pipeline,
            max_steps_per_turn=settings.max_steps_per_turn,
            session_id=identity.session_id,
            messages=initial_messages,
            session_store=session_store,
            compactor=ContextCompactor(
                context_window_tokens=settings.context_window,
                compaction_threshold_ratio=settings.compaction_threshold,
            ),
            last_entry_id=last_entry_id,
            reasoning_level=reasoning_level,
            tool_context_metadata={
                "agent_id": agent.agent_id,
                "run_id": identity.run_id,
                "task_id": identity.task_id,
                "session_id": identity.session_id,
            },
        )
        collected_disposers: list[Callable[[], Awaitable[None] | None]] = []
        if hasattr(provider, "aclose") and callable(provider.aclose):
            collected_disposers.append(_attributed_disposer(provider.aclose, "provider"))
        for tool in tools:
            pid = getattr(tool, "plugin_id", "plugin")
            if hasattr(tool, "dispose") and callable(tool.dispose):
                collected_disposers.append(_attributed_disposer(tool.dispose, pid))
            elif hasattr(tool, "cleanup") and callable(tool.cleanup):
                collected_disposers.append(_attributed_disposer(tool.cleanup, pid))
        if activation is not None:
            collected_disposers.extend(activation.disposers)
        if disposers is not None:
            collected_disposers.extend(disposers)

        return AgentRuntime(
            harness=harness,
            identity=identity,
            session_store=session_store,
            agent=agent,
            effective_settings=settings,
            disposers=tuple(collected_disposers),
            activation=activation,
        )

    @staticmethod
    def _build_pipeline(
        middlewares: list[str],
        *,
        agent: Agent | None = None,
        identity: RuntimeIdentity | None = None,
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool | None = None,
        tool_effects: dict[str, Any] | None = None,
        plugin_middleware: Sequence[Any] = (),
        diagnostic_store: Any | None = None,
    ) -> ToolPipeline:
        active: list[Any] = []
        final_validator = None
        if agent is not None and identity is not None:
            effective_confirmed = (
                agent.full_access_confirmed
                if full_access_confirmed is None
                else full_access_confirmed
            )
            active.append(
                AccessPolicyMiddleware(
                    access_policy=agent.access_policy,
                    capabilities=agent.tools,
                    approval_callback=approval_callback,
                    full_access_confirmed=effective_confirmed,
                    agent_id=agent.agent_id,
                    run_id=identity.run_id,
                    task_id=identity.task_id,
                    session_id=identity.session_id,
                    tool_effects=tool_effects,
                )
            )
            final_validator = FinalCoreToolValidator(
                agent_id=agent.agent_id,
                access_policy=agent.access_policy,
                capabilities=agent.tools,
                full_access_confirmed=effective_confirmed,
                tool_effects=tool_effects,
                approval_callback=approval_callback,
            )
        active.append(SecurityGuardMiddleware())

        def _log_to_diagnostic_store(record: Any) -> None:
            if diagnostic_store is not None:
                import contextlib

                with contextlib.suppress(Exception):
                    from mia_agent.diagnostics import DiagnosticRecord

                    diag = DiagnosticRecord.create(
                        source="tool",
                        agent_id=getattr(record, "agent_id", ""),
                        run_id=getattr(record, "run_id", ""),
                        task_id=getattr(record, "task_id", ""),
                        session_id=getattr(record, "session_id", ""),
                        plugin_id=getattr(record, "plugin_id", None),
                        tool_name=getattr(record, "tool_name", None),
                        action="execute",
                        outcome="failed" if getattr(record, "is_error", False) else "success",
                        duration_ms=getattr(record, "duration_ms", None),
                        details={"arguments": getattr(record, "arguments", {})},
                        error=getattr(record, "error_message", None),
                    )
                    diagnostic_store.append(diag)

        active.append(AuditLogMiddleware(callback=_log_to_diagnostic_store))
        active.append(CostBudgetMiddleware())
        for pm in plugin_middleware:
            active.append(_wrap_plugin_middleware(pm))
        return ToolPipeline(active, final_validator=final_validator)

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
        *,
        namespace: str = "agent",
    ) -> str | None:
        data = identity.model_dump(exclude_none=True)
        for entry in session_store.load_entries():
            if (
                isinstance(entry, CustomEntry)
                and entry.namespace == namespace
                and entry.data == data
            ):
                return parent_entry_id
        metadata = CustomEntry(
            parent_id=parent_entry_id,
            namespace=namespace,
            data=data,
        )
        session_store.append_entry(metadata)
        return metadata.id
