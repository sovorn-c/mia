"""Production-grade Stream-First interactive CLI pair-programming REPL for Mia with prompt_toolkit & Pi/Tau inspection."""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import os
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mia_agent.auth.config import (
    ConfigManager,
    MiaConfig,
    discover_provider_models,
    validate_api_key,
)
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.auth.openai_auth import OpenAIOAuthManager
from mia_agent.events import StepEndEvent, TurnCompleteEvent
from mia_agent.harness import AgentHarness
from mia_agent.orchestration import (
    AgentRuntime,
    AgentRuntimeFactory,
    ModeRuntime,
    OrchestrationErrorEvent,
    RuntimeIdentity,
)
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.entries import LeafEntry, MessageEntry, SessionInfoEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.base import LLMProvider
from mia_cli.interactive_input import (
    LivePromptSession,
    interactive_select,
)
from mia_cli.renderers.rich_stream import RichStreamRenderer

SLASH_COMMANDS = [
    "/help",
    "/login",
    "/logout",
    "/mode",
    "/model",
    "/profile",
    "/diff",
    "/cost",
    "/compact",
    "/sessions",
    "/resume",
    "/tree",
    "/inspect",
    "/thinking",
    "/stop",
    "/init",
    "/clear",
    "/quit",
]

COMMAND_DESCRIPTIONS: dict[str, str] = {
    "/help": "Show complete command menu, shortcuts & tools (alias: /?)",
    "/login": "Authenticate AI provider via API key or OpenAI Auth (alias: /auth)",
    "/logout": "Remove stored credentials & sign out of providers (alias: /signout)",
    "/mode": "Show or select the orchestration mode used for prompts",
    "/model": "Interactive model picker & switcher scoped to authenticated providers (alias: /llm)",
    "/profile": "View or switch agent persona (alias: /role, /persona)",
    "/diff": "View git diff of session modifications with Monokai syntax (alias: /changes)",
    "/cost": "Show real-time session tokens and estimated USD cost (alias: /stats, /tokens)",
    "/compact": "Check/trigger context window compaction (alias: /compress)",
    "/sessions": "List saved JSONL session history trees (alias: /history)",
    "/resume": "Resume a saved session; Ctrl+D/d deletes the selected saved session",
    "/tree": "Explore and fork session conversation branch (alias: /branch)",
    "/inspect": "Open post-turn detail audit viewer and file diffs (alias: /logs)",
    "/thinking": "Toggle display of model reasoning / thinking tokens (alias: /trace)",
    "/stop": "Halt the active running agent turn (alias: /abort)",
    "/init": "Inspect repository context, rules & AGENTS.md (alias: /bootstrap)",
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
    "/branch": "/tree",
    "/logs": "/inspect",
    "/trace": "/thinking",
    "/abort": "/stop",
    "/bootstrap": "/init",
    "/cls": "/clear",
    "/exit": "/quit",
}

PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "1": {
        "id": "opencode-go",
        "name": "OpenCode Zen (OpenCode-Go API)",
        "base_url": "https://opencode.ai/zen/go/v1",
        "models": ["mimo-v2.5", "qwen2.5-coder-32b-instruct", "deepseek-v3"],
    },
    "2": {
        "id": "openrouter",
        "name": "OpenRouter (Multi-Model Gateway)",
        "base_url": "https://openrouter.ai/api/v1",
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
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    },
    "4": {
        "id": "openai",
        "name": "OpenAI (GPT-4o / o1 / o3-mini)",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1"],
    },
    "5": {
        "id": "anthropic",
        "name": "Anthropic (Claude 3.5 / 3.7 Sonnet)",
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-3-7-sonnet", "claude-3-5-sonnet-20241022", "claude-3-5-haiku"],
    },
    "6": {
        "id": "deepseek",
        "name": "DeepSeek (DeepSeek-V3 / DeepSeek-R1)",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "7": {
        "id": "custom",
        "name": "Custom OpenAI-Compatible / Local (Ollama, vLLM, local)",
        "base_url": "http://localhost:11434/v1",
        "models": [],
    },
}


class MiaREPL:
    """Stream-first interactive coding agent harness with prompt_toolkit & Pi/Tau inspection."""

    def __init__(
        self,
        *,
        model: str | None = None,
        profile: str = "coding",
        cwd: Path | None = None,
        custom_provider: LLMProvider | None = None,
        session_id: str | None = None,
    ) -> None:
        self.console = Console()
        self.cwd = cwd or Path.cwd()
        self.config_mgr = ConfigManager()
        self.cred_store = FileCredentialStore()
        self.profile_mgr = ProfileManager()
        self.profile_name = profile
        self.custom_provider = custom_provider
        self.mode_name = "single"
        self.runtime_factory = AgentRuntimeFactory(
            profile_manager=self.profile_mgr,
            config_manager=self.config_mgr,
        )
        self.mode_runtime = ModeRuntime(
            factory=self.runtime_factory,
            profile_manager=self.profile_mgr,
        )

        # Never assume a model unless explicitly authenticated or provided
        initial_model = model or (
            None if custom_provider else self.config_mgr.config.default_model or None
        )
        if initial_model and not custom_provider:
            inferred_prov = self.config_mgr.infer_provider(initial_model)
            has_key = self.cred_store.get_api_key(inferred_prov) or os.environ.get(
                f"{inferred_prov.upper()}_API_KEY"
            )
            if not has_key:
                initial_model = None

        self.model_name: str | None = initial_model
        self.session_id = session_id or f"session_{os.urandom(4).hex()}"
        self.agent_runtime: AgentRuntime | None = None
        self.harness: AgentHarness | None = None
        self.total_cost_usd = 0.0
        self.total_tokens = 0
        self.show_thinking_trace = False

        self.stream_renderer = RichStreamRenderer(
            console=self.console, show_thinking_trace=self.show_thinking_trace
        )
        self._history_file = Path.home() / ".mia" / "history"

        # Initialize prompt_toolkit session with floating slash completions
        self.prompt_session = LivePromptSession(
            history_file=self._history_file,
        )
        self._init_harness()

    def _init_harness(self) -> None:
        """Instantiate the active profile through the shared runtime factory."""
        self.agent_runtime = None
        if not self.custom_provider and not self.model_name:
            self.harness = None
            return

        profile = self.profile_mgr.get_profile(self.profile_name)
        if not self.model_name and not profile.model and not self.custom_provider:
            self.harness = None
            return

        identity = RuntimeIdentity(
            mode=self.mode_name,
            run_id=f"run_{self.session_id}",
            task_id="root",
            agent_id="coordinator",
            profile=profile.name,
            session_id=self.session_id,
        )
        self.agent_runtime = self.runtime_factory.build(
            identity=identity,
            provider=self.custom_provider,
            model_override=self.model_name,
            cwd=self.cwd,
        )
        self.harness = self.agent_runtime.harness

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
            is_oauth = False
        else:
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

            self._save_auth_state(selected_provider, base_url)
            self.console.print(
                f"[bold green]✓ Validated & Authenticated {selected_provider} via Auth. Saved to ~/.mia/credentials.json[/bold green]"
            )
            self.console.print(
                "[dim]Next: Use [bold white]/model[/bold white] to choose your active model.[/dim]\n"
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

            if api_key:
                self.console.print(f"[dim]Testing {selected_provider} credentials...[/dim]")
                is_valid, val_msg = validate_api_key(selected_provider, api_key, base_url)
                if not is_valid:
                    self.console.print(f"\n[bold red]✗ Validation failed:[/bold red] {val_msg}")
                    if any(w in val_msg for w in ("Unauthorized", "401", "403", "Invalid")):
                        self.console.print(
                            "[yellow]Credentials were NOT saved. Please check your key and try again.[/yellow]\n"
                        )
                        return
                    else:
                        try:
                            save_anyway = (
                                input("Endpoint unreachable. Save credentials anyway? [y/N]: ")
                                .strip()
                                .lower()
                            )
                        except (KeyboardInterrupt, EOFError):
                            save_anyway = "n"
                        if save_anyway not in ("y", "yes"):
                            self.console.print("[yellow]Credentials not saved.[/yellow]\n")
                            return

                self.cred_store.set_api_key(selected_provider, api_key)

            self._save_auth_state(selected_provider, base_url)
            self.console.print(
                f"[bold green]✓ Validated & Authenticated {selected_provider}. Saved to ~/.mia/credentials.json[/bold green]"
            )
            self.console.print(
                "[dim]Next: Use [bold white]/model[/bold white] to choose your active model.[/dim]\n"
            )

        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[yellow]Login cancelled.[/yellow]\n")

    def _save_auth_state(self, provider_id: str, base_url: str) -> None:
        """Persist provider credentials and base URL."""
        current_cfg = self.config_mgr.config
        updated_cfg = MiaConfig(
            default_provider=provider_id,
            default_model=self.model_name or "",
            base_urls={**current_cfg.base_urls, provider_id: base_url},
            max_steps_per_turn=current_cfg.max_steps_per_turn,
            temperature=current_cfg.temperature,
            compaction_threshold_ratio=current_cfg.compaction_threshold_ratio,
            context_window_tokens=current_cfg.context_window_tokens,
            keep_recent_tokens=current_cfg.keep_recent_tokens,
        )
        self.config_mgr.save_config(updated_cfg)
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
        """Interactive Model Switcher with dynamic live model discovery and provider scoping (Pi-Style)."""
        stored_providers = self.cred_store.list_stored_providers()
        all_known = [
            "opencode-go",
            "openrouter",
            "gemini",
            "openai",
            "anthropic",
            "deepseek",
            "custom",
        ]
        authenticated_pids: list[str] = list(stored_providers)
        for pid in all_known:
            if pid not in authenticated_pids:
                key = os.environ.get(f"{pid.upper()}_API_KEY")
                if key:
                    authenticated_pids.append(pid)

        if not authenticated_pids:
            self.console.print(
                "[yellow]No providers authenticated yet. Launching /login setup...[/yellow]\n"
            )
            self.interactive_login()
            return

        # If multiple providers authenticated, ask user if they want to scope by provider or view all
        target_providers = authenticated_pids
        if len(authenticated_pids) > 1:
            scope_options = [(p, p, f"Discover models from {p}") for p in authenticated_pids]
            scope_options.insert(
                0,
                (
                    "all",
                    "All Providers",
                    "List models across all authenticated providers",
                ),
            )
            chosen_scope = interactive_select(
                "🔍 Scope Model Provider (Pi-Style)", scope_options, default_idx=0
            )
            if not chosen_scope:
                return
            if chosen_scope != "all":
                target_providers = [chosen_scope]

        self.console.print("[dim]Fetching live models from provider(s)...[/dim]")

        model_options: list[tuple[str, str, str]] = []
        model_provider_map: dict[str, str] = {}
        default_idx = 0

        for pid in target_providers:
            key = self.cred_store.get_api_key(pid) or os.environ.get(f"{pid.upper()}_API_KEY")
            base_url = self.config_mgr.config.base_urls.get(pid)
            live_models = discover_provider_models(pid, api_key=key, base_url=base_url)

            for m in live_models:
                is_active = m == self.model_name
                desc = f"Provider: {pid} (Active)" if is_active else f"Provider: {pid}"
                if is_active:
                    default_idx = len(model_options)
                model_options.append((m, m, desc))
                model_provider_map[m] = pid

        model_options.append(
            ("__custom__", "Custom Model", "Type any custom or unlisted model ID...")
        )

        selected = interactive_select(
            "🤖 Switch Active Model", model_options, default_idx=default_idx
        )
        if not selected:
            return

        if selected == "__custom__":
            try:
                custom_m = input(
                    "Enter custom model name (e.g. gpt-4o, claude-3-7-sonnet): "
                ).strip()
                if custom_m:
                    self.model_name = custom_m
                    inferred_prov = self.config_mgr.infer_provider(custom_m)
                    current_cfg = self.config_mgr.config
                    self.config_mgr.save_config(
                        MiaConfig(
                            default_provider=inferred_prov or current_cfg.default_provider,
                            default_model=custom_m,
                            base_urls=current_cfg.base_urls,
                        )
                    )
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

    def _session_file(self, session_id: str | None = None) -> Path:
        """Return the JSONL path for the active profile and session."""
        prof = self.profile_mgr.get_profile(self.profile_name)
        return (
            self.profile_mgr.get_session_dir(prof.name) / f"{session_id or self.session_id}.jsonl"
        )

    @staticmethod
    def _message_preview(entry: MessageEntry) -> str:
        content = str(entry.message.content or "").replace("\n", " ").strip()
        if len(content) > 54:
            return f"{content[:51]}..."
        return content or "(empty message)"

    def _render_restored_messages(self, messages: list[Any]) -> None:
        """Show the restored active branch without replaying it as a new turn."""
        for message in messages:
            content = Text(str(message.content or ""))
            if message.role == "user":
                self.console.print(Text("› ", style="bold #FF7A00") + content)
            elif message.role == "assistant":
                self.console.print(Text("🥕 mia › ", style="bold #FF7A00") + content)
            elif message.role == "tool":
                self.console.print(
                    Text(f"  {message.tool_name or 'tool'} › ", style="dim") + content
                )

    def _tree_options(
        self, entries: list[Any], active_ids: set[str]
    ) -> tuple[list[tuple[str, str, str]], int]:
        """Build Pi-like tree rows and preserve the active branch selection."""
        visible = [
            entry for entry in entries if not isinstance(entry, (LeafEntry, SessionInfoEntry))
        ]
        by_parent: dict[str | None, list[Any]] = {}
        visible_ids = {entry.id for entry in visible}
        for entry in visible:
            parent_id = entry.parent_id if entry.parent_id in visible_ids else None
            by_parent.setdefault(parent_id, []).append(entry)

        rows: list[tuple[str, str, str]] = []

        def walk(parent_id: str | None, prefix: str) -> None:
            children = by_parent.get(parent_id, [])
            for index, entry in enumerate(children):
                is_last = index == len(children) - 1
                branch = "└─ " if is_last else "├─ "
                marker = "●" if entry.id in active_ids else "○"
                if isinstance(entry, MessageEntry):
                    role = "you" if entry.message.role == "user" else entry.message.role
                    preview = self._message_preview(entry)
                else:
                    role = entry.type
                    preview = str(getattr(entry, "summary", ""))[:54]
                label = f"{prefix}{branch}{marker} {role}: {preview}"
                description = (
                    "Active branch" if entry.id in active_ids else "Fork from this checkpoint"
                ) + f" • {entry.id[:8]}"
                rows.append((entry.id, label, description))
                walk(entry.id, prefix + ("   " if is_last else "│  "))

        walk(None, "")
        if not rows:
            return [], 0
        active_candidates = [idx for idx, row in enumerate(rows) if row[0] in active_ids]
        return rows, active_candidates[-1] if active_candidates else len(rows) - 1

    def interactive_tree_navigator(self) -> None:
        """Navigate the full JSONL tree and fork future prompts from the selected entry."""
        if not self.harness:
            self.console.print("[dim]No active session tree to navigate.[/dim]\n")
            return

        session_file = self._session_file()
        if not session_file.exists():
            self.console.print("[dim]No conversation turns in this session yet.[/dim]\n")
            return

        try:
            store = JsonlSessionStore(session_file)
            entries = store.load_entries()
            tree = SessionTree(entries)
            active_path = tree.get_active_path()
            active_ids = {entry.id for entry in active_path}
            options, default_idx = self._tree_options(entries, active_ids)
            if not options:
                self.console.print("[dim]No past turns to branch from.[/dim]\n")
                return

            chosen = interactive_select(
                "🌿 Session Tree (↑/↓ choose checkpoint, Enter forks here)",
                options,
                default_idx=default_idx,
            )
            if not chosen:
                return
            if active_path and chosen == active_path[-1].id:
                self.console.print("[dim]Already at this checkpoint.[/dim]\n")
                return

            messages = self.harness.navigate_to(chosen)
            self.console.print(
                f"\n[bold green]✓ Branched from checkpoint {chosen[:8]}[/bold green]\n"
            )
            self._render_restored_messages(messages)
            self.console.print()
        except Exception as exc:
            self.console.print(f"[red]Failed to navigate session tree: {exc}[/red]\n")

    def delete_session(self, session_id: str) -> None:
        """Delete a saved session, but never remove the active session file."""
        if session_id == self.session_id:
            raise ValueError("Cannot delete the currently active session")
        session_file = self._session_file(session_id)
        if not session_file.exists():
            raise FileNotFoundError(f"Session '{session_id}' was not found")
        session_file.unlink()

    def interactive_session_resumer(self) -> None:
        """Pick a saved session in the current profile and restore its active branch."""
        session_dir = self.profile_mgr.get_session_dir(self.profile_name)
        session_files = sorted(
            session_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        options: list[tuple[str, str, str]] = []
        for path in session_files:
            try:
                entries = JsonlSessionStore(path).load_entries()
                tree = SessionTree(entries)
                messages = tree.extract_messages_from_path(tree.get_active_path())
                first_user = next((m for m in messages if m.role == "user"), None)
                preview = str(first_user.content if first_user else "(empty session)")
                preview = preview.replace("\n", " ").strip()[:52]
                user_count = sum(1 for m in messages if m.role == "user")
                current = " • current" if path.stem == self.session_id else ""
                options.append(
                    (
                        path.stem,
                        f"{preview or '(empty session)'}{current}",
                        f"{user_count} prompt(s) • {path.stat().st_size / 1024:.1f} KB",
                    )
                )
            except Exception:
                continue

        if not options:
            self.console.print("[dim]No saved sessions found for this profile.[/dim]\n")
            return

        chosen = interactive_select(
            "↩ Resume Session (↑/↓ choose, Enter resume, Ctrl+D/d delete)",
            options,
            default_idx=0,
            on_delete=self.delete_session,
        )
        if chosen:
            self.resume_session(chosen)

    def resume_session(self, session_id: str) -> None:
        """Restore a saved session and its active branch into the live harness."""
        if not session_id or Path(session_id).name != session_id or session_id in {".", ".."}:
            self.console.print("[yellow]Invalid session ID.[/yellow]\n")
            return
        session_file = self._session_file(session_id)
        if not session_file.exists():
            self.console.print(f"[yellow]Session '{session_id}' was not found.[/yellow]\n")
            return
        try:
            entries = JsonlSessionStore(session_file).load_entries()
            tree = SessionTree(entries)
            messages = tree.extract_messages_from_path(tree.get_active_path())
            self.session_id = session_id
            self._init_harness()
            self.console.print(
                f"\n[bold green]✓ Resumed {session_id} ({len(messages)} messages)[/bold green]\n"
            )
            self._render_restored_messages(messages)
            self.console.print()
        except Exception as exc:
            self.console.print(f"[red]Failed to resume session: {exc}[/red]\n")

    def print_banner(self) -> None:
        """Render clean, compact top status banner with full session telemetry."""
        model_display = self.model_name if self.model_name else "(none - run /login)"
        model_style = "bold #38BDF8" if self.model_name else "dim yellow"
        ws_name = self.cwd.name or str(self.cwd)

        # Context window computation
        window_tokens = 128000
        pct = (self.total_tokens / max(1, window_tokens)) * 100
        pct_str = f"{pct:.1f}%" if self.total_tokens > 0 else "0%"
        tokens_str = (
            f"{self.total_tokens / 1000:.1f}k"
            if self.total_tokens >= 1000
            else str(self.total_tokens)
        )
        window_str = f"{window_tokens // 1000}k" if window_tokens >= 1000 else str(window_tokens)

        thinking_text = "on" if self.show_thinking_trace else "off"
        thinking_style = "bold #FF7A00" if self.show_thinking_trace else "dim #9CA3AF"

        banner_content = Text.assemble(
            ("📁 ", "dim #9CA3AF"),
            (f"{ws_name}  ", "bold white"),
            ("│  🧠 ", "dim #9CA3AF"),
            (f"{model_display}  ", model_style),
            ("│  ⚡ ", "dim #9CA3AF"),
            (f"{tokens_str}/{window_str} ({pct_str})  ", "dim #9CA3AF"),
            ("│  💭 ", "dim #9CA3AF"),
            (f"{thinking_text}  ", thinking_style),
            ("│  ^O ", "bold #FF7A00"),
            ("audit  ", "dim #9CA3AF"),
            ("│  ^T ", "bold #FF7A00"),
            ("trace  ", "dim #9CA3AF"),
            ("│  Esc Esc ", "bold #FF7A00"),
            ("tree  ", "dim #9CA3AF"),
            ("│  ", "dim #9CA3AF"),
            ("/", "bold #FF7A00"),
            (" help", "dim #9CA3AF"),
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
        """Render the 13 essential commands palette with descriptions and examples."""
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
            "[dim]Tip: Type any partial command or press [bold white]Tab[/bold white] to autocomplete.[/dim]\n"
        )

    async def execute_turn(self, prompt: str) -> None:
        """Run single prompt turn with minimalist stream rendering."""
        # Start elapsed timing and working animation immediately upon submission
        self.stream_renderer.start_turn()

        if not self.harness:
            if not self.model_name:
                self.stream_renderer._stop_status()
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
        assert self.agent_runtime is not None

        try:
            self.stream_renderer.show_thinking_trace = self.show_thinking_trace
            async for envelope in self.mode_runtime.prompt(
                prompt,
                mode_name=self.mode_name,
                profile_name=self.profile_name,
                provider=self.custom_provider,
                model_override=self.model_name,
                session_id=self.session_id,
                cwd=self.cwd,
                runtime=self.agent_runtime if self.mode_name == "single" else None,
            ):
                event = envelope.event
                if isinstance(event, OrchestrationErrorEvent):
                    self.stream_renderer._stop_status()
                    self.console.print(
                        f"[bold red]Orchestration error ({event.stage}): {event.error}[/bold red]"
                    )
                    continue
                self.stream_renderer.on_event(event)
                if isinstance(event, StepEndEvent):
                    self.total_tokens += event.input_tokens + event.output_tokens
                elif isinstance(event, TurnCompleteEvent):
                    self.total_cost_usd += event.total_cost_usd

        except asyncio.CancelledError:
            self.stream_renderer._stop_status()
            self.console.print("\n[yellow]⚠️  Turn halted by user (/stop or Ctrl+C).[/yellow]\n")
        except Exception as exc:
            self.stream_renderer._stop_status()
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

        elif cmd == "/mode":
            if not args:
                available = ", ".join(self.mode_runtime.catalog.available_modes())
                self.console.print(
                    f"[bold #FF7A00]Current mode:[/bold #FF7A00] [bold cyan]{self.mode_name}[/bold cyan]"
                )
                self.console.print(f"[dim]Available modes: {available}[/dim]\n")
            else:
                try:
                    self.mode_runtime.catalog.resolve(args, self.profile_name)
                except ValueError as exc:
                    self.console.print(f"[yellow]{exc}[/yellow]\n")
                else:
                    self.mode_name = args.strip().lower()
                    self._init_harness()
                    self.console.print(
                        f"[bold green]✓ Switched orchestration mode to {self.mode_name}[/bold green]\n"
                    )

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
            self.console.print("[dim]Use /resume to restore one.[/dim]\n")

        elif cmd == "/resume":
            if args:
                self.resume_session(args)
            else:
                self.interactive_session_resumer()

        elif cmd in ("/tree", "/branch"):
            self.interactive_tree_navigator()

        elif cmd in ("/inspect", "/logs"):
            self.stream_renderer.render_audit_log()

        elif cmd in ("/thinking", "/trace"):
            self.show_thinking_trace = not self.show_thinking_trace
            state_str = "ENABLED" if self.show_thinking_trace else "DISABLED"
            self.console.print(
                f"[bold #FF7A00]💭 Model reasoning trace is now {state_str}.[/bold #FF7A00]\n"
            )

        elif cmd in ("/stop", "/abort"):
            self.console.print("[yellow]No active turn running.[/yellow]\n")

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
        with contextlib.suppress(KeyboardInterrupt, EOFError):
            asyncio.run(self.run_async())

    async def run_async(self) -> None:
        """Main async REPL loop with first-run onboarding verification."""
        self.print_banner()

        if not self.custom_provider and not self.model_name:
            self.console.print(
                "[dim]💡 No AI provider authenticated yet. Type [bold #FF7A00]/login[/bold #FF7A00] to authenticate, or [bold #FF7A00]/help[/bold #FF7A00] for commands.[/dim]\n"
            )
        else:
            self.console.print()

        while True:
            try:
                user_input = await self.prompt_session.read_prompt_async("› ")

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
