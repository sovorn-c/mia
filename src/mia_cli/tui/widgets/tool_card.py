"""Modern ToolCall card widget with diff syntax rendering."""

from __future__ import annotations

import json
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ToolCallCard(Vertical):
    """Card displaying a tool invocation, its execution status, and results."""

    def __init__(
        self,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.call_id = call_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.is_done = False
        self.is_error = False
        self.duration_ms = 0.0
        self.output_text = ""

        self.header_widget = Static("", classes="tool-header")
        self.body_widget = Static("", classes="tool-body")

    def compose(self) -> ComposeResult:
        self._render_header()
        yield self.header_widget
        yield self.body_widget

    def set_result(self, output: Any, is_error: bool = False, duration_ms: float = 0.0) -> None:
        """Update card with completed tool execution result."""
        self.is_done = True
        self.is_error = is_error
        self.duration_ms = duration_ms
        self.output_text = str(output)
        self._render_header()
        self._render_body()

    def _render_header(self) -> None:
        args_str = json.dumps(self.arguments, ensure_ascii=False)
        if len(args_str) > 80:
            args_str = args_str[:77] + "..."

        if not self.is_done:
            status = Text("⚡ Running...", style="bold #FF7A00")
        elif self.is_error:
            status = Text(f"✗ Failed ({self.duration_ms:.1f}ms)", style="bold #EF4444")
        else:
            status = Text(f"✓ Succeeded ({self.duration_ms:.1f}ms)", style="bold #10B981")

        header = Text.assemble(
            ("▶ Tool: ", "bold #38BDF8"),
            (f"{self.tool_name}", "bold #F3F4F6"),
            (f"({args_str}) ", "#9CA3AF"),
            status,
        )
        self.header_widget.update(header)

    def _render_body(self) -> None:
        if not self.output_text:
            return

        # If unified diff, render with diff syntax
        if "--- a/" in self.output_text and "+++ b/" in self.output_text:
            syntax_diff = Syntax(self.output_text, "diff", theme="monokai", line_numbers=False)
            self.body_widget.update(syntax_diff)
        else:
            lines = self.output_text.splitlines()
            if len(lines) > 25:
                preview = "\n".join(lines[:20] + [f"... [{len(lines) - 20} more lines]"])
            else:
                preview = self.output_text
            self.body_widget.update(Text(preview, style="#9CA3AF"))
