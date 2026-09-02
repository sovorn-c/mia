"""Agent runtime construction and policy wiring."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import Any

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.harness import AgentHarness
from mia_agent.orchestration_models import AgentRuntime, RuntimeIdentity, _profile_from_agent
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.entries import CustomEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.access import AccessPolicyMiddleware, ApprovalCallback, tool_effect
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool


class AgentRuntimeFactory:
    """Build every Agent with the same Tool, provider, and Session invariants."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager | None = None,
        profile_manager: ProfileManager | None = None,
        config_manager: ConfigManager | None = None,
        delegation_service: Any | None = None,
    ) -> None:
        self.profile_manager = profile_manager or ProfileManager()
        self.agent_manager = agent_manager or AgentManager(profile_manager=self.profile_manager)
        self.config_manager = config_manager or ConfigManager()
        self.delegation_service = delegation_service

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
    ) -> AgentRuntime:
        """Construct an Agent-scoped harness, restoring and annotating its Session."""
        if identity.profile is not None:
            # Compatibility callers still provide Profile and retain their old Session path.
            profile = self.profile_manager.get_profile(identity.profile)
            try:
                agent = self.agent_manager.get_agent(identity.agent_id)
            except ValueError:
                agent = self.agent_manager.get_agent(profile.name)
            session_dir = self.profile_manager.get_session_dir(profile.name)
            namespace = "orchestration"
        else:
            agent = self.agent_manager.get_agent(identity.agent_id)
            profile = _profile_from_agent(agent)
            session_dir = self.agent_manager.get_session_dir(agent.agent_id)
            namespace = "agent"

        if access_policy_override is not None or capabilities_override is not None:
            updates: dict[str, Any] = {}
            if access_policy_override is not None:
                updates["access_policy"] = access_policy_override
            if capabilities_override is not None:
                updates["tools"] = list(capabilities_override)
            agent = agent.model_copy(update=updates)
            profile = _profile_from_agent(agent)

        work_dir = cwd or Path.cwd()
        target_model = model_override or agent.model or ("" if provider else "claude-3-5-sonnet")

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

        available_tools = [
            ReadFileTool(cwd=work_dir),
            WriteFileTool(cwd=work_dir),
            EditFileTool(cwd=work_dir),
            BashTool(cwd=work_dir),
        ]
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
        pipeline = self._build_pipeline(
            agent.middlewares,
            agent=agent,
            identity=identity,
            approval_callback=approval_callback,
            full_access_confirmed=(
                agent.full_access_confirmed
                if full_access_confirmed is None
                else full_access_confirmed
            ),
            tool_effects={
                tool.name: tool_effect(tool.name, {"effect": tool.effect})
                for tool in available_tools
            },
        )
        session_store = JsonlSessionStore(session_dir / f"{identity.session_id}.jsonl")
        initial_messages, last_entry_id = self._restore_session(session_store)
        last_entry_id = self._persist_identity(
            identity, session_store, last_entry_id, namespace=namespace
        )

        config = self.config_manager.config
        compaction_ratio = (
            compaction_threshold
            if compaction_threshold is not None
            else (
                agent.compaction_threshold_ratio
                if agent.compaction_threshold_ratio is not None
                else config.compaction_threshold_ratio
            )
        )
        window_tokens = (
            context_window
            if context_window is not None
            else (
                agent.context_window_tokens
                if agent.context_window_tokens is not None
                else config.context_window_tokens
            )
        )
        harness = AgentHarness(
            provider=provider,
            model=model_name,
            system_prompt=agent.instructions,
            tools=tools,
            pipeline=pipeline,
            max_steps_per_turn=agent.max_steps_per_turn,
            session_id=identity.session_id,
            messages=initial_messages,
            session_store=session_store,
            compactor=ContextCompactor(
                context_window_tokens=window_tokens,
                compaction_threshold_ratio=compaction_ratio,
            ),
            last_entry_id=last_entry_id,
            tool_context_metadata={
                "agent_id": agent.agent_id,
                "run_id": identity.run_id,
                "task_id": identity.task_id,
                "session_id": identity.session_id,
            },
        )
        return AgentRuntime(
            harness=harness,
            identity=identity,
            profile=profile,
            session_store=session_store,
            agent=agent,
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
        if agent is not None and identity is not None:
            active.append(
                AccessPolicyMiddleware(
                    access_policy=agent.access_policy,
                    capabilities=agent.tools,
                    approval_callback=approval_callback,
                    full_access_confirmed=(
                        agent.full_access_confirmed
                        if full_access_confirmed is None
                        else full_access_confirmed
                    ),
                    agent_id=agent.agent_id,
                    run_id=identity.run_id,
                    task_id=identity.task_id,
                    session_id=identity.session_id,
                    tool_effects=tool_effects,
                )
            )
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
        *,
        namespace: str = "orchestration",
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
