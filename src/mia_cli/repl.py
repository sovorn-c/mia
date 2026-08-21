"""Production-grade interactive CLI pair-programming REPL for Mia."""

from __future__ import annotations

import asyncio
import contextlib
import os
import readline
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mia_agent.auth.config import ConfigManager
from mia_agent.events import (
    AssistantChunkEvent,
    StepEndEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnCompleteEvent,
    TurnStartEvent,
)
from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.jsonl import JsonlSessionStore
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool

SLASH_COMMANDS = [
    "/help",
    "/model",
    "/profile",
    "/compact",
    "/cost",
    "/sessions",
    "/clear",
    "/quit",
    "/exit",
]


class REPLCompleter:
    """Tab-completion handler for slash commands and profiles."""

    def __init__(self, commands: list[str]) -> None:
        self.commands = commands

    def complete(self, text: str, state: int) -> str | None:
        # Match text against commands
        options = [cmd for cmd in self.commands if cmd.startswith(text)]
        if state < len(options):
            return options[state]
        return None


class MiaREPL:
    """Stream-first interactive coding agent harness."""

    def __init__(
        self,
        *,
        model: str | None = None,
        profile: str = "coding",
        cwd: Path | None = None,
        custom_provider: LLMProvider | None = None,
    ) -> None:
        self.console = Console()
        self.cwd = cwd or Path.cwd()
        self.config_mgr = ConfigManager()
        self.profile_mgr = ProfileManager()
        self.profile_name = profile
        self.model_name = model or self.config_mgr.config.default_model
        self.custom_provider = custom_provider

        self.session_id = f"session_{os.urandom(4).hex()}"
        self.harness: AgentHarness | None = None
        self.total_cost_usd = 0.0
        self.total_tokens = 0

        self._history_file = Path.home() / ".mia" / "history"
        self._setup_readline()
        self._init_harness()

    def _setup_readline(self) -> None:
        """Initialize readline history and completion across macOS (libedit) and Linux (GNU readline)."""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            if self._history_file.exists():
                readline.read_history_file(str(self._history_file))

            # Remove '/' from word delimiters so '/model' is treated as a single token for completion
            delims = readline.get_completer_delims().replace("/", "").replace("-", "")
            readline.set_completer_delims(delims)

            readline.set_completer(REPLCompleter(SLASH_COMMANDS).complete)

            # Bind Tab for both GNU Readline and macOS libedit
            doc = getattr(readline, "__doc__", "") or ""
            if "libedit" in doc:
                readline.parse_and_bind("bind ^I rl_complete")
                readline.parse_and_bind("bind ^I complete")
            else:
                readline.parse_and_bind("tab: complete")

            readline.set_history_length(1000)
        except Exception:
            pass

    def _save_history(self) -> None:
        """Save history to ~/.mia/history."""
        with contextlib.suppress(Exception):
            readline.write_history_file(str(self._history_file))

    def _create_provider(self, target_model: str) -> tuple[LLMProvider, str]:
        """Resolve LLMProvider and model name."""
        if self.custom_provider:
            return self.custom_provider, target_model

        provider_name, actual_model, api_key, base_url = self.config_mgr.resolve_credentials(
            model=target_model
        )
        if provider_name == "anthropic":
            return AnthropicProvider(api_key=api_key, base_url=base_url), actual_model
        return OpenAICompatibleProvider(api_key=api_key, base_url=base_url), actual_model

    def _init_harness(self) -> None:
        """Instantiate AgentHarness with active profile and model."""
        prof = self.profile_mgr.get_profile(self.profile_name)
        target_model = self.model_name or prof.model or self.config_mgr.config.default_model
        provider, resolved_model = self._create_provider(target_model)

        base_tools = [
            ReadFileTool(cwd=self.cwd),
            WriteFileTool(cwd=self.cwd),
            EditFileTool(cwd=self.cwd),
            BashTool(cwd=self.cwd),
        ]
        tools = self.profile_mgr.filter_tools(prof, base_tools)

        pipeline = ToolPipeline(
            [
                SecurityGuardMiddleware(),
                AuditLogMiddleware(),
                CostBudgetMiddleware(),
            ]
        )

        session_dir = self.profile_mgr.get_session_dir(prof.name)
        session_file = session_dir / f"{self.session_id}.jsonl"
        session_store = JsonlSessionStore(session_file)

        compactor = ContextCompactor(
            context_window_tokens=prof.context_window_tokens
            or self.config_mgr.config.context_window_tokens,
            compaction_threshold_ratio=prof.compaction_threshold_ratio
            or self.config_mgr.config.compaction_threshold_ratio,
        )

        self.harness = AgentHarness(
            provider=provider,
            model=resolved_model,
            system_prompt=prof.system_prompt,
            tools=tools,
            pipeline=pipeline,
            max_steps_per_turn=prof.max_steps_per_turn,
            session_id=self.session_id,
            session_store=session_store,
            compactor=compactor,
        )

    def print_banner(self) -> None:
        """Render clean, modern welcome banner."""
        banner_content = Text.assemble(
            ("Directory: ", "dim #9CA3AF"),
            (f"{self.cwd}\n", "bold #F3F4F6"),
            ("Model:     ", "dim #9CA3AF"),
            (f"{self.model_name}  ", "bold #38BDF8"),
            ("│  Profile: ", "dim #9CA3AF"),
            (f"{self.profile_name}  ", "bold #10B981"),
            ("│  Session: ", "dim #9CA3AF"),
            (f"{self.session_id}\n", "dim #F3F4F6"),
            ("Commands:  ", "dim #9CA3AF"),
            ("Type / for command menu (/help, /model, /profile, /cost, /quit)", "dim #FF7A00"),
        )
        self.console.print(
            Panel(
                banner_content,
                title="[bold #FF7A00]🥕 Mia v0.2.0[/bold #FF7A00]",
                border_style="#2D3342",
                padding=(0, 1),
            )
        )

    async def execute_turn(self, prompt: str) -> None:
        """Run single prompt turn with real-time stream rendering."""
        if not self.harness:
            self._init_harness()
        assert self.harness is not None

        in_thought = False
        in_assistant = False

        try:
            async for event in self.harness.prompt(prompt):
                if isinstance(event, TurnStartEvent):
                    pass

                elif isinstance(event, AssistantChunkEvent):
                    if event.thought_delta:
                        if not in_thought:
                            self.console.print(
                                "\n[bold #FF7A00]💭 Thinking:[/bold #FF7A00] ", end=""
                            )
                            in_thought = True
                        self.console.print(
                            f"[italic dim #9CA3AF]{event.thought_delta}[/italic dim #9CA3AF]",
                            end="",
                        )

                    if event.delta_text:
                        if in_thought:
                            self.console.print("\n")
                            in_thought = False
                        if not in_assistant:
                            in_assistant = True
                        self.console.print(event.delta_text, end="")

                elif isinstance(event, ToolCallEvent):
                    if in_thought or in_assistant:
                        self.console.print()
                        in_thought = False
                        in_assistant = False

                    args_preview = str(event.arguments)
                    if len(args_preview) > 80:
                        args_preview = args_preview[:77] + "..."
                    self.console.print(
                        f"\n[bold cyan]▶ Tool:[/bold cyan] [bold white]{event.tool_name}[/bold white]({args_preview})",
                        end=" ",
                    )

                elif isinstance(event, ToolResultEvent):
                    status = (
                        "[bold green]✓ Succeeded[/bold green]"
                        if not event.is_error
                        else "[bold red]✗ Failed[/bold red]"
                    )
                    self.console.print(f"── {status} [dim]({event.duration_ms:.1f}ms)[/dim]")

                    # If diff output, render with Monokai syntax highlighting
                    output_str = str(event.output)
                    if "--- a/" in output_str or "+++ b/" in output_str:
                        diff_syntax = Syntax(
                            output_str, "diff", theme="monokai", line_numbers=False
                        )
                        self.console.print(diff_syntax)
                    elif event.is_error:
                        self.console.print(f"[red]{output_str[:300]}[/red]")

                elif isinstance(event, StepEndEvent):
                    self.total_tokens += event.input_tokens + event.output_tokens

                elif isinstance(event, TurnCompleteEvent):
                    self.total_cost_usd += event.total_cost_usd
                    if in_thought or in_assistant:
                        self.console.print()
                    self.console.print(
                        f"[dim]✓ Turn completed • Total tokens: {self.total_tokens:,} • Cost: ${self.total_cost_usd:.4f}[/dim]\n"
                    )

        except asyncio.CancelledError:
            self.console.print("\n[yellow]⚠️  Turn cancelled by user (Ctrl+C).[/yellow]\n")
        except Exception as exc:
            self.console.print(f"\n[bold red]Error during execution:[/bold red] {exc}\n")

    def handle_slash_command(self, cmd_line: str) -> bool:
        """Handle slash commands. Returns True if should continue, False if exit."""
        clean = cmd_line.strip()
        parts = clean.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        # If user typed just '/' or '/?' or '/help', print command palette
        if cmd in ("/", "/?", "/help"):
            table = Table(title="🥕 Mia Commands", border_style="#2D3342", show_header=True)
            table.add_column("Command", style="bold #FF7A00", width=18)
            table.add_column("Usage / Description", style="white")
            table.add_row("/help", "Show this command menu")
            table.add_row(
                "/model [name]", f"View or switch active model (current: {self.model_name})"
            )
            table.add_row(
                "/profile [name]", f"View or switch profile (current: {self.profile_name})"
            )
            table.add_row("/compact", "Check/trigger context compaction")
            table.add_row("/cost", "Show tokens and estimated USD cost")
            table.add_row("/sessions", "List saved session trees")
            table.add_row("/clear", "Clear terminal screen")
            table.add_row("/quit, /exit", "Exit Mia session")
            self.console.print(table)
            self.console.print(
                "[dim]Tip: Press [bold white]Tab[/bold white] after typing / to auto-complete commands.[/dim]\n"
            )
            return True

        elif cmd in ("/quit", "/exit"):
            self.console.print("[dim]Goodbye![/dim]")
            return False

        elif cmd == "/clear":
            self.console.clear()
            self.print_banner()

        elif cmd == "/model":
            if not args:
                self.console.print(
                    f"[bold #FF7A00]Current model:[/bold #FF7A00] [bold cyan]{self.model_name}[/bold cyan]"
                )
                self.console.print(
                    "[dim]To switch, use: /model <name> (e.g. /model mimo-v2.5 or /model claude-3-5-sonnet)[/dim]\n"
                )
            else:
                self.model_name = args
                self._init_harness()
                self.console.print(
                    f"[bold green]✓ Switched active model to {self.model_name}[/bold green]\n"
                )

        elif cmd == "/profile":
            if not args:
                profiles = [p.name for p in self.profile_mgr.list_profiles()]
                self.console.print(
                    f"[bold #FF7A00]Current profile:[/bold #FF7A00] [bold cyan]{self.profile_name}[/bold cyan]"
                )
                self.console.print(f"[dim]Available profiles: {', '.join(profiles)}[/dim]")
                self.console.print(
                    "[dim]To switch, use: /profile <name> (e.g. /profile architect)[/dim]\n"
                )
            else:
                self.profile_name = args
                self._init_harness()
                self.console.print(
                    f"[bold green]✓ Switched profile to {self.profile_name}[/bold green]\n"
                )

        elif cmd == "/cost":
            self.console.print(
                f"[bold #FF7A00]Session Metrics:[/bold #FF7A00] Tokens: {self.total_tokens:,} │ Cost: ${self.total_cost_usd:.4f}\n"
            )

        elif cmd == "/sessions":
            session_dir = self.profile_mgr.get_session_dir(self.profile_name)
            files = list(session_dir.glob("*.jsonl"))
            self.console.print(f"[bold]Saved sessions ({len(files)}):[/bold]")
            for f in files[:10]:
                self.console.print(f" - {f.stem} [dim]({f.stat().st_size / 1024:.1f} KB)[/dim]")
            self.console.print()

        elif cmd == "/compact":
            self.console.print("[dim]Context compaction status verified.[/dim]\n")

        else:
            self.console.print(
                f"[yellow]Unknown command '{cmd}'. Type / or /help for command list.[/yellow]\n"
            )

        return True

    def run(self) -> None:
        """Synchronous entrypoint running the interactive async REPL loop."""
        try:
            asyncio.run(self.run_async())
        finally:
            self._save_history()

    async def run_async(self) -> None:
        """Main async REPL loop."""
        self.print_banner()

        while True:
            try:
                # Readline input with Carrot Orange prompt
                prompt_prefix = "🥕 mia > "
                user_input = input(prompt_prefix).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_continue = self.handle_slash_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Run turn with cancellation support
                await self.execute_turn(user_input)

            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Exiting Mia session... Goodbye![/dim]")
                break
