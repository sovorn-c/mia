"""Interactive multiline prompt input with autocomplete and submit handlers."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Static


class PromptInputBar(Vertical):
    """Input bar with Carrot Orange prompt indicator and auto-target parsing."""

    class PromptSubmitted(Message):
        """Emitted when user submits a prompt."""

        def __init__(self, target_agent: str, prompt_text: str) -> None:
            super().__init__()
            self.target_agent = target_agent
            self.prompt_text = prompt_text

    def __init__(self, default_target: str = "lead", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_target = default_target
        self.prefix_widget = Static(Text("🥕 > ", style="bold #FF7A00"), classes="input-prefix")
        self.input_widget = Input(
            placeholder=f"Prompt @{self.default_target} (type @agent to direct)...",
            id="prompt-text-input",
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="input-row"):
            yield self.prefix_widget
            yield self.input_widget

    def set_target(self, target_agent: str) -> None:
        """Update placeholder to reflect currently focused agent."""
        self.default_target = target_agent
        self.input_widget.placeholder = (
            f"Prompt @{target_agent} (type @agent to direct, /help for commands)..."
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key submission."""
        raw_text = event.value.strip()
        if not raw_text:
            return

        target = self.default_target
        prompt = raw_text

        # Check if user prefixed prompt with @agent_id
        if raw_text.startswith("@"):
            parts = raw_text.split(" ", 1)
            target_candidate = parts[0][1:].strip().lower()
            if len(parts) > 1:
                target = target_candidate
                prompt = parts[1].strip()
            else:
                target = target_candidate
                prompt = ""

        if prompt:
            self.input_widget.value = ""
            self.post_message(self.PromptSubmitted(target_agent=target, prompt_text=prompt))
