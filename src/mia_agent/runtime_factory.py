"""Agent runtime construction and policy wiring."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Sequence
from pathlib import Path
from typing import Any

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.harness import AgentHarness
from mia_agent.plugins import PluginManager
from mia_agent.runtime_models import AgentRuntime, EffectiveSettings, RuntimeIdentity
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.entries import CustomEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.access import (
    AccessPolicyMiddleware,
    ApprovalCallback,
    FinalCoreToolValidator,
    tool_effect,
)
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool

POLICY_RANK: dict[str, int] = {
    "read-only": 0,
    "approval-required": 1,
    "full-access": 2,
}


def _attributed_disposer(
    fn: Callable[[], Any], plugin_id: str
) -> Callable[[], Awaitable[None] | None]:
    def _wrapper() -> Any:
        return fn()

    _wrapper.plugin_id = plugin_id  # type: ignore[attr-defined]
    return _wrapper


class AgentRuntimeFactory:
    """Build every Agent with the same Tool, provider, and Session invariants."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        config_manager: ConfigManager | None = None,
        delegation_service: Any | None = None,
        plugin_manager: PluginManager | None = None,
    ) -> None:
        self.agent_manager = agent_manager or AgentManager()
        self.config_manager = config_manager or ConfigManager()
        self.delegation_service = delegation_service
        self.plugin_manager = plugin_manager or PluginManager(agent_manager=self.agent_manager)

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

        # 4. Context window precedence
        window_tokens = (
            context_window
            if context_window is not None
            else (
                agent.context_window_tokens
                if agent.context_window_tokens is not None
                else config.context_window_tokens
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
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool | None = None,
        access_policy_override: str | None = None,
        capabilities_override: Collection[str] | None = None,
        delegation_service: Any | None = None,
        delegation_depth: int = 0,
        disposers: Sequence[Callable[[], Awaitable[None] | None]] | None = None,
    ) -> AgentRuntime:
        """Construct an Agent-scoped harness, restoring and annotating its Session."""
        agent = self.agent_manager.get_agent(identity.agent_id)
        namespace = "agent"

        work_dir = cwd or Path.cwd()

        # Stage and validate complete current Plugin Tool set before settings/provider/harness
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
            if provider_name == "anthropic":
                provider = AnthropicProvider(api_key=api_key, base_url=base_url)
            else:
                provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url)
        else:
            model_name = target_model

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
        pipeline = self._build_pipeline(
            agent.middlewares,
            agent=agent,
            identity=identity,
            approval_callback=approval_callback,
            full_access_confirmed=settings.full_access_confirmed,
            tool_effects={
                tool.name: tool_effect(tool.name, {"effect": tool.effect}) for tool in tools
            },
        )
        session_store = JsonlSessionStore(
            self.agent_manager.get_session_path(agent.agent_id, identity.session_id)
        )
        initial_messages, last_entry_id = self._restore_session(session_store)
        last_entry_id = self._persist_identity(
            identity, session_store, last_entry_id, namespace=namespace
        )

        harness = AgentHarness(
            provider=provider,
            model=model_name,
            system_prompt=agent.instructions,
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
            tool_context_metadata={
                "agent_id": agent.agent_id,
                "run_id": identity.run_id,
                "task_id": identity.task_id,
                "session_id": identity.session_id,
            },
        )
        collected_disposers: list[Callable[[], Awaitable[None] | None]] = []
        for tool in tools:
            pid = getattr(tool, "plugin_id", "plugin")
            if hasattr(tool, "dispose") and callable(tool.dispose):
                collected_disposers.append(_attributed_disposer(tool.dispose, pid))
            elif hasattr(tool, "cleanup") and callable(tool.cleanup):
                collected_disposers.append(_attributed_disposer(tool.cleanup, pid))
        if disposers is not None:
            collected_disposers.extend(disposers)

        return AgentRuntime(
            harness=harness,
            identity=identity,
            session_store=session_store,
            agent=agent,
            effective_settings=settings,
            disposers=tuple(collected_disposers),
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
        active.append(AuditLogMiddleware())
        active.append(CostBudgetMiddleware())
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
