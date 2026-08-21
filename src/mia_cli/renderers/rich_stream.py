"""Rich terminal streaming event renderer for Mia agent execution."""

from __future__ import annotations

import json

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


class RichStreamRenderer:
    """Consumes typed AgentEvents and renders live syntax-highlighted streaming output."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._in_thought = False
        self._in_text = False
        self.turn_count = 0

    def on_event(self, event: AgentEvent) -> None:
        """Handle a single AgentEvent and print corresponding Rich output."""
        if isinstance(event, TurnStartEvent):
            self.turn_count += 1
            self._end_streams()
            self.console.print(f"\n[bold blue]─── Turn #{event.turn_index} ───[/bold blue]")

        elif isinstance(event, StepStartEvent):
            self._end_streams()

        elif isinstance(event, AssistantChunkEvent):
            if event.thought_delta:
                if not self._in_thought:
                    if self._in_text:
                        self.console.print()
                        self._in_text = False
                    self.console.print(Text("💭 Thinking: ", style="dim italic"), end="")
                    self._in_thought = True
                self.console.print(Text(event.thought_delta, style="dim italic"), end="")

            if event.delta_text:
                if self._in_thought:
                    self.console.print("\n")
                    self._in_thought = False
                self._in_text = True
                self.console.print(Text(event.delta_text), end="")

        elif isinstance(event, ToolCallEvent):
            self._end_streams()
            args_str = json.dumps(event.arguments, ensure_ascii=False)
            if len(args_str) > 120:
                args_str = args_str[:117] + "..."
            self.console.print(
                f"\n[bold cyan]▶ Tool Call:[/bold cyan] [bold]{event.tool_name}[/bold]({args_str})"
            )

        elif isinstance(event, ToolResultEvent):
            self._end_streams()
            status_symbol = (
                "[bold red]✗ Failed[/bold red]"
                if event.is_error
                else "[bold green]✓ Succeeded[/bold green]"
            )
            dur_str = f"[dim]({event.duration_ms:.1f}ms)[/dim]"
            header = f"{status_symbol} {event.tool_name} {dur_str}"

            output_str = str(event.output)
            # If unified diff, render with diff syntax
            if "--- a/" in output_str and "+++ b/" in output_str:
                rendered_body = Syntax(output_str, "diff", theme="monokai", line_numbers=False)
                self.console.print(
                    Panel(rendered_body, title=header, expand=False, border_style="cyan")
                )
            else:
                lines = output_str.splitlines()
                if len(lines) > 20:
                    truncated_text = "\n".join(lines[:15] + [f"... [{len(lines) - 15} more lines]"])
                else:
                    truncated_text = output_str
                self.console.print(
                    Panel(Text(truncated_text), title=header, expand=False, border_style="dim")
                )

        elif isinstance(event, StepEndEvent):
            self._end_streams()

        elif isinstance(event, TurnCompleteEvent):
            self._end_streams()
            cost_str = f" | Cost: ${event.total_cost_usd:.4f}" if event.total_cost_usd > 0 else ""
            self.console.print(
                f"\n[dim green]✓ Turn Complete ({event.total_steps} step(s){cost_str})[/dim green]\n"
            )

    def _end_streams(self) -> None:
        """Close open streaming blocks cleanly."""
        if self._in_thought:
            self.console.print("\n")
            self._in_thought = False
        if self._in_text:
            self.console.print()
            self._in_text = False
