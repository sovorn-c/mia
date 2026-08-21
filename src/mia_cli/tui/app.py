"""Main Textual Application for Mia AI Coding Agent with managed async workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from mia_agent.events import AssistantChunkEvent
from mia_agent.herd.manager import HerdManager
from mia_agent.herd.models import AgentEventEnvelope, HerdEvent
from mia_cli.tui.panes import AgentPaneContainer
from mia_cli.tui.sidebar import AgentSidebar
from mia_cli.tui.theme import MIA_THEME_CSS
from mia_cli.tui.widgets.prompt_editor import MiaPromptEditor


class MiaHeader(Static):
    """Modern header displaying active model, total cost, and token usage."""

    def __init__(self, model_name: str = "mimo-v2.5", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.model_name = model_name
        self.total_tokens = 0
        self.total_cost = 0.0

    def compose(self) -> ComposeResult:
        yield Static(self._build_content(), id="header-content")

    def update_metrics(self, total_tokens: int, total_cost: float) -> None:
        self.total_tokens = total_tokens
        self.total_cost = total_cost
        self.query_one("#header-content", Static).update(self._build_content())

    def _build_content(self) -> Text:
        cost_str = f"${self.total_cost:.4f}" if self.total_cost > 0 else "$0.0000"
        return Text.assemble(
            ("🥕 MIA ", "bold #FF7A00"),
            ("v0.2.0  ", "dim #9CA3AF"),
            ("│  Model: ", "#9CA3AF"),
            (f"{self.model_name}  ", "bold #38BDF8"),
            ("│  Tokens: ", "#9CA3AF"),
            (f"{self.total_tokens:,}  ", "bold #F3F4F6"),
            ("│  Cost: ", "#9CA3AF"),
            (cost_str, "bold #10B981"),
        )


class MiaFooter(Static):
    """Bottom status and shortcut indicator."""

    def compose(self) -> ComposeResult:
        shortcuts = Text.assemble(
            (" [Alt+1..9] ", "bold #FF7A00"),
            ("Switch Agent  ", "#9CA3AF"),
            (" [Ctrl+N] ", "bold #FF7A00"),
            ("New Agent  ", "#9CA3AF"),
            (" [Ctrl+C] ", "bold #FF7A00"),
            ("Cancel Turn  ", "#9CA3AF"),
            (" [Ctrl+Q] ", "bold #FF7A00"),
            ("Quit", "#9CA3AF"),
        )
        yield Static(shortcuts)


class MiaApp(App[None]):
    """Full-screen interactive Textual TUI for Mia."""

    CSS = MIA_THEME_CSS

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("alt+1", "switch_agent(1)", "Agent 1", show=False),
        Binding("alt+2", "switch_agent(2)", "Agent 2", show=False),
        Binding("alt+3", "switch_agent(3)", "Agent 3", show=False),
        Binding("alt+4", "switch_agent(4)", "Agent 4", show=False),
        Binding("ctrl+n", "spawn_new_agent", "New Agent", show=False),
    ]

    def __init__(
        self,
        herd_manager: HerdManager | None = None,
        model_name: str = "mimo-v2.5",
        cwd: Path | None = None,
    ) -> None:
        super().__init__()
        self.herd_manager = herd_manager or HerdManager(cwd=cwd)
        self.model_name = model_name
        self.active_agent_id = "lead"

        self.header_widget = MiaHeader(model_name=self.model_name)
        self.sidebar_widget = AgentSidebar(agents=[], active_id=self.active_agent_id)
        self.pane_container = AgentPaneContainer(active_agent_id=self.active_agent_id)
        self.prompt_editor = MiaPromptEditor(default_target=self.active_agent_id)
        self.footer_widget = MiaFooter()

    def compose(self) -> ComposeResult:
        yield self.header_widget
        with Horizontal(id="main-layout"):
            yield self.sidebar_widget
            yield self.pane_container
        yield self.prompt_editor
        yield self.footer_widget

    def on_mount(self) -> None:
        """Initialize default agents and subscribe to events."""
        # 1. Spawn default agents: @lead (architect) and @coder (coding)
        self.herd_manager.spawn_agent(
            agent_id="lead",
            name="Lead Architect",
            profile="architect",
            model=self.model_name,
        )
        self.herd_manager.spawn_agent(
            agent_id="coder",
            name="Senior Coder",
            profile="coding",
            model=self.model_name,
        )

        self.sidebar_widget.update_agent_list(
            self.herd_manager.list_agents(), active_id=self.active_agent_id
        )

        # 2. Subscribe to orchestrator events
        self.herd_manager.subscribe(self._on_herd_event)

    def _on_herd_event(self, event: HerdEvent) -> None:
        """Handle incoming asynchronous event from HerdManager."""
        self.call_later(self._process_event_in_main_thread, event)

    def _process_event_in_main_thread(self, event: HerdEvent) -> None:
        """Process event within Textual UI thread."""
        agents = self.herd_manager.list_agents()
        total_tokens = sum(a.total_tokens for a in agents)
        total_cost = sum(a.total_cost_usd for a in agents)
        self.header_widget.update_metrics(total_tokens, total_cost)
        self.sidebar_widget.update_agent_list(agents, active_id=self.active_agent_id)

        if isinstance(event, AgentEventEnvelope):
            self.pane_container.dispatch_event(event.agent_id, event.event)

    def on_agent_sidebar_agent_selected(self, message: AgentSidebar.AgentSelected) -> None:
        """User selected an agent from the sidebar."""
        self.active_agent_id = message.agent_id
        self.pane_container.switch_to_agent(self.active_agent_id)
        self.prompt_editor.set_target(self.active_agent_id)

    def on_mia_prompt_editor_slash_command_triggered(
        self, message: MiaPromptEditor.SlashCommandTriggered
    ) -> None:
        """Handle slash commands (/help, /model, /clear, /quit)."""
        cmd = message.command
        args = message.args

        if cmd == "help":
            help_msg = (
                "**🥕 Mia Commands & Shortcuts:**\n\n"
                "- `@<agent> <prompt>`: Send message to specific agent (e.g. `@coder fix tests`)\n"
                "- `/model <name>`: Switch active model (e.g. `/model mimo-v2.5`)\n"
                "- `/clear`: Clear active agent transcript\n"
                "- `Alt+1..9`: Switch between active agents\n"
                "- `Ctrl+N`: Spawn new worker agent\n"
                "- `Ctrl+Q`: Quit Mia"
            )
            self.pane_container.add_user_message(self.active_agent_id, "/help")
            self.pane_container.dispatch_event(
                self.active_agent_id,
                AssistantChunkEvent(delta_text=help_msg),
            )
        elif cmd == "model" and args:
            self.model_name = args
            self.header_widget.model_name = args
            self.header_widget.update_metrics(
                self.header_widget.total_tokens, self.header_widget.total_cost
            )
            self.pane_container.add_user_message(self.active_agent_id, f"/model {args}")
            self.pane_container.dispatch_event(
                self.active_agent_id,
                AssistantChunkEvent(delta_text=f"✓ Switched active model to `{args}`."),
            )
        elif cmd == "quit":
            self.exit()

    def on_mia_prompt_editor_prompt_submitted(
        self, message: MiaPromptEditor.PromptSubmitted
    ) -> None:
        """User submitted a prompt for an agent."""
        target_id = message.target_agent
        prompt_text = message.prompt_text

        # Ensure agent exists
        if not self.herd_manager.get_agent(target_id):
            self.herd_manager.spawn_agent(
                agent_id=target_id,
                name=f"Agent @{target_id}",
                profile="coding",
                model=self.model_name,
            )

        self.active_agent_id = target_id
        self.sidebar_widget.update_agent_list(
            self.herd_manager.list_agents(), active_id=self.active_agent_id
        )
        self.pane_container.switch_to_agent(self.active_agent_id)
        self.pane_container.add_user_message(self.active_agent_id, prompt_text)
        self.prompt_editor.set_target(self.active_agent_id)

        # Launch managed background agent worker
        self.run_agent_turn_worker(target_id, prompt_text)

    @work(exclusive=False, thread=False)
    async def run_agent_turn_worker(self, agent_id: str, prompt_text: str) -> None:
        """Execute agent turn within Textual's managed async worker framework."""
        try:
            async for _ in self.herd_manager.run_agent(agent_id, prompt_text):
                pass
        except Exception:
            pass

    def action_switch_agent(self, index: int) -> None:
        """Switch agent via Alt+1..9 shortcut."""
        agents = self.herd_manager.list_agents()
        if 1 <= index <= len(agents):
            target = agents[index - 1]
            self.active_agent_id = target.id
            self.sidebar_widget.update_agent_list(agents, active_id=self.active_agent_id)
            self.pane_container.switch_to_agent(self.active_agent_id)
            self.prompt_editor.set_target(self.active_agent_id)

    def action_spawn_new_agent(self) -> None:
        """Spawn a new worker agent via Ctrl+N."""
        existing = len(self.herd_manager.list_agents())
        new_id = f"worker{existing + 1}"
        self.herd_manager.spawn_agent(
            agent_id=new_id,
            name=f"Worker {existing + 1}",
            profile="coding",
            model=self.model_name,
        )
        self.action_switch_agent(len(self.herd_manager.list_agents()))


# Alias for backward compatibility
MiaHerdApp = MiaApp
