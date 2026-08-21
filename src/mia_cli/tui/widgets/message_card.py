"""User and Assistant message card widgets for Textual TUI."""

from __future__ import annotations

import time
from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class UserMessageCard(Vertical):
    """Card displaying a user instruction sent to an agent."""

    def __init__(self, prompt: str, target_agent: str = "coder", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt
        self.target_agent = target_agent
        self.timestamp_str = time.strftime("%H:%M:%S")

    def compose(self) -> ComposeResult:
        header = Text.assemble(
            ("🥕 User ➔ ", "bold #FF7A00"),
            (f"@{self.target_agent} ", "bold #38BDF8"),
            (f"• {self.timestamp_str}", "dim #9CA3AF"),
        )
        yield Static(header, classes="user-msg-header")
        yield Static(Text(self.prompt, style="#F3F4F6"), classes="user-msg-body")


class AssistantMessageCard(Vertical):
    """Card displaying an assistant response stream."""

    def __init__(self, initial_text: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._content = initial_text
        self.content_widget = Static("", classes="assistant-msg-body")

    def compose(self) -> ComposeResult:
        self._render_content()
        yield self.content_widget

    def append_text(self, delta: str) -> None:
        """Stream append assistant text."""
        self._content += delta
        self._render_content()

    def _render_content(self) -> None:
        if not self._content:
            return
        try:
            self.content_widget.update(Markdown(self._content))
        except Exception:
            self.content_widget.update(Text(self._content, style="#F3F4F6"))
