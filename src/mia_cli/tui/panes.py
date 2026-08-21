"""Active agent transcript pane container managing cards and live stream rendering."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from mia_agent.events import (
    AgentEvent,
    AssistantChunkEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnStartEvent,
)
from mia_cli.tui.widgets.message_card import AssistantMessageCard, UserMessageCard
from mia_cli.tui.widgets.thinking_drawer import ThoughtDrawer
from mia_cli.tui.widgets.tool_card import ToolCallCard


class AgentTranscriptView(VerticalScroll):
    """Scrollable transcript for a single agent."""

    def __init__(self, agent_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self._current_assistant_card: AssistantMessageCard | None = None
        self._current_thought_drawer: ThoughtDrawer | None = None
        self._active_tool_cards: dict[str, ToolCallCard] = {}

    def add_user_message(self, prompt: str) -> None:
        """Add user prompt card."""
        self._current_assistant_card = None
        self._current_thought_drawer = None
        card = UserMessageCard(prompt=prompt, target_agent=self.agent_id)
        self.mount(card)
        self.scroll_end(animate=False)

    def handle_agent_event(self, event: AgentEvent) -> None:
        """Process incoming live streaming event from AgentHarness."""
        if isinstance(event, TurnStartEvent):
            self._current_assistant_card = None
            self._current_thought_drawer = None

        elif isinstance(event, AssistantChunkEvent):
            if event.thought_delta:
                if not self._current_thought_drawer:
                    self._current_assistant_card = None
                    self._current_thought_drawer = ThoughtDrawer(
                        initial_thought=event.thought_delta
                    )
                    self.mount(self._current_thought_drawer)
                else:
                    self._current_thought_drawer.append_thought(event.thought_delta)
                self.scroll_end(animate=False)

            if event.delta_text:
                if self._current_thought_drawer and not self._current_thought_drawer.is_collapsed:
                    # Auto-collapse thought drawer when real response starts
                    self._current_thought_drawer.toggle_collapse()

                if not self._current_assistant_card:
                    self._current_assistant_card = AssistantMessageCard(
                        initial_text=event.delta_text
                    )
                    self.mount(self._current_assistant_card)
                else:
                    self._current_assistant_card.append_text(event.delta_text)
                self.scroll_end(animate=False)

        elif isinstance(event, ToolCallEvent):
            self._current_assistant_card = None
            self._current_thought_drawer = None
            card = ToolCallCard(
                call_id=event.call_id,
                tool_name=event.tool_name,
                arguments=event.arguments,
            )
            self._active_tool_cards[event.call_id] = card
            self.mount(card)
            self.scroll_end(animate=False)

        elif isinstance(event, ToolResultEvent):
            res_card = self._active_tool_cards.get(event.call_id)
            if res_card:
                res_card.set_result(
                    output=event.output,
                    is_error=event.is_error,
                    duration_ms=event.duration_ms,
                )
            self.scroll_end(animate=False)


class AgentPaneContainer(Vertical):
    """Container holding active transcript panes for all agents and switching visibility."""

    def __init__(self, active_agent_id: str = "lead", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.active_agent_id = active_agent_id
        self._transcripts: dict[str, AgentTranscriptView] = {}
        self.header_title = Static("", classes="pane-header-title")

    def compose(self) -> ComposeResult:
        yield self.header_title

    def on_mount(self) -> None:
        self.switch_to_agent(self.active_agent_id)

    def switch_to_agent(self, agent_id: str) -> None:
        """Switch active visible transcript pane."""
        self.active_agent_id = agent_id
        self.header_title.update(
            Text.assemble(
                ("🥕 Active Stream: ", "bold #FF7A00"),
                (f"@{agent_id}", "bold #38BDF8"),
            )
        )

        for aid, view in self._transcripts.items():
            view.display = aid == agent_id

        if agent_id not in self._transcripts:
            new_view = AgentTranscriptView(agent_id=agent_id, id=f"transcript-view-{agent_id}")
            self._transcripts[agent_id] = new_view
            self.mount(new_view)

        self._transcripts[agent_id].display = True

    def dispatch_event(self, agent_id: str, event: AgentEvent) -> None:
        """Forward an event to the target agent's transcript."""
        if agent_id not in self._transcripts:
            new_view = AgentTranscriptView(agent_id=agent_id, id=f"transcript-view-{agent_id}")
            new_view.display = agent_id == self.active_agent_id
            self._transcripts[agent_id] = new_view
            self.mount(new_view)

        self._transcripts[agent_id].handle_agent_event(event)

    def add_user_message(self, agent_id: str, prompt: str) -> None:
        """Add user message card to target agent transcript."""
        if agent_id not in self._transcripts:
            self.switch_to_agent(agent_id)
        self._transcripts[agent_id].add_user_message(prompt)
