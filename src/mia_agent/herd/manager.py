"""Central orchestrator managing multi-agent lifecycles, background execution, and event streams."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from mia_agent.auth.config import ConfigManager
from mia_agent.events import AgentEvent
from mia_agent.harness import AgentHarness
from mia_agent.herd.models import (
    AgentEventEnvelope,
    AgentSpawnedEvent,
    AgentState,
    AgentStateChangedEvent,
    HerdEvent,
    InterAgentMessageEvent,
    ManagedAgent,
)
from mia_agent.herd.tools import InvokeSubagentTool, SendMessageTool
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.jsonl import JsonlSessionStore
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool


class HerdManager:
    """Manages a registry of concurrent AgentHarness workers and broadcasts typed HerdEvents."""

    def __init__(
        self,
        *,
        config_manager: ConfigManager | None = None,
        profile_manager: ProfileManager | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.config_mgr = config_manager or ConfigManager()
        self.profile_mgr = profile_manager or ProfileManager()
        self.cwd = cwd or Path.cwd()

        self._agents: dict[str, ManagedAgent] = {}
        self._harnesses: dict[str, AgentHarness] = {}
        self._listeners: list[Callable[[HerdEvent], Any]] = []
        self._background_tasks: dict[str, asyncio.Task[Any]] = {}

    def subscribe(self, listener: Callable[[HerdEvent], Any]) -> None:
        """Subscribe a callback to all published HerdEvents."""
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[HerdEvent], Any]) -> None:
        """Remove a subscriber callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def emit(self, event: HerdEvent) -> None:
        """Broadcast an event to all subscribers."""
        for listener in list(self._listeners):
            try:
                res = listener(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def list_agents(self) -> list[ManagedAgent]:
        """Return list of all registered managed agents."""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> ManagedAgent | None:
        """Get agent descriptor by ID."""
        return self._agents.get(agent_id.lower().strip())

    def set_agent_state(self, agent_id: str, new_state: AgentState, reason: str = "") -> None:
        """Update an agent's operational state and emit a state change event."""
        agent = self.get_agent(agent_id)
        if not agent:
            return
        if agent.state != new_state:
            prev = agent.state
            agent.state = new_state
            evt = AgentStateChangedEvent(
                agent_id=agent.id,
                previous_state=prev,
                new_state=new_state,
                reason=reason,
            )
            # Schedule async emit
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.emit(evt))
            except RuntimeError:
                pass

    def create_provider_for_model(self, model_name: str) -> tuple[LLMProvider, str]:
        """Instantiate LLMProvider using resolved credentials."""
        provider_name, actual_model, api_key, base_url = self.config_mgr.resolve_credentials(
            model=model_name
        )
        if provider_name == "anthropic":
            return AnthropicProvider(api_key=api_key, base_url=base_url), actual_model
        return OpenAICompatibleProvider(api_key=api_key, base_url=base_url), actual_model

    def build_tools_for_agent(self, agent_id: str, profile_name: str) -> list[Any]:
        """Assemble coding tools and inter-agent coordination tools."""
        profile = self.profile_mgr.get_profile(profile_name)

        base_tools: list[Any] = [
            ReadFileTool(cwd=self.cwd),
            WriteFileTool(cwd=self.cwd),
            EditFileTool(cwd=self.cwd),
            BashTool(cwd=self.cwd),
        ]
        filtered_tools = self.profile_mgr.filter_tools(profile, base_tools)

        # Append coordination tools
        filtered_tools.append(InvokeSubagentTool(self))
        filtered_tools.append(SendMessageTool(self, sender_id=agent_id))
        return filtered_tools

    def spawn_agent(
        self,
        *,
        agent_id: str,
        name: str,
        profile: str = "coding",
        model: str | None = None,
        custom_provider: LLMProvider | None = None,
    ) -> ManagedAgent:
        """Register and initialize an AgentHarness worker."""
        clean_id = agent_id.lower().strip().lstrip("@")
        if clean_id in self._agents:
            return self._agents[clean_id]

        prof = self.profile_mgr.get_profile(profile)
        target_model = model or prof.model or self.config_mgr.config.default_model

        if custom_provider:
            provider = custom_provider
            resolved_model = target_model
        else:
            provider, resolved_model = self.create_provider_for_model(target_model)

        tools = self.build_tools_for_agent(clean_id, prof.name)
        pipeline = ToolPipeline(
            [
                SecurityGuardMiddleware(),
                AuditLogMiddleware(),
                CostBudgetMiddleware(),
            ]
        )

        session_dir = self.profile_mgr.get_session_dir(prof.name)
        session_file = session_dir / f"herd_{clean_id}.jsonl"
        session_store = JsonlSessionStore(session_file)
        compactor = ContextCompactor(
            context_window_tokens=prof.context_window_tokens
            or self.config_mgr.config.context_window_tokens,
            compaction_threshold_ratio=prof.compaction_threshold_ratio
            or self.config_mgr.config.compaction_threshold_ratio,
        )

        harness = AgentHarness(
            provider=provider,
            model=resolved_model,
            system_prompt=prof.system_prompt,
            tools=tools,
            pipeline=pipeline,
            max_steps_per_turn=prof.max_steps_per_turn,
            session_id=clean_id,
            session_store=session_store,
            compactor=compactor,
        )

        managed = ManagedAgent(
            id=clean_id,
            name=name,
            profile=prof.name,
            model=resolved_model,
            state=AgentState.IDLE,
            session_id=clean_id,
        )

        self._agents[clean_id] = managed
        self._harnesses[clean_id] = harness

        evt = AgentSpawnedEvent(agent=managed)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(evt))
        except RuntimeError:
            pass

        return managed

    async def run_agent(self, agent_id: str, prompt_text: str) -> AsyncIterator[AgentEvent]:
        """Execute a prompt turn for the given agent, broadcasting events through the herd bus."""
        clean_id = agent_id.lower().strip().lstrip("@")
        agent = self.get_agent(clean_id)
        if not agent or clean_id not in self._harnesses:
            raise ValueError(f"Agent '@{clean_id}' does not exist in the herd.")

        harness = self._harnesses[clean_id]
        self.set_agent_state(clean_id, AgentState.WORKING)

        last_stop_reason = "stop"
        try:
            async for event in harness.prompt(prompt_text):
                # Update tokens and step
                if event.type == "step_end":
                    agent.current_step = getattr(event, "step_index", agent.current_step)
                    agent.total_tokens += getattr(event, "input_tokens", 0) + getattr(
                        event, "output_tokens", 0
                    )
                elif event.type == "turn_complete":
                    agent.total_cost_usd += getattr(event, "total_cost_usd", 0.0)
                    last_stop_reason = getattr(event, "stop_reason", "stop")

                # Wrap and emit envelope
                envelope = AgentEventEnvelope(agent_id=clean_id, event=event)
                await self.emit(envelope)
                yield event

            final_state = AgentState.DONE if last_stop_reason == "stop" else AgentState.IDLE
            self.set_agent_state(clean_id, final_state)
        except Exception as exc:
            self.set_agent_state(clean_id, AgentState.ERROR, reason=str(exc))
            raise

    async def delegate_task(
        self,
        *,
        target_id: str,
        prompt: str,
        profile: str | None = None,
    ) -> str:
        """Delegate task to a subagent and await final assistant response."""
        clean_id = target_id.lower().strip().lstrip("@")
        if clean_id not in self._agents:
            self.spawn_agent(
                agent_id=clean_id,
                name=f"Subagent @{clean_id}",
                profile=profile or "coding",
            )

        accumulated_response: list[str] = []
        async for event in self.run_agent(clean_id, prompt):
            if event.type == "assistant_chunk" and getattr(event, "delta_text", None):
                accumulated_response.append(event.delta_text)

        result_text = "".join(accumulated_response).strip()
        return result_text or f"Task completed by @{clean_id}."

    async def send_direct_message(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
    ) -> None:
        """Deliver a direct message event between agents."""
        clean_recipient = recipient_id.lower().strip().lstrip("@")
        clean_sender = sender_id.lower().strip().lstrip("@")

        recipient = self.get_agent(clean_recipient)
        if recipient:
            recipient.unread_messages += 1

        evt = InterAgentMessageEvent(
            sender_id=clean_sender,
            recipient_id=clean_recipient,
            content=content,
        )
        await self.emit(evt)
