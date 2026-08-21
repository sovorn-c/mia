"""Interactive prompt input with history cycling, mention routing, and slash commands."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.message import Message
from textual.widgets import Input, Static


class PromptInputBar(Vertical):
    """Input bar with Carrot Orange prompt indicator, command history, and target routing."""

    class PromptSubmitted(Message):
        """Emitted when user submits a prompt."""

        def __init__(self, target_agent: str, prompt_text: str) -> None:
            super().__init__()
            self.target_agent = target_agent
            self.prompt_text = prompt_text

    class SlashCommandTriggered(Message):
        """Emitted when user enters a slash command (/model, /profile, etc.)."""

        def __init__(self, command: str, args: str) -> None:
            super().__init__()
            self.command = command
            self.args = args

    def __init__(self, default_target: str = "lead", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_target = default_target
        self._history: list[str] = []
        self._history_idx: int = -1

        self.prefix_widget = Static(Text("🥕 > ", style="bold #FF7A00"), classes="input-prefix")
        self.input_widget = Input(
            placeholder=f"Prompt @{self.default_target} (type @agent or /help)...",
            id="prompt-text-input",
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="input-row"):
            yield self.prefix_widget
            yield self.input_widget

    def set_target(self, target_agent: str) -> None:
        """Update placeholder to reflect currently focused agent."""
        self.default_target = target_agent
        self.input_widget.placeholder = f"Prompt @{target_agent} (type @agent or /help)..."

    def on_key(self, event: Key) -> None:
        """Handle Up/Down arrow keys for input history navigation."""
        if event.key == "up" and self._history:
            if self._history_idx == -1:
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
            self.input_widget.value = self._history[self._history_idx]
            self.input_widget.cursor_position = len(self.input_widget.value)
            event.prevent_default()
            event.stop()
        elif event.key == "down" and self._history:
            if self._history_idx != -1:
                if self._history_idx < len(self._history) - 1:
                    self._history_idx += 1
                    self.input_widget.value = self._history[self._history_idx]
                else:
                    self._history_idx = -1
                    self.input_widget.value = ""
                self.input_widget.cursor_position = len(self.input_widget.value)
                event.prevent_default()
                event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key submission."""
        raw_text = event.value.strip()
        if not raw_text:
            return

        # Save to history
        self._history.append(raw_text)
        self._history_idx = -1
        self.input_widget.value = ""

        # Check for slash commands (/model, /profile, /compact, /clear, /help)
        if raw_text.startswith("/"):
            parts = raw_text[1:].split(" ", 1)
            cmd = parts[0].lower().strip()
            args = parts[1].strip() if len(parts) > 1 else ""
            self.post_message(self.SlashCommandTriggered(command=cmd, args=args))
            return

        # Check if user prefixed prompt with @agent_id
        target = self.default_target
        prompt = raw_text

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
            self.post_message(self.PromptSubmitted(target_agent=target, prompt_text=prompt))
