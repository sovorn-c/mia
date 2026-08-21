"""Collapsible thinking drawer widget with streaming reasoning and token count."""

from __future__ import annotations

import time
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
        self.is_streaming = True
        self.start_time = time.time()
        self.duration_s = 0.0

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
        self.duration_s = time.time() - self.start_time
        self._update_header()
        self._update_body()

    def complete(self) -> None:
        """Mark thinking as finalized."""
        self.is_streaming = False
        self.duration_s = time.time() - self.start_time
        self._update_header()

    def toggle_collapse(self) -> None:
        """Toggle collapsed state."""
        self.is_collapsed = not self.is_collapsed
        self.body_widget.display = not self.is_collapsed
        self._update_header()

    def on_click(self) -> None:
        self.toggle_collapse()

    def _update_header(self) -> None:
        icon = "▶" if self.is_collapsed else "▼"
        word_count = len(self._thought_text.split())
        status_label = (
            f"({word_count} words • {self.duration_s:.1f}s)"
            if self.duration_s > 0
            else f"({word_count} words)"
        )

        header_text = Text.assemble(
            (f"{icon} 💭 Thinking ", "bold #FF7A00"),
            (status_label, "dim #9CA3AF"),
        )
        self.header_widget.update(header_text)

    def _update_body(self) -> None:
        if not self.is_collapsed:
            self.body_widget.update(Text(self._thought_text, style="italic #9CA3AF"))
