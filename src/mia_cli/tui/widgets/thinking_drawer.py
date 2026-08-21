"""Collapsible thinking drawer widget for reasoning tokens."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ThoughtDrawer(Vertical):
    """Collapsible drawer displaying live reasoning / thinking tokens."""

    def __init__(
        self, initial_thought: str = "", is_collapsed: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._thought_text = initial_thought
        self.is_collapsed = is_collapsed
        self.header_widget = Static("", classes="thought-header")
        self.body_widget = Static("", classes="thought-body")

    def compose(self) -> ComposeResult:
        self._update_header()
        self._update_body()
        yield self.header_widget
        yield self.body_widget

    def append_thought(self, delta: str) -> None:
        """Stream append thinking tokens."""
        self._thought_text += delta
        self._update_body()

    def toggle_collapse(self) -> None:
        """Toggle collapsed state."""
        self.is_collapsed = not self.is_collapsed
        self.body_widget.display = not self.is_collapsed
        self._update_header()

    def on_click(self) -> None:
        self.toggle_collapse()

    def _update_header(self) -> None:
        icon = "▶" if self.is_collapsed else "▼"
        self.header_widget.update(
            Text(
                f"{icon} 💭 Thinking ({len(self._thought_text.split())} words)",
                style="bold #FF7A00",
            )
        )

    def _update_body(self) -> None:
        if not self.is_collapsed:
            self.body_widget.update(Text(self._thought_text, style="italic #9CA3AF"))
