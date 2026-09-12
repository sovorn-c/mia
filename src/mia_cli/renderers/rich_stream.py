"""Rich terminal streaming event renderer for Mia agent execution with signature carrot_bounce and audit logs."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Literal

import rich.spinner
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from mia_agent.events import (
    AgentErrorEvent,
    AgentEvent,
    AssistantChunkEvent,
    StepEndEvent,
    StepStartEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnCompleteEvent,
    TurnStartEvent,
)
from mia_agent.runtime_events import RunErrorEvent
from mia_middleware.access import sanitize_arguments

RunPhase = Literal[
    "idle", "thinking", "responding", "tool", "approval", "success", "failure", "cancelled"
]
_MAX_DISPLAY_CHARS = 4000
ToolRowState = Literal["pending", "approval", "completed", "error", "cancelled"]


@dataclass
class ToolRow:
    """Ephemeral, sanitized display state for one attributable Tool call."""

    call_id: str
    tool_name: str
    summary: str
    state: ToolRowState = "pending"
    arguments: str = ""
    result: str = ""
    expanded: bool = False


def _safe_display_text(value: Any) -> str:
    """Bound terminal display text and remove control characters without changing content semantics."""
    text = str(value).replace("\x1b", "").replace("\r", "")
    if len(text) <= _MAX_DISPLAY_CHARS:
        return text
    return text[: _MAX_DISPLAY_CHARS - 1] + "…"


def _safe_value_text(value: Any) -> str:
    """Serialize sanitized Tool data for bounded terminal display."""
    try:
        safe_value = sanitize_arguments(value)
        if isinstance(safe_value, str):
            return _safe_display_text(safe_value)
        return _safe_display_text(json.dumps(safe_value, ensure_ascii=False, default=str))
    except Exception:
        return "[REDACTED]"


def resolve_plain_mode(
    plain_option: bool = False,
    console: Console | None = None,
    environ: dict[str, str] | None = None,
) -> bool:
    """Determine whether plain, non-animated, accessible output should be used.

    Returns True if:
    1. plain_option is True (explicit --plain flag)
    2. NO_COLOR environment variable is set and non-empty
    3. The target console/stream is not an interactive terminal
    """
    if plain_option:
        return True
    env = os.environ if environ is None else environ
    if env.get("NO_COLOR"):
        return True
    if console is not None:
        if not console.is_terminal or console.no_color:
            return True
    elif not sys.stdout.isatty():
        return True
    return False


spinners_dict = getattr(rich.spinner, "SPINNERS", {})
if "dot_cycle" not in spinners_dict:
    spinners_dict["dot_cycle"] = {
        "interval": 200,
        "frames": [".  ", ".. ", "...", "   "],
    }


class CarrotBounceSpinner:
    """Animated spinner frames with signature carrot bounce."""

    FRAMES = ["🥕   ", " 🥕  ", "  🥕 ", "   🥕", "  🥕 ", " 🥕  "]

    @classmethod
    def get_frame(cls, elapsed_seconds: float) -> str:
        idx = int(elapsed_seconds * 4) % len(cls.FRAMES)
        return cls.FRAMES[idx]

    @classmethod
    def render_frame(cls, elapsed_seconds: float = 0.0) -> str:
        frame = cls.get_frame(elapsed_seconds)
        return f"{frame} Thinking ({elapsed_seconds:.1f}s)..."


class AnimatedWorkingStatus:
    """Live renderable widget providing braille spinner + action label + dynamic . .. ... dot cycling + ticking elapsed seconds."""

    def __init__(
        self,
        action: str = "Thinking",
        turn_start_time: float = 0.0,
        style: str = "bold #FF7A00",
    ) -> None:
        self.action = action
        self.turn_start_time = turn_start_time
        self.style = style
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.dot_frames = [".  ", ".. ", "...", "   "]

    def update(self, action: str, style: str = "bold #FF7A00") -> None:
        self.action = action
        self.style = style

    def __rich__(self) -> Text:
        now = time.time()
        elapsed = max(0.0, now - self.turn_start_time)
        spin_idx = int(elapsed * 10) % len(self.spinner_frames)
        dot_idx = int(elapsed * 3) % len(self.dot_frames)
        spin = self.spinner_frames[spin_idx]
        dots = self.dot_frames[dot_idx]

        return Text.assemble(
            (f"{spin} ", self.style),
            (f"{self.action}", self.style),
            (f"{dots} ", self.style),
            (f"({elapsed:.1f}s)", "dim #9CA3AF"),
        )


class RichStreamRenderer:
    """Consumes typed AgentEvents and renders minimalist inline output with live animated working status."""

    def __init__(
        self,
        console: Console | None = None,
        show_thinking_trace: bool = False,
        plain_mode: bool | None = None,
    ) -> None:
        self.console = console or Console()
        self.plain_mode = (
            plain_mode if plain_mode is not None else resolve_plain_mode(console=self.console)
        )
        self.show_thinking_trace = show_thinking_trace
        self._in_thought = False
        self._in_text = False
        self.turn_count = 0
        self.turn_start_time = 0.0
        self.thinking_buffer: list[str] = []
        self.turn_audit_log: list[dict[str, Any]] = []
        self._active_status: Live | None = None
        self._status_widget: AnimatedWorkingStatus | None = None
        self.phase: RunPhase = "idle"
        self._user_prompt_rendered = False
        self.tool_rows: dict[str, ToolRow] = {}

    def start_turn(self) -> None:
        """Called immediately upon user submission (Enter) to start elapsed timing and animation."""
        self.turn_count += 1
        self.turn_start_time = time.time()
        self.phase = "thinking"
        self._user_prompt_rendered = False
        self.thinking_buffer.clear()
        self.turn_audit_log.clear()
        self.tool_rows.clear()
        self._end_streams()
        self.console.print()
        self._start_status("Thinking")

    def _start_status(self, action: str, style: str = "bold #FF7A00") -> None:
        """Start or update live animated working status with dynamic cycling dots and live timer."""
        if self.plain_mode or not self.console.is_terminal:
            return
        if self._active_status is None:
            self._status_widget = AnimatedWorkingStatus(
                action=action,
                turn_start_time=self.turn_start_time,
                style=style,
            )
            self._active_status = Live(
                self._status_widget,
                console=self.console,
                refresh_per_second=10,
                transient=True,
            )
            self._active_status.start()
        else:
            if self._status_widget is not None:
                self._status_widget.turn_start_time = self.turn_start_time
                self._status_widget.update(action=action, style=style)

    def _stop_status(self) -> None:
        """Stop and clear active status spinner cleanly."""
        if self._active_status is not None:
            self._active_status.stop()
            self._active_status = None
            self._status_widget = None

    def set_tool_approval(self, tool_name: str) -> None:
        """Mark the latest matching pending Tool row as awaiting explicit approval."""
        for row in reversed(list(self.tool_rows.values())):
            if row.tool_name == tool_name and row.state == "pending":
                row.state = "approval"
                self.phase = "approval"
                self._print_tool_row(row)
                return
        self.phase = "approval"

    def toggle_tool_row(self, call_id: str) -> bool:
        """Expand or collapse one retained Tool result and return its new state."""
        row = self.tool_rows.get(call_id)
        if row is None:
            return False
        row.expanded = not row.expanded
        state = "expanded" if row.expanded else "collapsed"
        self.console.print(f"[tool {state}] {row.call_id} {row.tool_name}", markup=False)
        if row.expanded:
            self.console.print(f"  ↳ {row.result or '[no retained result]'}", markup=False)
        return row.expanded

    def _tool_summary(self, event: ToolCallEvent) -> str:
        safe_arguments = sanitize_arguments(event.arguments)
        if event.tool_name in {"read_file", "write_file", "edit_file"}:
            summary = f"{event.tool_name} {safe_arguments.get('path', '')}"
        elif event.tool_name == "bash":
            command = str(safe_arguments.get("command", ""))
            summary = f"bash: {command}"
        else:
            summary = event.tool_name
        return _safe_display_text(summary)

    def _print_tool_row(self, row: ToolRow, duration_ms: float | None = None) -> None:
        duration = f" ({duration_ms:.1f}ms)" if duration_ms is not None else ""
        legacy_role = {
            "pending": " [running]",
            "completed": " [ok]",
            "error": " [error]",
            "cancelled": " [cancelled]",
            "approval": " [approval-required]",
        }[row.state]
        self.console.print(
            f"[tool {row.state}] {row.tool_name} {row.summary}{duration}{legacy_role} {row.tool_name}",
            markup=False,
        )

    def _cancel_pending_tool_rows(self, state: ToolRowState) -> None:
        for row in self.tool_rows.values():
            if row.state in {"pending", "approval"}:
                row.state = state
                self._print_tool_row(row)

    def on_event(self, event: AgentEvent | RunErrorEvent) -> None:
        """Handle a single AgentEvent and print minimalist output."""
        if isinstance(event, TurnStartEvent):
            self.phase = "thinking"
            if not self._user_prompt_rendered:
                self.console.print(f"[user] {_safe_display_text(event.user_prompt)}", markup=False)
                self._user_prompt_rendered = True
            if self.turn_start_time <= 0:
                self.turn_count += 1
                self.turn_start_time = time.time()
            self.thinking_buffer.clear()
            self.turn_audit_log.clear()
            self._end_streams()
            self._start_status("Thinking")

        elif isinstance(event, StepStartEvent):
            self._end_streams()

        elif isinstance(event, AssistantChunkEvent):
            if event.thought_delta:
                self.phase = "thinking"
                self.thinking_buffer.append(event.thought_delta)
                if self.show_thinking_trace:
                    self._stop_status()
                    if not self._in_thought:
                        if self._in_text:
                            self.console.print()
                            self._in_text = False
                        if self.plain_mode:
                            self.console.print("Thinking: ", end="", markup=False)
                        else:
                            self.console.print(
                                Text("💭 Thinking: ", style="dim italic #FF7A00"), end=""
                            )
                        self._in_thought = True
                    if self.plain_mode:
                        self.console.print(event.thought_delta, end="", markup=False)
                    else:
                        self.console.print(
                            Text(event.thought_delta, style="dim italic #9CA3AF"), end=""
                        )
                else:
                    self._start_status("Thinking")

            if event.delta_text:
                self.phase = "responding"
                self._stop_status()
                if self._in_thought:
                    self.console.print("\n")
                    self._in_thought = False
                if not self._in_text:
                    if self.plain_mode:
                        self.console.print("mia > ", end="", markup=False)
                    else:
                        self.console.print("[bold #FF7A00]🥕 mia ›[/bold #FF7A00] ", end="")
                self._in_text = True
                if self.plain_mode:
                    self.console.print(event.delta_text, end="", markup=False)
                else:
                    self.console.print(Text(event.delta_text), end="")

        elif isinstance(event, ToolCallEvent):
            self.phase = "tool"
            self._stop_status()
            self._end_streams()
            row = ToolRow(
                call_id=event.call_id,
                tool_name=_safe_display_text(event.tool_name),
                summary=self._tool_summary(event),
                arguments=_safe_value_text(event.arguments),
            )
            self.tool_rows[event.call_id] = row
            self._print_tool_row(row)
            self._start_status(
                f"Running {row.summary}",
                style="bold #38BDF8",
            )
            self.turn_audit_log.append(
                {
                    "call_id": event.call_id,
                    "tool_name": row.tool_name,
                    "arguments": sanitize_arguments(event.arguments),
                    "status": "pending",
                }
            )

        elif isinstance(event, ToolResultEvent):
            self._stop_status()
            self._end_streams()
            row = self.tool_rows.get(event.call_id)
            if row is None:
                row = ToolRow(
                    call_id=event.call_id,
                    tool_name=_safe_display_text(event.tool_name),
                    summary=_safe_display_text(event.tool_name),
                )
                self.tool_rows[event.call_id] = row
            row.state = "error" if event.is_error else "completed"
            row.result = _safe_value_text(event.output)
            self._print_tool_row(row, event.duration_ms)

            if self.turn_audit_log:
                self.turn_audit_log[-1]["status"] = row.state
                self.turn_audit_log[-1]["duration_ms"] = event.duration_ms
                self.turn_audit_log[-1]["output"] = row.result

            self.phase = "thinking"
            self._start_status("Thinking")

        elif isinstance(event, StepEndEvent):
            self._end_streams()

        elif isinstance(event, AgentErrorEvent):
            self.phase = "failure"
            self._stop_status()
            self._end_streams()
            if self.plain_mode:
                self.console.print(f"[error] Agent error: {event.error}", markup=False)
            else:
                self.console.print(f"[bold red]✗ Agent error: {event.error}[/bold red]")

        elif isinstance(event, RunErrorEvent):
            self.phase = "cancelled" if event.cancelled else "failure"
            self._cancel_pending_tool_rows("cancelled" if event.cancelled else "error")
            self._stop_status()
            self._end_streams()
            if event.cancelled:
                if self.plain_mode:
                    self.console.print(
                        f"[cancelled] Run cancelled ({event.stage}): {event.error}", markup=False
                    )
                else:
                    self.console.print(
                        f"[yellow]⚠️  Run cancelled ({event.stage}): {event.error}[/yellow]"
                    )
            else:
                if self.plain_mode:
                    self.console.print(
                        f"[error] Run error ({event.stage}): {event.error}", markup=False
                    )
                else:
                    self.console.print(
                        f"[bold red]✗ Run error ({event.stage}): {event.error}[/bold red]"
                    )

        elif isinstance(event, TurnCompleteEvent):
            self.phase = "success" if event.stop_reason == "stop" else "failure"
            self._stop_status()
            self._end_streams()
            cost_str = f" | ${event.total_cost_usd:.4f}" if event.total_cost_usd > 0 else ""
            elapsed = time.time() - self.turn_start_time if self.turn_start_time > 0 else 0.0
            step_word = "1 step" if event.total_steps == 1 else f"{event.total_steps} steps"
            if self.plain_mode:
                self.console.print(
                    f"\n[ok] Turn completed in {elapsed:.1f}s, [{step_word}]{cost_str}\n",
                    markup=False,
                )
            else:
                self.console.print(
                    f"\n[dim green]✓ Turn completed in {elapsed:.1f}s, [{step_word}]{cost_str}[/dim green]\n"
                )

    def render_audit_log(self) -> None:
        """Render detailed post-turn tool execution logs and diffs."""
        if not self.turn_audit_log:
            self.console.print("[dim]No tool executions in the latest turn.[/dim]\n")
            return

        self.console.print(
            "\n[bold #FF7A00]🔍 Turn Execution Audit Log & File Diffs[/bold #FF7A00]"
        )
        self.console.print("[dim]─" * 68 + "[/dim]")

        for i, item in enumerate(self.turn_audit_log, start=1):
            tool = item["tool_name"]
            status = item.get("status", "unknown")
            dur = item.get("duration_ms", 0.0)
            status_style = "bold green" if status == "succeeded" else "bold red"

            self.console.print(
                f"[bold cyan]Step #{i}:[/bold cyan] [{status_style}]{status.upper()}[/{status_style}] [bold white]{tool}[/bold white] [dim]({dur:.1f}ms)[/dim]"
            )
            self.console.print(
                f"  [dim]Arguments:[/dim] {json.dumps(item.get('arguments', {}), ensure_ascii=False)}"
            )

            output = str(item.get("output", ""))
            if "--- a/" in output or "+++ b/" in output:
                diff_syntax = Syntax(output, "diff", theme="monokai", line_numbers=True)
                self.console.print(
                    Panel(
                        diff_syntax,
                        title="[bold #FF7A00]File Modification Diff[/bold #FF7A00]",
                        border_style="#2D3342",
                    )
                )
            elif output.strip():
                lines = output.splitlines()
                if len(lines) > 25:
                    disp = "\n".join(lines[:20] + [f"... [{len(lines) - 20} more lines]"])
                else:
                    disp = output
                self.console.print(
                    Panel(
                        Text(disp),
                        title="[dim]Raw Tool Output[/dim]",
                        border_style="#2D3342",
                        padding=(0, 1),
                    )
                )
            self.console.print()

    def _end_streams(self) -> None:
        """Close open streaming blocks cleanly."""
        if self._in_thought:
            self.console.print("\n")
            self._in_thought = False
        if self._in_text:
            self.console.print()
            self._in_text = False
