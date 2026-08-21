"""Production-grade multi-line prompt editor with auto-growth, history, and keybindings."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.message import Message
from textual.widgets import Static, TextArea


class MiaPromptEditor(Vertical):
    """Modern auto-expanding multi-line prompt editor with command history and slash routing."""

    DEFAULT_CSS = """
    MiaPromptEditor {
        height: auto;
        min-height: 4;
        max-height: 10;
        background: #181B22;
        border: solid #2D3342;
        padding: 0 1;
    }

    MiaPromptEditor:focus-within {
        border: solid #FF7A00;
    }

    #editor-row {
        height: auto;
    }

    .editor-prefix {
        width: 5;
        height: 100%;
        color: #FF7A00;
        text-style: bold;
        padding-top: 0;
    }

    #prompt-textarea {
        height: auto;
        min-height: 2;
        max-height: 8;
        background: #181B22;
        border: none;
        color: #F3F4F6;
    }

    #prompt-textarea:focus {
        border: none;
    }

    .editor-hint {
        height: 1;
        color: #6B7280;
        text-style: dim;
        margin-top: 0;
    }
    """

    class PromptSubmitted(Message):
        """Emitted when user submits prompt."""

        def __init__(self, target_agent: str, prompt_text: str) -> None:
            super().__init__()
            self.target_agent = target_agent
            self.prompt_text = prompt_text

    class SlashCommandTriggered(Message):
        """Emitted when user triggers a slash command."""

        def __init__(self, command: str, args: str) -> None:
            super().__init__()
            self.command = command
            self.args = args

    def __init__(self, default_target: str = "lead", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_target = default_target
        self._history: list[str] = []
        self._history_idx: int = -1

        self.prefix_widget = Static(Text("🥕 > ", style="bold #FF7A00"), classes="editor-prefix")
        self.textarea = TextArea(
            text="",
            id="prompt-textarea",
            language=None,
            theme="monokai",
            show_line_numbers=False,
        )
        self.hint_widget = Static(
            self._build_hint_text(),
            classes="editor-hint",
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="editor-row"):
            yield self.prefix_widget
            yield self.textarea
        yield self.hint_widget

    def set_target(self, target_agent: str) -> None:
        """Update target agent and hint bar."""
        self.default_target = target_agent
        self.hint_widget.update(self._build_hint_text())

    def _build_hint_text(self) -> Text:
        return Text.assemble(
            ("Target: ", "dim #9CA3AF"),
            (f"@{self.default_target}  ", "bold #38BDF8"),
            (
                "│  [Enter] Submit  │  [Shift+Enter] Newline  │  [↑/↓] History  │  /help",
                "dim #6B7280",
            ),
        )

    def on_key(self, event: Key) -> None:
        """Handle Enter to submit and Up/Down history cycling."""
        # Enter submits prompt (Shift+Enter inserts newline in TextArea)
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self._submit_current_text()
            return

        # Up arrow -> history previous
        if event.key == "up" and self._history:
            cursor_location = self.textarea.cursor_location
            if cursor_location[0] == 0:  # On first line
                event.prevent_default()
                event.stop()
                if self._history_idx == -1:
                    self._history_idx = len(self._history) - 1
                elif self._history_idx > 0:
                    self._history_idx -= 1
                self.textarea.text = self._history[self._history_idx]
                self.textarea.move_cursor((self.textarea.document.line_count - 1, 0))
                return

        # Down arrow -> history next
        if event.key == "down" and self._history:
            cursor_location = self.textarea.cursor_location
            if cursor_location[0] >= self.textarea.document.line_count - 1:  # On last line
                event.prevent_default()
                event.stop()
                if self._history_idx != -1:
                    if self._history_idx < len(self._history) - 1:
                        self._history_idx += 1
                        self.textarea.text = self._history[self._history_idx]
                    else:
                        self._history_idx = -1
                        self.textarea.text = ""
                return

    def _submit_current_text(self) -> None:
        raw_text = self.textarea.text.strip()
        if not raw_text:
            return

        # Record into history buffer
        self._history.append(raw_text)
        self._history_idx = -1
        self.textarea.text = ""

        # Check for slash commands (/model, /profile, /compact, /clear, /help, /quit)
        if raw_text.startswith("/") and "\n" not in raw_text:
            parts = raw_text[1:].split(" ", 1)
            cmd = parts[0].lower().strip()
            args = parts[1].strip() if len(parts) > 1 else ""
            self.post_message(self.SlashCommandTriggered(command=cmd, args=args))
            return

        # Check for mention prefix @agent
        target = self.default_target
        prompt = raw_text

        if raw_text.startswith("@"):
            first_line = raw_text.splitlines()[0]
            parts = first_line.split(" ", 1)
            target_candidate = parts[0][1:].strip().lower()
            if len(parts) > 1:
                target = target_candidate
                prompt = raw_text[len(parts[0]) :].strip()
            else:
                target = target_candidate
                prompt = "\n".join(raw_text.splitlines()[1:]).strip()

        if prompt:
            self.post_message(self.PromptSubmitted(target_agent=target, prompt_text=prompt))
