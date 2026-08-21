"""Production-grade multi-line prompt editor with priority keybindings and history."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, TextArea


class PromptTextArea(TextArea):
    """Subclassed TextArea with priority bindings for instant Enter-submission and history."""

    BINDINGS = [
        Binding("enter", "submit_prompt", "Submit", priority=True),
        Binding("shift+enter", "insert_newline", "Newline", priority=True),
        Binding("up", "history_prev", "Previous", priority=True),
        Binding("down", "history_next", "Next", priority=True),
    ]

    class Submitted(Message):
        """Emitted when Enter is pressed to submit text."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class HistoryNavigation(Message):
        """Emitted when navigating history with Up/Down."""

        def __init__(self, direction: str) -> None:
            super().__init__()
            self.direction = direction

    def action_submit_prompt(self) -> None:
        """Handle Enter key: submit prompt if text is non-empty."""
        content = self.text.strip()
        if content:
            self.post_message(self.Submitted(content))
            self.text = ""

    def action_insert_newline(self) -> None:
        """Handle Shift+Enter key: insert literal newline."""
        self.insert("\n")

    def action_history_prev(self) -> None:
        """Navigate to previous command history if cursor is on line 0."""
        cursor_line = self.cursor_location[0]
        if cursor_line == 0:
            self.post_message(self.HistoryNavigation("up"))
        else:
            self.action_cursor_up()

    def action_history_next(self) -> None:
        """Navigate to next command history if cursor is on last line."""
        cursor_line = self.cursor_location[0]
        if cursor_line >= self.document.line_count - 1:
            self.post_message(self.HistoryNavigation("down"))
        else:
            self.action_cursor_down()


class MiaPromptEditor(Vertical):
    """Modern auto-expanding multi-line prompt editor with command history and slash routing."""

    DEFAULT_CSS = """
    MiaPromptEditor {
        dock: bottom;
        height: auto;
        min-height: 4;
        max-height: 10;
        background: #14171F;
        border-top: solid #2B303B;
        padding: 0 1;
    }

    MiaPromptEditor:focus-within {
        border-top: solid #FF7A00;
    }

    #editor-row {
        height: auto;
        min-height: 3;
    }

    .editor-prefix {
        width: 5;
        height: 100%;
        color: #FF7A00;
        text-style: bold;
        padding-top: 0;
    }

    PromptTextArea {
        height: auto;
        min-height: 2;
        max-height: 8;
        background: #14171F;
        border: none;
        color: #F3F4F6;
        padding: 0;
    }

    PromptTextArea:focus {
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
        self.textarea = PromptTextArea(
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

    def on_mount(self) -> None:
        """Focus the input editor automatically when mounted."""
        self.textarea.focus()

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

    def on_prompt_text_area_submitted(self, message: PromptTextArea.Submitted) -> None:
        """Handle submission from the inner PromptTextArea."""
        raw_text = message.text.strip()
        if not raw_text:
            return

        # Save to history buffer
        self._history.append(raw_text)
        self._history_idx = -1

        # Check for slash command (/model, /profile, /compact, /clear, /help, /quit)
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

    def on_prompt_text_area_history_navigation(
        self, message: PromptTextArea.HistoryNavigation
    ) -> None:
        """Handle Up/Down arrow history cycling."""
        if not self._history:
            return

        if message.direction == "up":
            if self._history_idx == -1:
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
            self.textarea.text = self._history[self._history_idx]
            self.textarea.move_cursor((self.textarea.document.line_count - 1, 0))
        elif message.direction == "down":
            if self._history_idx != -1:
                if self._history_idx < len(self._history) - 1:
                    self._history_idx += 1
                    self.textarea.text = self._history[self._history_idx]
                else:
                    self._history_idx = -1
                    self.textarea.text = ""
