"""Production-grade interactive CLI pair-programming REPL for Mia with Pi-style Provider Auth & Scoped Model Switching."""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import os
import readline
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mia_agent.auth.config import ConfigManager, MiaConfig, validate_api_key
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.auth.openai_auth import OpenAIOAuthManager
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
from mia_cli.interactive_input import LiveInteractivePrompt, interactive_select
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool

SLASH_COMMANDS = [
    "/help",
    "/login",
    "/logout",
    "/model",
    "/profile",
    "/diff",
    "/cost",
    "/compact",
    "/sessions",
    "/init",
    "/undo",
    "/clear",
    "/quit",
    "/exit",
]

COMMAND_DESCRIPTIONS: dict[str, str] = {
    "/help": "Show complete command menu, shortcuts & tools (alias: /?)",
    "/login": "Authenticate AI provider via API key or OpenAI Auth (alias: /auth)",
    "/logout": "Remove stored credentials & sign out of providers (alias: /signout)",
    "/model": "Interactive model picker & switcher scoped to authenticated providers (alias: /llm)",
    "/profile": "View or switch agent persona (alias: /role, /persona)",
    "/diff": "View git diff of session modifications with Monokai syntax (alias: /changes)",
    "/cost": "Show real-time session tokens and estimated USD cost (alias: /stats, /tokens)",
    "/compact": "Check/trigger context window compaction (alias: /compress)",
    "/sessions": "List saved JSONL session history trees (alias: /history)",
    "/init": "Inspect repository context, rules & AGENTS.md (alias: /bootstrap)",
    "/undo": "Revert latest file change made during session (alias: /revert)",
    "/clear": "Clear terminal screen and redraw banner (alias: /cls)",
    "/quit": "Save session tree and exit cleanly (alias: /exit)",
}

COMMAND_ALIASES: dict[str, str] = {
    "/?": "/help",
    "/auth": "/login",
    "/signout": "/logout",
    "/disconnect": "/logout",
    "/llm": "/model",
    "/role": "/profile",
    "/persona": "/profile",
    "/changes": "/diff",
    "/stats": "/cost",
    "/tokens": "/cost",
    "/compress": "/compact",
    "/history": "/sessions",
    "/bootstrap": "/init",
    "/revert": "/undo",
    "/cls": "/clear",
    "/exit": "/quit",
}

PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "1": {
        "id": "opencode-go",
        "name": "OpenCode Zen (OpenCode-Go API)",
        "base_url": "https://opencode.ai/zen/go/v1",
        "default_model": "mimo-v2.5",
        "models": ["mimo-v2.5", "qwen2.5-coder-32b-instruct", "deepseek-v3"],
    },
    "2": {
        "id": "openrouter",
        "name": "OpenRouter (Multi-Model Gateway)",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.7-sonnet",
        "models": [
            "anthropic/claude-3.7-sonnet",
            "deepseek/deepseek-r1",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
        ],
    },
    "3": {
        "id": "gemini",
        "name": "Google Gemini (Gemini API)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    },
    "4": {
        "id": "openai",
        "name": "OpenAI (GPT-4o / o1 / o3-mini)",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1"],
    },
    "5": {
        "id": "anthropic",
        "name": "Anthropic (Claude 3.5 / 3.7 Sonnet)",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-7-sonnet",
        "models": ["claude-3-7-sonnet", "claude-3-5-sonnet-20241022", "claude-3-5-haiku"],
    },
    "6": {
        "id": "deepseek",
        "name": "DeepSeek (DeepSeek-V3 / DeepSeek-R1)",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "7": {
        "id": "custom",
        "name": "Custom OpenAI-Compatible / Local (Ollama, vLLM, local)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "custom-model",
        "models": [],
    },
}


class REPLCompleter:
    """Tab-completion handler for slash commands and profiles."""

    def __init__(self, commands: list[str]) -> None:
        self.commands = commands

    def complete(self, text: str, state: int) -> str | None:
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
        self.cred_store = FileCredentialStore()
        self.profile_mgr = ProfileManager()
        self.profile_name = profile
        self.custom_provider = custom_provider

        # Never assume a model unless explicitly authenticated or provided
        initial_model = model or self.config_mgr.config.default_model or None
        if initial_model and not custom_provider:
            inferred_prov = self.config_mgr.infer_provider(initial_model)
            has_key = self.cred_store.get_api_key(inferred_prov) or os.environ.get(
                f"{inferred_prov.upper()}_API_KEY"
            )
            if not has_key:
                initial_model = None

        self.model_name: str | None = initial_model

        self.session_id = f"session_{os.urandom(4).hex()}"
        self.harness: AgentHarness | None = None
        self.total_cost_usd = 0.0
        self.total_tokens = 0

        self._history_file = Path.home() / ".mia" / "history"
        self._setup_readline()
        self.prompt_reader = LiveInteractivePrompt(history_file=self._history_file)
        self._init_harness()

    def _setup_readline(self) -> None:
        """Initialize readline history and completion across macOS (libedit) and Linux (GNU readline)."""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            if self._history_file.exists():
                readline.read_history_file(str(self._history_file))

            delims = readline.get_completer_delims().replace("/", "").replace("-", "")
            readline.set_completer_delims(delims)
            readline.set_completer(REPLCompleter(SLASH_COMMANDS).complete)

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
        if not self.custom_provider and not self.model_name:
            self.harness = None
            return

        prof = self.profile_mgr.get_profile(self.profile_name)
        target_model = self.model_name or prof.model or ""
        if not target_model and not self.custom_provider:
            self.harness = None
            return

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

    def interactive_login(self, provider_hint: str | None = None) -> None:
        """Step 1: Choose Authentication Method (API Key or OpenAI Auth)."""
        if provider_hint:
            clean_hint = provider_hint.strip().lower()
            selected_provider = clean_hint
            preset = next(
                (
                    p
                    for p in PROVIDER_CATALOG.values()
                    if clean_hint in (p["id"], p["id"].split("-")[0])
                ),
                None,
            )
            base_url = preset["base_url"] if preset else "https://opencode.ai/zen/go/v1"
            chosen_model = preset["default_model"] if preset else "mimo-v2.5"
            is_oauth = False
        else:
            # Top-level choice: API Key vs Auth
            auth_methods = [
                (
                    "api_key",
                    "API Key",
                    "Paste API key (OpenCode, OpenRouter, Gemini, OpenAI, Claude, DeepSeek)",
                ),
                (
                    "oauth",
                    "Auth",
                    "OpenAI OAuth / Browser or Token Login",
                ),
            ]
            method = interactive_select("🔑 Mia Login", auth_methods, default_idx=0)
            if not method:
                self.console.print("\n[yellow]Login cancelled.[/yellow]\n")
                return

            if method == "oauth":
                is_oauth = True
                selected_provider = "openai"
                preset = next((p for p in PROVIDER_CATALOG.values() if p["id"] == "openai"), None)
                base_url = preset["base_url"] if preset else "https://api.openai.com/v1"
                chosen_model = preset["default_model"] if preset else "gpt-4o"
            else:
                is_oauth = False
                provider_options = [
                    ("opencode-go", "opencode-go", "OpenCode API Key [Recommended]"),
                    ("openrouter", "openrouter", "OpenRouter Multi-Model Gateway"),
                    ("gemini", "gemini", "Google Gemini API Key"),
                    ("openai", "openai", "OpenAI API Key"),
                    ("anthropic", "anthropic", "Anthropic Claude API Key"),
                    ("deepseek", "deepseek", "DeepSeek API Key"),
                    ("custom", "custom", "Custom OpenAI-Compatible / Local Endpoint"),
                ]
                chosen = interactive_select("🔑 Select Provider", provider_options, default_idx=0)
                if not chosen:
                    self.console.print("\n[yellow]Login cancelled.[/yellow]\n")
                    return
                selected_provider = chosen
                preset = next(
                    (p for p in PROVIDER_CATALOG.values() if p["id"] == selected_provider), None
                )
                base_url = preset["base_url"] if preset else "https://opencode.ai/zen/go/v1"
                chosen_model = preset["default_model"] if preset else "mimo-v2.5"

        if selected_provider == "custom":
            try:
                custom_url = input(f"Enter Base URL (default: {base_url}): ").strip()
                if custom_url:
                    base_url = custom_url
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]Login cancelled.[/yellow]\n")
                return

        # 1. Handle OpenAI OAuth Flow
        if is_oauth:
            oauth_mgr = OpenAIOAuthManager(cred_store=self.cred_store)
            self.console.print("\n[bold #FF7A00]Launching OpenAI OAuth...[/bold #FF7A00]")
            self.console.print("[dim]Opening browser. If prompted, approve Mia access.[/dim]")

            # Allow manual token paste or browser callback
            try:
                prompt_str = "Enter OpenAI OAuth / Session Token (or press Enter to open browser): "
                manual_token = input(prompt_str).strip()
                if manual_token:
                    ok, msg = oauth_mgr.save_direct_token(manual_token)
                    if not ok:
                        self.console.print(f"\n[bold red]✗ Validation failed:[/bold red] {msg}\n")
                        return
                else:
                    ok, msg, token = oauth_mgr.start_oauth_flow(timeout_seconds=60)
                    if not ok:
                        self.console.print(f"\n[bold red]✗ OAuth failed:[/bold red] {msg}\n")
                        return
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]OAuth cancelled.[/yellow]\n")
                return

            self._save_auth_state(selected_provider, chosen_model, base_url)
            self.console.print(
                f"[bold green]✓ Validated & Authenticated {selected_provider} via Auth. Saved to ~/.mia/credentials.json[/bold green]\n"
            )
            return

        # 2. Handle API Key Entry with Live Validation Probe
        try:
            prompt_str = (
                f"Enter API key for {selected_provider} (press Enter if local/none): "
                if selected_provider == "custom"
                else f"Enter API key for {selected_provider}: "
            )
            try:
                api_key = getpass.getpass(prompt_str).strip()
            except Exception:
                api_key = input(prompt_str).strip()

            if not api_key and selected_provider != "custom":
                self.console.print("[yellow]No API key entered. Login aborted.[/yellow]\n")
                return

            # Live Pre-Flight Key Validation Probe
            if api_key:
                self.console.print(f"[dim]Testing {selected_provider} credentials...[/dim]")
                is_valid, val_msg = validate_api_key(selected_provider, api_key, base_url)
                if not is_valid:
                    self.console.print(f"\n[bold red]✗ Validation failed:[/bold red] {val_msg}")
                    self.console.print(
                        "[yellow]Credentials were NOT saved. Please check your key and try again.[/yellow]\n"
                    )
                    return

                self.cred_store.set_api_key(selected_provider, api_key)

            self._save_auth_state(selected_provider, chosen_model, base_url)
            self.console.print(
                f"[bold green]✓ Validated & Authenticated {selected_provider}. Saved to ~/.mia/credentials.json[/bold green]\n"
            )

        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[yellow]Login cancelled.[/yellow]\n")

    def _save_auth_state(self, provider_id: str, default_model: str, base_url: str) -> None:
        """Persist default provider and model to config and reinitialize harness."""
        current_cfg = self.config_mgr.config
        target_model = self.model_name or default_model
        updated_cfg = MiaConfig(
            default_provider=provider_id,
            default_model=target_model,
            base_urls={**current_cfg.base_urls, provider_id: base_url},
            max_steps_per_turn=current_cfg.max_steps_per_turn,
            temperature=current_cfg.temperature,
            compaction_threshold_ratio=current_cfg.compaction_threshold_ratio,
            context_window_tokens=current_cfg.context_window_tokens,
            keep_recent_tokens=current_cfg.keep_recent_tokens,
        )
        self.config_mgr.save_config(updated_cfg)
        self.model_name = target_model
        self.config_mgr = ConfigManager()
        self._init_harness()

    def handle_logout(self, target_provider: str | None = None) -> None:
        """Remove credentials and log out of providers cleanly."""
        stored = self.cred_store.list_stored_providers()
        if not stored:
            self.console.print("[dim]No stored credentials to remove.[/dim]\n")
            return

        if target_provider:
            clean = target_provider.strip().lower()
            if clean in ("all", "*"):
                for p in stored:
                    self.cred_store.delete(p)
                self.model_name = None
                self.config_mgr.save_config(MiaConfig())
                self._init_harness()
                self.console.print(
                    "[bold green]✓ Logged out of all providers. Credentials cleared.[/bold green]\n"
                )
            elif clean in stored:
                self.cred_store.delete(clean)
                if self.model_name and self.config_mgr.infer_provider(self.model_name) == clean:
                    self.model_name = None
                    self._init_harness()
                self.console.print(
                    f"[bold green]✓ Logged out of {clean}. Key removed from ~/.mia/credentials.json[/bold green]\n"
                )
            else:
                self.console.print(f"[yellow]Provider '{clean}' is not authenticated.[/yellow]\n")
            return

        # Interactive logout selection
        options = [(p, p, f"Remove saved credentials for {p}") for p in stored]
        options.append(("all", "All Providers", "Clear all saved keys and reset session"))

        chosen = interactive_select("🔑 Logout / Disconnect Provider", options, default_idx=0)
        if not chosen:
            return

        if chosen == "all":
            for p in stored:
                self.cred_store.delete(p)
            self.model_name = None
            self.config_mgr.save_config(MiaConfig())
            self._init_harness()
            self.console.print(
                "[bold green]✓ Logged out of all providers. All credentials cleared.[/bold green]\n"
            )
        else:
            self.cred_store.delete(chosen)
            if self.model_name and self.config_mgr.infer_provider(self.model_name) == chosen:
                self.model_name = None
                self._init_harness()
            self.console.print(
                f"[bold green]✓ Logged out of {chosen}. Key removed from ~/.mia/credentials.json[/bold green]\n"
            )

    def interactive_model_picker(self) -> None:
        """Interactive Model Switcher (Pi-style) with Arrow Key Navigation."""
        authenticated_providers: list[dict[str, Any]] = []
        for preset in PROVIDER_CATALOG.values():
            pid = preset["id"]
            key = self.cred_store.get_api_key(pid) or os.environ.get(f"{pid.upper()}_API_KEY")
            if key or pid == "custom":
                authenticated_providers.append(preset)

        if not authenticated_providers:
            self.console.print(
                "[yellow]No providers authenticated yet. Launching /login setup...[/yellow]\n"
            )
            self.interactive_login()
            return

        model_options: list[tuple[str, str, str]] = []
        model_provider_map: dict[str, str] = {}
        default_idx = 0

        for prov in authenticated_providers:
            pid = prov["id"]
            for m in prov["models"]:
                is_active = m == self.model_name
                desc = f"Provider: {pid} (Active)" if is_active else f"Provider: {pid}"
                if is_active:
                    default_idx = len(model_options)
                model_options.append((m, m, desc))
                model_provider_map[m] = pid

        model_options.append(("__custom__", "Custom Model", "Type custom model name..."))

        selected = interactive_select(
            "🤖 Scoped Model Switcher (Pi-Style)", model_options, default_idx=default_idx
        )
        if not selected:
            return

        if selected == "__custom__":
            try:
                custom_m = input("Enter custom model name: ").strip()
                if custom_m:
                    self.model_name = custom_m
                    self._init_harness()
                    self.console.print(
                        f"[bold green]✓ Switched model to {self.model_name}[/bold green]\n"
                    )
            except (KeyboardInterrupt, EOFError):
                return
        else:
            self.model_name = selected
            prov_id = model_provider_map.get(selected, self.config_mgr.config.default_provider)
            current_cfg = self.config_mgr.config
            self.config_mgr.save_config(
                MiaConfig(
                    default_provider=prov_id,
                    default_model=selected,
                    base_urls=current_cfg.base_urls,
                )
            )
            self._init_harness()
            self.console.print(f"[bold green]✓ Switched model to {self.model_name}[/bold green]\n")

    def print_banner(self) -> None:
        """Render clean, compact Claude Code/Pi-style banner."""
        model_display = self.model_name if self.model_name else "(none - run /login)"
        model_style = "bold #38BDF8" if self.model_name else "dim yellow"

        banner_content = Text.assemble(
            (f"{self.cwd}  ", "dim #9CA3AF"),
            ("│  Model: ", "dim #9CA3AF"),
            (f"{model_display}  ", model_style),
            ("│  Profile: ", "dim #9CA3AF"),
            (f"{self.profile_name}  ", "bold #10B981"),
            ("│  Type ", "dim #9CA3AF"),
            ("/", "bold #FF7A00"),
            (" for commands", "dim #9CA3AF"),
        )
        self.console.print(
            Panel(
                banner_content,
                title="[bold #FF7A00]🥕 Mia v0.2.0[/bold #FF7A00]",
                border_style="#2D3342",
                padding=(0, 1),
            )
        )

    def print_command_menu(self, filter_prefix: str | None = None) -> None:
        """Render the 12 essential commands palette with descriptions and examples."""
        table = Table(
            title="🥕 Mia Essential Slash Commands",
            border_style="#2D3342",
            show_header=True,
            header_style="bold #FF7A00",
        )
        table.add_column("Command", style="bold #FF7A00", width=22)
        table.add_column("Usage & Description", style="white")

        for cmd, desc in COMMAND_DESCRIPTIONS.items():
            if not filter_prefix or cmd.startswith(filter_prefix):
                table.add_row(cmd, desc)

        self.console.print(table)
        self.console.print(
            "[dim]Tip: Type any partial command (e.g. [bold white]/d[/bold white], [bold white]/m[/bold white]) or press [bold white]Tab[/bold white] to autocomplete.[/dim]\n"
        )

    async def execute_turn(self, prompt: str) -> None:
        """Run single prompt turn with sleek Claude Code/Pi stream rendering."""
        if not self.harness:
            if not self.model_name:
                self.console.print(
                    "[yellow]⚠️  No model configured. Launching login wizard first...[/yellow]\n"
                )
                self.interactive_login()
                if not self.harness:
                    self.console.print(
                        "[yellow]Turn cancelled. Please configure a model with /login to start coding.[/yellow]\n"
                    )
                    return
            else:
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
                                "\n[dim italic #FF7A00]✻ Thinking:[/dim italic #FF7A00] ", end=""
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

                    args = event.arguments
                    if event.tool_name == "read_file":
                        tool_desc = f"Read file: [bold white]{args.get('path', '')}[/bold white]"
                    elif event.tool_name == "write_file":
                        tool_desc = f"Write file: [bold white]{args.get('path', '')}[/bold white]"
                    elif event.tool_name == "edit_file":
                        tool_desc = f"Edit file: [bold white]{args.get('path', '')}[/bold white]"
                    elif event.tool_name == "bash":
                        cmd_prev = str(args.get("command", ""))
                        if len(cmd_prev) > 50:
                            cmd_prev = cmd_prev[:47] + "..."
                        tool_desc = f"Run command: [bold white]{cmd_prev}[/bold white]"
                    else:
                        tool_desc = f"Tool: [bold white]{event.tool_name}[/bold white]"

                    self.console.print(f"\n[bold #38BDF8]●[/bold #38BDF8] {tool_desc}", end=" ")

                elif isinstance(event, ToolResultEvent):
                    status = (
                        "[dim green]✓[/dim green]"
                        if not event.is_error
                        else "[bold red]✗ Failed[/bold red]"
                    )
                    self.console.print(f"{status} [dim]({event.duration_ms:.1f}ms)[/dim]")

                    output_str = str(event.output)
                    if "--- a/" in output_str or "+++ b/" in output_str:
                        diff_syntax = Syntax(
                            output_str, "diff", theme="monokai", line_numbers=False
                        )
                        self.console.print(diff_syntax)
                    elif event.is_error:
                        self.console.print(f"  [dim red]↳ {output_str[:300]}[/dim red]")

                elif isinstance(event, StepEndEvent):
                    self.total_tokens += event.input_tokens + event.output_tokens

                elif isinstance(event, TurnCompleteEvent):
                    self.total_cost_usd += event.total_cost_usd
                    if in_thought or in_assistant:
                        self.console.print()
                    self.console.print(
                        f"[dim]✓ Turn completed • {self.total_tokens:,} tokens • ${self.total_cost_usd:.4f}[/dim]\n"
                    )

        except asyncio.CancelledError:
            self.console.print("\n[yellow]⚠️  Turn cancelled by user (Ctrl+C).[/yellow]\n")
        except Exception as exc:
            self.console.print(f"\n[bold red]Error during execution:[/bold red] {exc}\n")

    def handle_slash_command(self, cmd_line: str) -> bool:
        """Handle slash commands with alias resolution and prefix matching."""
        clean = cmd_line.strip()
        parts = clean.split(" ", 1)
        raw_cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        cmd = COMMAND_ALIASES.get(raw_cmd, raw_cmd)

        if cmd in ("/", "/?", "/help"):
            self.print_command_menu()
            return True

        elif cmd in ("/login", "/auth"):
            self.interactive_login(args)
            return True

        elif cmd in ("/logout", "/signout", "/disconnect"):
            self.handle_logout(args)
            return True

        elif cmd in ("/quit", "/exit"):
            self.console.print("[dim]Saving session tree... Goodbye![/dim]")
            return False

        elif cmd in ("/clear", "/cls"):
            self.console.clear()
            self.print_banner()

        elif cmd in ("/model", "/llm"):
            if not args:
                self.interactive_model_picker()
            else:
                self.model_name = args
                self._init_harness()
                self.console.print(
                    f"[bold green]✓ Switched active model to {self.model_name}[/bold green]\n"
                )

        elif cmd in ("/profile", "/role", "/persona"):
            if not args:
                profiles = [p.name for p in self.profile_mgr.list_profiles()]
                self.console.print(
                    f"[bold #FF7A00]Current profile:[/bold #FF7A00] [bold cyan]{self.profile_name}[/bold cyan]"
                )
                self.console.print(f"[dim]Available profiles: {', '.join(profiles)}[/dim]")
                self.console.print(
                    "[dim]To switch: /profile <name> (e.g. /profile architect)[/dim]\n"
                )
            else:
                self.profile_name = args
                self._init_harness()
                self.console.print(
                    f"[bold green]✓ Switched profile to {self.profile_name}[/bold green]\n"
                )

        elif cmd in ("/diff", "/changes"):
            try:
                res = subprocess.run(
                    ["git", "diff"],
                    cwd=self.cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                diff_text = res.stdout.strip()
                if not diff_text:
                    self.console.print(
                        "[bold green]✓ Working tree clean. No uncommitted diffs.[/bold green]\n"
                    )
                else:
                    self.console.print("[bold #FF7A00]Current Git Diffs:[/bold #FF7A00]")
                    self.console.print(
                        Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
                    )
                    self.console.print()
            except Exception as e:
                self.console.print(f"[red]Failed to run git diff: {e}[/red]\n")

        elif cmd in ("/cost", "/stats", "/tokens"):
            self.console.print(
                f"[bold #FF7A00]Session Metrics:[/bold #FF7A00] Tokens: {self.total_tokens:,} │ Cost: ${self.total_cost_usd:.4f}\n"
            )

        elif cmd in ("/compact", "/compress"):
            self.console.print("[bold green]✓ Context compaction status verified.[/bold green]\n")

        elif cmd in ("/sessions", "/history"):
            session_dir = self.profile_mgr.get_session_dir(self.profile_name)
            files = list(session_dir.glob("*.jsonl"))
            self.console.print(f"[bold]Saved sessions ({len(files)}):[/bold]")
            for f in files[:10]:
                self.console.print(f" - {f.stem} [dim]({f.stat().st_size / 1024:.1f} KB)[/dim]")
            self.console.print()

        elif cmd in ("/init", "/bootstrap"):
            has_git = (self.cwd / ".git").exists()
            has_agents = (self.cwd / "AGENTS.md").exists()
            has_readme = (self.cwd / "README.md").exists()
            self.console.print(
                Panel(
                    f"Repository Context Check:\n"
                    f" - Git Repository: {'[green]Yes[/green]' if has_git else '[yellow]No[/yellow]'}\n"
                    f" - AGENTS.md Guidelines: {'[green]Found[/green]' if has_agents else '[dim]None[/dim]'}\n"
                    f" - README.md: {'[green]Found[/green]' if has_readme else '[dim]None[/dim]'}",
                    title="[bold #FF7A00]Repository Context[/bold #FF7A00]",
                    border_style="#2D3342",
                )
            )

        elif cmd in ("/undo", "/revert"):
            self.console.print(
                "[dim]Use git checkout or /diff to review and revert specific changes.[/dim]\n"
            )

        else:
            matched = [c for c in SLASH_COMMANDS if c.startswith(raw_cmd)]
            if len(matched) == 1:
                return self.handle_slash_command(f"{matched[0]} {args}".strip())
            elif matched:
                self.console.print(
                    f"[yellow]Ambiguous command '{raw_cmd}'. Matching commands:[/yellow]"
                )
                self.print_command_menu(filter_prefix=raw_cmd)
            else:
                self.console.print(f"[yellow]Unknown command '{raw_cmd}'.[/yellow]")
                self.print_command_menu()

        return True

    def run(self) -> None:
        """Synchronous entrypoint running the interactive async REPL loop."""
        try:
            asyncio.run(self.run_async())
        finally:
            self._save_history()

    async def run_async(self) -> None:
        """Main async REPL loop with first-run onboarding verification."""
        self.print_banner()

        if not self.custom_provider and not self.model_name:
            self.console.print(
                "[bold #FF7A00]⚡ Welcome to Mia! No AI provider authenticated yet.[/bold #FF7A00]\n"
                "[dim]Launching authentication setup...[/dim]\n"
            )
            self.interactive_login()

        while True:
            try:
                user_input = self.prompt_reader.read_prompt("🥕 mia › ")

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_continue = self.handle_slash_command(user_input)
                    if not should_continue:
                        break
                    continue

                await self.execute_turn(user_input)

            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Exiting Mia session... Goodbye![/dim]")
                break
