"""Herdr-style Sidebar widget displaying agent roster and real-time state."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from mia_agent.herd.models import AgentState, ManagedAgent


class AgentListItem(Vertical):
    """Visual card for an individual agent in the roster."""

    def __init__(self, agent: ManagedAgent, is_active: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.agent = agent
        self.is_active = is_active
        if is_active:
            self.add_class("-active")

    def compose(self) -> ComposeResult:
        yield Static(self._build_header(), classes="agent-item-header")
        yield Static(self._build_details(), classes="agent-item-details")

    def update_agent(self, agent: ManagedAgent, is_active: bool | None = None) -> None:
        """Update rendered state."""
        self.agent = agent
        if is_active is not None:
            self.is_active = is_active
            if self.is_active:
                self.add_class("-active")
            else:
                self.remove_class("-active")
        self.query_one(".agent-item-header", Static).update(self._build_header())
        self.query_one(".agent-item-details", Static).update(self._build_details())

    def _build_header(self) -> Text:
        # Status icon
        if self.agent.state == AgentState.WORKING:
            status_icon = Text("🟢 ", style="#10B981")
        elif self.agent.state == AgentState.BLOCKED:
            status_icon = Text("🟡 ", style="#F59E0B")
        elif self.agent.state == AgentState.DONE:
            status_icon = Text("🔵 ", style="#3B82F6")
        elif self.agent.state == AgentState.ERROR:
            status_icon = Text("🔴 ", style="#EF4444")
        else:
            status_icon = Text("⚪ ", style="#6B7280")

        handle_style = "bold #FF7A00" if self.is_active else "bold #F3F4F6"
        return Text.assemble(
            status_icon,
            (f"@{self.agent.id} ", handle_style),
            (f"[{self.agent.profile}]", "dim #9CA3AF"),
        )

    def _build_details(self) -> Text:
        step_str = f"Step: {self.agent.current_step}/{self.agent.max_steps}"
        tokens_str = f"Tokens: {self.agent.total_tokens:,}"
        cost_str = f" | ${self.agent.total_cost_usd:.3f}" if self.agent.total_cost_usd > 0 else ""
        return Text(f"{self.agent.name}\n{step_str} | {tokens_str}{cost_str}", style="dim #9CA3AF")


class HerdSidebar(Vertical):
    """Sidebar containing the list of active agents in the herd."""

    class AgentSelected(Message):
        """Emitted when user selects an agent from the sidebar."""

        def __init__(self, agent_id: str) -> None:
            super().__init__()
            self.agent_id = agent_id

    def __init__(self, agents: list[ManagedAgent], active_id: str = "lead", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._agents = {a.id: a for a in agents}
        self.active_id = active_id
        self.scroll_container = VerticalScroll(id="sidebar-agents-scroll")

    def compose(self) -> ComposeResult:
        yield Static("🥕 HERD ROSTER", classes="sidebar-title")
        with self.scroll_container:
            for agent in self._agents.values():
                yield AgentListItem(
                    agent=agent,
                    is_active=(agent.id == self.active_id),
                    id=f"agent-item-{agent.id}",
                )

    def update_agent_list(self, agents: list[ManagedAgent], active_id: str | None = None) -> None:
        """Refresh agent list items."""
        if active_id:
            self.active_id = active_id
        self._agents = {a.id: a for a in agents}

        for agent in agents:
            try:
                item = self.query_one(f"#agent-item-{agent.id}", AgentListItem)
                item.update_agent(agent, is_active=(agent.id == self.active_id))
            except Exception:
                # Mount new agent
                new_item = AgentListItem(
                    agent=agent,
                    is_active=(agent.id == self.active_id),
                    id=f"agent-item-{agent.id}",
                )
                self.scroll_container.mount(new_item)

    def on_click(self, event: object) -> None:
        """Handle click on an agent item."""
        target = getattr(event, "widget", None)
        while target and not isinstance(target, AgentListItem):
            target = getattr(target, "parent", None)

        if isinstance(target, AgentListItem):
            self.active_id = target.agent.id
            self.post_message(self.AgentSelected(self.active_id))
            self.update_agent_list(list(self._agents.values()), active_id=self.active_id)
