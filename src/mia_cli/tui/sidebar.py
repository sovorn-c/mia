"""Sidebar widget displaying the Agent roster and access scope."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from mia_agent.agents import Agent


class AgentListItem(Vertical):
    """Visual card for one Agent in the roster."""

    def __init__(self, agent: Agent, is_active: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.agent = agent
        self.is_active = is_active
        if is_active:
            self.add_class("-active")

    def compose(self) -> ComposeResult:
        yield Static(self._build_header(), classes="agent-item-header")
        yield Static(self._build_details(), classes="agent-item-details")

    def update_agent(self, agent: Agent, is_active: bool | None = None) -> None:
        """Update rendered Agent data."""
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
        handle_style = "bold #FF7A00" if self.is_active else "bold #F3F4F6"
        return Text.assemble(
            ("● ", "#10B981" if self.is_active else "#6B7280"),
            (f"@{self.agent.agent_id} ", handle_style),
            (f"[{self.agent.access_policy}]", "dim #9CA3AF"),
        )

    def _build_details(self) -> Text:
        tools = ", ".join(self.agent.tools) if self.agent.tools else "(none)"
        return Text(
            f"{self.agent.display_name}\nTools: {tools}",
            style="dim #9CA3AF",
        )


class AgentSidebar(Vertical):
    """Sidebar containing the selectable Agent roster."""

    class AgentSelected(Message):
        """Emitted when the user selects an Agent."""

        def __init__(self, agent_id: str) -> None:
            super().__init__()
            self.agent_id = agent_id

    def __init__(self, agents: list[Agent], active_id: str = "mia", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._agents = {agent.agent_id: agent for agent in agents}
        self.active_id = active_id
        self.scroll_container = VerticalScroll(id="sidebar-agents-scroll")

    def compose(self) -> ComposeResult:
        yield Static("🥕 AGENTS", classes="sidebar-title")
        with self.scroll_container:
            for agent in self._agents.values():
                yield AgentListItem(
                    agent=agent,
                    is_active=(agent.agent_id == self.active_id),
                    id=f"agent-item-{agent.agent_id}",
                )

    def update_agent_list(self, agents: list[Agent], active_id: str | None = None) -> None:
        """Refresh Agent list items."""
        if active_id:
            self.active_id = active_id
        self._agents = {agent.agent_id: agent for agent in agents}

        for agent in agents:
            try:
                item = self.query_one(f"#agent-item-{agent.agent_id}", AgentListItem)
                item.update_agent(agent, is_active=(agent.agent_id == self.active_id))
            except Exception:
                new_item = AgentListItem(
                    agent=agent,
                    is_active=(agent.agent_id == self.active_id),
                    id=f"agent-item-{agent.agent_id}",
                )
                self.scroll_container.mount(new_item)

    def on_click(self, event: object) -> None:
        """Handle click on an Agent item."""
        target = getattr(event, "widget", None)
        while target and not isinstance(target, AgentListItem):
            target = getattr(target, "parent", None)

        if isinstance(target, AgentListItem):
            self.active_id = target.agent.agent_id
            self.post_message(self.AgentSelected(self.active_id))
            self.update_agent_list(list(self._agents.values()), active_id=self.active_id)
