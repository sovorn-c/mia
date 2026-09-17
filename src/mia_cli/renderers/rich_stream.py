"""Rich terminal streaming event renderer for Mia agent execution with signature carrot_bounce and audit logs."""

from __future__ import annotations

import json
import os
import sys
import time
import unicodedata
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
    """Bound terminal display text and replace terminal controls with spaces."""
    text = "".join(" " if unicodedata.category(char) == "Cc" else char for char in str(value))
    if len(text) <= _MAX_DISPLAY_CHARS:
        return text
    return text[: _MAX_DISPLAY_CHARS - 1] + "…"


def _safe_value_text(value: Any) -> str:
    """Serialize sanitized Tool data for bounded terminal display."""
    try:
        safe_value = sanitize_arguments(value)
        if isinstance(safe_value, str):
            return _safe_display_text(safe_value)
        return _safe_display_text(json.dumps(safe_value, ensure_ascii=False))
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
        idx = int(max(0.0, elapsed_seconds)) % len(cls.FRAMES)
        return cls.FRAMES[idx]

    @classmethod
    def render_frame(cls, elapsed_seconds: float = 0.0) -> str:
        frame = cls.get_frame(elapsed_seconds)
        return f"{frame} Thinking ({int(max(0.0, elapsed_seconds))}s)..."


class AnimatedWorkingStatus:
    """Live renderable widget providing braille spinner + action label + dynamic . .. ... dot cycling + ticking elapsed seconds."""

    def __init__(
        self,
        action: str = "Thinking",
        turn_start_time: float = 0.0,
        style: str = "bold",
    ) -> None:
        self.action = action
        self.turn_start_time = turn_start_time
        self.style = style
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.dot_frames = [".  ", ".. ", "...", "   "]

    def update(self, action: str, style: str = "bold") -> None:
        self.action = action
        self.style = style

    def __rich__(self) -> Text:
        elapsed = max(0, int(time.time() - self.turn_start_time))
        spin_idx = elapsed % len(self.spinner_frames)
        dot_idx = elapsed % len(self.dot_frames)
        spin = self.spinner_frames[spin_idx]
        dots = self.dot_frames[dot_idx]

        return Text.assemble(
            (f"{spin} ", self.style),
            (f"{self.action}", self.style),
            (f"{dots} ", self.style),
            (f"({elapsed}s)", "dim"),
        )


class RichStreamRenderer:
    """Consumes typed AgentEvents and renders minimalist inline output with live animated working status."""

    def __init__(
        self,
        console: Console | None = None,
        show_thinking_trace: bool = False,
        plain_mode: bool | None = None,
        live_status: bool = True,
    ) -> None:
        self.console = console or Console()
        self.plain_mode = (
            plain_mode if plain_mode is not None else resolve_plain_mode(console=self.console)
        )
        self.show_thinking_trace = show_thinking_trace
        self.live_status = live_status
        self._in_thought = False
        self._in_text = False
        self.turn_count = 0
        self.turn_start_time = 0.0
        self.thinking_buffer: list[str] = []
        self._assistant_buffer: list[str] = []
        self._defer_text = not live_status
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
        self._end_streams()
        self.thinking_buffer.clear()
        self._assistant_buffer.clear()
        self.turn_audit_log.clear()
        self.tool_rows.clear()
        self.console.print()
        self._start_status("Thinking")

    def _start_status(self, action: str, style: str = "bold") -> None:
        """Start or update the animated working status."""
        if self.plain_mode or not self.console.is_terminal:
            return
        if self._status_widget is None:
            self._status_widget = AnimatedWorkingStatus(
                action=action,
                turn_start_time=self.turn_start_time,
                style=style,
            )
            if self.live_status:
                self._active_status = Live(
                    self._status_widget,
                    console=self.console,
                    refresh_per_second=1,
                    transient=True,
                )
                self._active_status.start()
        elif self._status_widget is not None:
            self._status_widget.turn_start_time = self.turn_start_time
            self._status_widget.update(action=action, style=style)

    def prompt_status(self) -> str | None:
        """Return the current status text for a prompt prefix above the editor."""
        if self._defer_text and self.phase == "responding" and self._assistant_buffer:
            preview = " ".join(_safe_display_text("".join(self._assistant_buffer)).split())
            if len(preview) > 240:
                preview = preview[:239] + "…"
            elapsed = max(0, int(time.time() - self.turn_start_time))
            return f"🥕 mia › {preview} ({elapsed}s)"
        if self._status_widget is None or self.phase not in {
            "thinking",
            "responding",
            "tool",
            "approval",
        }:
            return None
        return self._status_widget.__rich__().plain

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

    def toggle_tool_row(self, call_id: str) -> bool | None:
        """Expand or collapse one retained Tool result; None means no such row."""
        row = self.tool_rows.get(call_id)
        if row is None:
            return None
        row.expanded = not row.expanded
        state = "expanded" if row.expanded else "collapsed"
        self.console.print(f"[tool {state}] {row.call_id} {row.tool_name}", markup=False)
        if row.expanded:
            self.console.print(f"  output: {row.result or '[no retained result]'}", markup=False)
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
        state_label = {
            "pending": "running",
            "completed": "ok",
            "error": "error",
            "cancelled": "cancelled",
            "approval": "approval",
        }[row.state]
        self.console.print(
            f"[tool {row.state}] {row.summary} · {row.call_id} · {state_label}{duration}",
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
                self.console.print()
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
                            self.console.print(Text("thinking: ", style="dim italic"), end="")
                        self._in_thought = True
                    if self.plain_mode:
                        self.console.print(event.thought_delta, end="", markup=False)
                    else:
                        self.console.print(Text(event.thought_delta, style="dim italic"), end="")
                else:
                    self._start_status("Thinking")

            if event.delta_text:
                self.phase = "responding"
                if self._in_thought:
                    self.console.print("\n")
                    self._in_thought = False
                first_text = not self._in_text
                self._in_text = True
                if self._defer_text:
                    self._assistant_buffer.append(event.delta_text)
                    self._start_status("Responding")
                else:
                    self._stop_status()
                    if self.plain_mode:
                        prefix = "🥕 mia › " if first_text else ""
                        self.console.print(prefix + event.delta_text, end="", markup=False)
                    else:
                        rendered_text = (
                            Text.assemble(("🥕 mia › ", "bold"), (event.delta_text, ""))
                            if first_text
                            else Text(event.delta_text)
                        )
                        self.console.print(rendered_text, end="")

        elif isinstance(event, ToolCallEvent):
            self.phase = "tool"
            self._stop_status()
            self._end_streams()
            row = ToolRow(
                call_id=_safe_display_text(event.call_id),
                tool_name=_safe_display_text(event.tool_name),
                summary=self._tool_summary(event),
                arguments=_safe_value_text(event.arguments),
            )
            self.tool_rows[event.call_id] = row
            self._print_tool_row(row)
            self._start_status(f"running {row.summary}", style="bold")
            self.turn_audit_log.append(
                {
                    "call_id": event.call_id,
                    "tool_name": row.tool_name,
                    "arguments": _safe_value_text(event.arguments),
                    "status": "pending",
                }
            )

        elif isinstance(event, ToolResultEvent):
            self._stop_status()
            self._end_streams()
            result_row: ToolRow | None = self.tool_rows.get(event.call_id)
            if result_row is None:
                result_row = ToolRow(
                    call_id=_safe_display_text(event.call_id),
                    tool_name=_safe_display_text(event.tool_name),
                    summary=_safe_display_text(event.tool_name),
                )
                self.tool_rows[event.call_id] = result_row
            result_row.state = "error" if event.is_error else "completed"
            result_row.result = _safe_value_text(event.output)
            self._print_tool_row(result_row, event.duration_ms)

            if self.turn_audit_log:
                self.turn_audit_log[-1]["status"] = result_row.state
                self.turn_audit_log[-1]["duration_ms"] = event.duration_ms
                self.turn_audit_log[-1]["output"] = result_row.result

            self.phase = "thinking"
            self._start_status("Thinking")

        elif isinstance(event, StepEndEvent):
            self._end_streams()

        elif isinstance(event, AgentErrorEvent):
            self.phase = "failure"
            self._cancel_pending_tool_rows("error")
            self._stop_status()
            self._end_streams()
            if self.plain_mode:
                self.console.print(
                    f"[error] Agent error: {_safe_display_text(event.error)}", markup=False
                )
            else:
                self.console.print(
                    Text(f"[error] Agent error: {_safe_display_text(event.error)}", style="bold")
                )

        elif isinstance(event, RunErrorEvent):
            self.phase = "cancelled" if event.cancelled else "failure"
            self._cancel_pending_tool_rows("cancelled" if event.cancelled else "error")
            self._stop_status()
            self._end_streams()
            if event.cancelled:
                if self.plain_mode:
                    self.console.print(
                        f"[cancelled] Run cancelled ({_safe_display_text(event.stage)}): "
                        f"{_safe_display_text(event.error)}",
                        markup=False,
                    )
                else:
                    self.console.print(
                        Text(
                            f"[cancelled] Run cancelled ({_safe_display_text(event.stage)}): "
                            f"{_safe_display_text(event.error)}",
                            style="bold",
                        )
                    )
            else:
                if self.plain_mode:
                    self.console.print(
                        f"[error] Run error ({_safe_display_text(event.stage)}): "
                        f"{_safe_display_text(event.error)}",
                        markup=False,
                    )
                else:
                    self.console.print(
                        Text(
                            f"[error] Run error ({_safe_display_text(event.stage)}): "
                            f"{_safe_display_text(event.error)}",
                            style="bold",
                        )
                    )

        elif isinstance(event, TurnCompleteEvent):
            was_cancelled = self.phase == "cancelled"
            successful = (
                event.stop_reason == "stop" and not was_cancelled and self.phase != "failure"
            )
            self.phase = "success" if successful else "cancelled" if was_cancelled else "failure"
            self._stop_status()
            self._end_streams()
            cost_str = f" | ${event.total_cost_usd:.4f}" if event.total_cost_usd > 0 else ""
            elapsed = (
                max(0, int(time.time() - self.turn_start_time)) if self.turn_start_time > 0 else 0
            )
            step_word = "1 step" if event.total_steps == 1 else f"{event.total_steps} steps"
            if successful:
                outcome = f"Turn completed in {elapsed}s, [{step_word}]{cost_str}"
                style = "dim"
                label = "ok"
            elif was_cancelled:
                outcome = f"Turn cancelled in {elapsed}s, [{step_word}]"
                style = "bold"
                label = "cancelled"
            else:
                outcome = (
                    f"Turn failed ({_safe_display_text(event.stop_reason)}) in "
                    f"{elapsed}s, [{step_word}]"
                )
                style = "bold"
                label = "error"
            if self.plain_mode:
                self.console.print(f"\n[{label}] {outcome}\n", markup=False)
            else:
                self.console.print(Text(f"\n{outcome}\n", style=style))

    def render_audit_log(self) -> None:
        """Render detailed post-turn tool execution logs and diffs."""
        if not self.turn_audit_log:
            self.console.print("[dim]No tool executions in the latest turn.[/dim]\n")
            return

        self.console.print("\n[bold]Turn execution audit log & file diffs[/bold]")
        self.console.print("[dim]─" * 68 + "[/dim]")

        for i, item in enumerate(self.turn_audit_log, start=1):
            tool = item["tool_name"]
            status = item.get("status", "unknown")
            dur = item.get("duration_ms", 0.0)
            status_style = "bold"

            audit_line = Text.assemble(
                (f"Step #{i}: ", "bold"),
                (status.upper(), status_style),
                (f" {tool} ", "bold"),
                (f"({dur:.1f}ms)", "dim"),
            )
            self.console.print(audit_line)
            self.console.print(
                Text(
                    f"  Arguments: {json.dumps(item.get('arguments', {}), ensure_ascii=False)}",
                    style="dim",
                )
            )

            output = str(item.get("output", ""))
            if "--- a/" in output or "+++ b/" in output:
                diff_syntax = Syntax(output, "diff", theme="monokai", line_numbers=True)
                self.console.print(
                    Panel(
                        diff_syntax,
                        title="[bold]File modification diff[/bold]",
                        border_style="dim",
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
                        border_style="dim",
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
            if self._defer_text:
                text = "".join(self._assistant_buffer)
                self._assistant_buffer.clear()
                if self.plain_mode:
                    self.console.print(f"🥕 mia › {text}", markup=False)
                else:
                    self.console.print(Text.assemble(("🥕 mia › ", "bold"), (text, "")))
            else:
                self.console.print()
            self._in_text = False
