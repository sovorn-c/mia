"""Textual presentation adapter for canonical Agent Runs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from mia_agent.agent_runner import AgentRunner
from mia_agent.agents import AgentManager
from mia_agent.events import AssistantChunkEvent, StepEndEvent, TurnCompleteEvent
from mia_agent.runtime_events import AgentEventEnvelope, error_envelope
from mia_agent.runtime_models import RuntimeIdentity
from mia_ai.providers.base import LLMProvider
from mia_cli.tui.panes import AgentPaneContainer
from mia_cli.tui.sidebar import AgentSidebar
from mia_cli.tui.theme import MIA_THEME_CSS
from mia_cli.tui.widgets.approval_modal import ApprovalModal
from mia_cli.tui.widgets.prompt_editor import MiaPromptEditor
from mia_middleware.access import ApprovalCallback, ApprovalRequest


class MiaHeader(Static):
    """Header displaying the active model and current Run metrics."""

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
            ("v0.6.0  ", "dim #9CA3AF"),
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
            (" [Ctrl+Q] ", "bold #FF7A00"),
            ("Quit", "#9CA3AF"),
        )
        yield Static(shortcuts)


class MiaApp(App[None]):
    """Full-screen Textual frontend for canonical Agent Runs."""

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
        agent_manager: AgentManager | None = None,
        agent_runner: AgentRunner | None = None,
        model_name: str = "mimo-v2.5",
        cwd: Path | None = None,
        provider: LLMProvider | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        super().__init__()
        self.agent_manager = agent_manager or AgentManager()
        self.agent_runner = agent_runner or AgentRunner(agent_manager=self.agent_manager)
        self.model_name = model_name
        self.cwd = cwd or Path.cwd()
        self.provider = provider
        self.approval_callback = approval_callback or self._request_tool_approval
        self.active_agent_id = self.agent_manager.default_agent().agent_id
        self.total_tokens = 0
        self.total_cost = 0.0

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

    def _request_tool_approval(self, request: ApprovalRequest) -> Awaitable[bool]:
        """Open a modal and resolve the Tool approval when the user responds."""
        future = asyncio.get_running_loop().create_future()

        def complete(result: bool | None) -> None:
            if not future.done():
                future.set_result(bool(result))

        self.push_screen(
            ApprovalModal(
                action_name=request.tool_name,
                details=json.dumps(request.arguments, ensure_ascii=False),
                agent_id=request.agent_id or self.active_agent_id,
            ),
            complete,
        )
        return future

    def on_mount(self) -> None:
        """Load the persisted Agent roster without creating transient workers."""
        agents = self.agent_manager.list_agents()
        if not any(agent.agent_id == self.active_agent_id for agent in agents) and agents:
            self.active_agent_id = agents[0].agent_id
            self.pane_container.switch_to_agent(self.active_agent_id)
            self.prompt_editor.set_target(self.active_agent_id)
        self.sidebar_widget.update_agent_list(agents, active_id=self.active_agent_id)

    def _process_event_in_main_thread(self, envelope: AgentEventEnvelope) -> None:
        """Render one canonical Agent event in the target transcript."""
        event = envelope.event
        if isinstance(event, StepEndEvent):
            self.total_tokens += event.input_tokens + event.output_tokens
        elif isinstance(event, TurnCompleteEvent):
            self.total_cost += event.total_cost_usd
        self.header_widget.update_metrics(self.total_tokens, self.total_cost)
        self.pane_container.dispatch_event(envelope.agent_id, event)

    def on_agent_sidebar_agent_selected(self, message: AgentSidebar.AgentSelected) -> None:
        """Select an Agent from the sidebar."""
        self.active_agent_id = message.agent_id
        self.pane_container.switch_to_agent(self.active_agent_id)
        self.prompt_editor.set_target(self.active_agent_id)

    def on_mia_prompt_editor_slash_command_triggered(
        self, message: MiaPromptEditor.SlashCommandTriggered
    ) -> None:
        """Handle the small set of frontend-local slash commands."""
        cmd = message.command
        args = message.args

        if cmd == "help":
            help_msg = (
                "**🥕 Mia Commands & Shortcuts:**\n\n"
                "- `@<agent> <prompt>`: Send a prompt to an Agent\n"
                "- `/model <name>`: Switch the active model\n"
                "- `/clear`: Clear the active Agent transcript\n"
                "- `Alt+1..9`: Switch between Agents\n"
                "- `Ctrl+N`: Create a persisted Agent\n"
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
            self.header_widget.update_metrics(self.total_tokens, self.total_cost)
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
        """Submit a prompt for an existing Agent."""
        target_id = message.target_agent
        prompt_text = message.prompt_text
        try:
            self.agent_manager.get_agent(target_id)
        except ValueError as exc:
            self.pane_container.switch_to_agent(self.active_agent_id)
            self.pane_container.dispatch_event(
                self.active_agent_id,
                AssistantChunkEvent(delta_text=f"Agent error: {exc}"),
            )
            return

        self.active_agent_id = target_id
        self.sidebar_widget.update_agent_list(
            self.agent_manager.list_agents(), active_id=self.active_agent_id
        )
        self.pane_container.switch_to_agent(self.active_agent_id)
        self.pane_container.add_user_message(self.active_agent_id, prompt_text)
        self.prompt_editor.set_target(self.active_agent_id)
        self.run_agent_turn_worker(target_id, prompt_text)

    @work(exclusive=False, thread=False)
    async def run_agent_turn_worker(self, agent_id: str, prompt_text: str) -> None:
        """Run one Agent prompt through AgentRunner and render its events."""
        try:
            async for envelope in self.agent_runner.prompt(
                prompt_text,
                agent_id=agent_id,
                provider=self.provider,
                model_override=self.model_name,
                cwd=self.cwd,
                session_id=f"tui_{agent_id}",
                approval_callback=self.approval_callback,
            ):
                self._process_event_in_main_thread(envelope)
        except Exception as exc:
            identity = RuntimeIdentity(
                run_id="tui",
                task_id="root",
                agent_id=agent_id,
                session_id=f"tui_{agent_id}",
            )
            self._process_event_in_main_thread(error_envelope(identity, "tui", str(exc)))

    def action_switch_agent(self, index: int) -> None:
        """Switch Agent via an Alt+number shortcut."""
        agents = self.agent_manager.list_agents()
        if 1 <= index <= len(agents):
            target = agents[index - 1]
            self.active_agent_id = target.agent_id
            self.sidebar_widget.update_agent_list(agents, active_id=self.active_agent_id)
            self.pane_container.switch_to_agent(self.active_agent_id)
            self.prompt_editor.set_target(self.active_agent_id)

    def action_spawn_new_agent(self) -> None:
        """Create and select a persisted coding-style Agent."""
        existing = len(self.agent_manager.list_agents())
        new_id = f"worker{existing + 1}"
        self.agent_manager.create_agent(
            new_id,
            display_name=f"Worker {existing + 1}",
            instructions="You are a helpful local coding Agent.",
            model=self.model_name or None,
            tools=["read_file", "write_file", "edit_file", "bash"],
            access_policy="approval-required",
        )
        agents = self.agent_manager.list_agents()
        self.active_agent_id = new_id
        self.sidebar_widget.update_agent_list(agents, active_id=new_id)
        self.pane_container.switch_to_agent(new_id)
        self.prompt_editor.set_target(new_id)
