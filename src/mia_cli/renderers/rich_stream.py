"""Rich terminal streaming event renderer for Mia agent execution with signature carrot_bounce and audit logs."""

from __future__ import annotations

import json
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from mia_agent.events import (
    AgentEvent,
    AssistantChunkEvent,
    StepEndEvent,
    StepStartEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnCompleteEvent,
    TurnStartEvent,
)


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


class RichStreamRenderer:
    """Consumes typed AgentEvents and renders minimalist inline output with audit logging."""

    def __init__(
        self,
        console: Console | None = None,
        show_thinking_trace: bool = False,
    ) -> None:
        self.console = console or Console()
        self.show_thinking_trace = show_thinking_trace
        self._in_thought = False
        self._in_text = False
        self.turn_count = 0
        self.turn_start_time = 0.0
        self.thinking_buffer: list[str] = []
        self.turn_audit_log: list[dict[str, Any]] = []

    def on_event(self, event: AgentEvent) -> None:
        """Handle a single AgentEvent and print minimalist output."""
        if isinstance(event, TurnStartEvent):
            self.turn_count += 1
            self.turn_start_time = time.time()
            self.thinking_buffer.clear()
            self.turn_audit_log.clear()
            self._end_streams()

        elif isinstance(event, StepStartEvent):
            self._end_streams()

        elif isinstance(event, AssistantChunkEvent):
            if event.thought_delta:
                self.thinking_buffer.append(event.thought_delta)
                if self.show_thinking_trace:
                    if not self._in_thought:
                        if self._in_text:
                            self.console.print()
                            self._in_text = False
                        self.console.print(
                            Text("💭 Thinking: ", style="dim italic #FF7A00"), end=""
                        )
                        self._in_thought = True
                    self.console.print(
                        Text(event.thought_delta, style="dim italic #9CA3AF"), end=""
                    )

            if event.delta_text:
                if self._in_thought:
                    self.console.print("\n")
                    self._in_thought = False
                self._in_text = True
                self.console.print(Text(event.delta_text), end="")

        elif isinstance(event, ToolCallEvent):
            self._end_streams()
            args = event.arguments
            if event.tool_name == "read_file":
                tool_summary = f"read_file {args.get('path', '')}"
            elif event.tool_name == "write_file":
                tool_summary = f"write_file {args.get('path', '')}"
            elif event.tool_name == "edit_file":
                tool_summary = f"edit_file {args.get('path', '')}"
            elif event.tool_name == "bash":
                cmd = str(args.get("command", ""))
                tool_summary = f"bash: {cmd[:45]}..." if len(cmd) > 48 else f"bash: {cmd}"
            else:
                tool_summary = event.tool_name

            self.console.print(
                f"\n[bold #38BDF8]⠋[/bold #38BDF8] [dim]{tool_summary}[/dim]", end=""
            )
            self.turn_audit_log.append(
                {
                    "tool_name": event.tool_name,
                    "arguments": event.arguments,
                    "status": "running",
                }
            )

        elif isinstance(event, ToolResultEvent):
            self._end_streams()
            dur_str = f"({event.duration_ms:.1f}ms)"
            output_str = str(event.output)

            # Extract compact result summary
            if event.tool_name == "read_file":
                lines_count = len(output_str.splitlines())
                result_desc = f"✓ Read {lines_count} lines"
            elif event.tool_name in ("write_file", "edit_file"):
                result_desc = "✓ Applied file changes"
            elif event.tool_name == "bash":
                result_desc = "✓ Command finished"
            else:
                result_desc = "✓ Succeeded"

            if event.is_error:
                self.console.print(
                    f"\r[bold red]✗ {event.tool_name}[/bold red] [dim]{dur_str}[/dim]"
                )
                self.console.print(f"  [dim red]↳ {output_str[:250]}[/dim red]")
            else:
                self.console.print(
                    f"\r[bold green]✓[/bold green] [bold white]{event.tool_name}[/bold white] [dim green]{result_desc}[/dim green] [dim]{dur_str}[/dim]"
                )

            # Update audit log entry
            if self.turn_audit_log:
                self.turn_audit_log[-1]["status"] = "failed" if event.is_error else "succeeded"
                self.turn_audit_log[-1]["duration_ms"] = event.duration_ms
                self.turn_audit_log[-1]["output"] = output_str

        elif isinstance(event, StepEndEvent):
            self._end_streams()

        elif isinstance(event, TurnCompleteEvent):
            self._end_streams()
            cost_str = f" | ${event.total_cost_usd:.4f}" if event.total_cost_usd > 0 else ""
            elapsed = time.time() - self.turn_start_time if self.turn_start_time > 0 else 0.0
            self.console.print(
                f"\n[dim green]✓ Turn completed in {elapsed:.1f}s ({event.total_steps} step(s){cost_str})[/dim green]"
            )
            self.console.print(
                "[dim #6B7280]💡 Press [bold white]Ctrl+O[/bold white] for full audit logs • [bold white]Ctrl+T[/bold white] for thinking trace[/dim #6B7280]\n"
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
