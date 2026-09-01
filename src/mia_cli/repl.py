"""Production-grade Stream-First interactive CLI pair-programming REPL for Mia with prompt_toolkit & Pi/Tau inspection."""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mia_agent.agents import AgentManager
from mia_agent.auth.config import (
    ENV_API_KEY_MAP,
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
from mia_middleware.access import ApprovalRequest
from mia_agent.session.entries import LeafEntry, MessageEntry, SessionInfoEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.base import LLMProvider
from mia_cli.interactive_input import (
    COMMAND_HINTS,
    LivePromptSession,
    interactive_multi_select,
    interactive_select,
)
from mia_cli.renderers.rich_stream import RichStreamRenderer

SLASH_COMMANDS = [command for command, _ in COMMAND_HINTS]
COMMAND_DESCRIPTIONS: dict[str, str] = dict(COMMAND_HINTS)

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
        agent: str | None = None,
        agent_manager: AgentManager | None = None,
        cwd: Path | None = None,
        custom_provider: LLMProvider | None = None,
        session_id: str | None = None,
    ) -> None:
        self.console = Console()
        self.cwd = cwd or Path.cwd()
        self.config_mgr = ConfigManager()
        self.cred_store = FileCredentialStore()
        self.profile_mgr = ProfileManager()
        self.agent_mgr = agent_manager or AgentManager(profile_manager=self.profile_mgr)
        self.profile_name = profile
        self.agent_id = agent or profile
        self._canonical_agent = agent is not None
        self.custom_provider = custom_provider
        self.mode_name = "single"
        self.runtime_factory = AgentRuntimeFactory(
            agent_manager=self.agent_mgr,
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
        self.available_model_sources: dict[str, str] = {}
        self.scoped_models: list[str] = list(self.config_mgr.config.scoped_models)
        if session_id and (Path(session_id).name != session_id or session_id in {".", ".."}):
            raise ValueError("Invalid session ID")
        self.session_id = session_id or f"session_{os.urandom(4).hex()}"
        self.agent_runtime: AgentRuntime | None = None
        self.harness: AgentHarness | None = None
        self.total_cost_usd = 0.0
        self.total_tokens = 0
        self.show_thinking_trace = False
        self._approval_callback = self._request_tool_approval if self._canonical_agent else None

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
        """Instantiate the active Agent or legacy Profile through one factory."""
        self.agent_runtime = None
        if not self.custom_provider and not self.model_name:
            self.harness = None
            return

        if self._canonical_agent:
            agent = self.agent_mgr.get_agent(self.agent_id)
            configured_model = agent.model
            if not self.model_name and not configured_model and not self.custom_provider:
                self.harness = None
                return
            identity = RuntimeIdentity(
                run_id=f"run_{uuid.uuid4().hex}",
                task_id="root",
                agent_id=agent.agent_id,
                session_id=self.session_id,
            )
        else:
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
            approval_callback=self._approval_callback,
        )
        self.harness = self.agent_runtime.harness

    def _request_tool_approval(self, request: ApprovalRequest) -> bool:
        """Ask the interactive frontend for one sanitized side-effect decision."""
        self.console.print(
            f"[yellow]Approve {request.effect} Tool [bold]{request.tool_name}[/bold] "
            f"for Agent {request.agent_id or self.agent_id}?[/yellow]"
        )
        try:
            return input("Approve? [y/N] ").strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

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
        updated_cfg = current_cfg.model_copy(
            update={
                "default_provider": provider_id,
                "default_model": self.model_name or "",
                "base_urls": {**current_cfg.base_urls, provider_id: base_url},
            }
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

    def _provider_api_key(self, provider_id: str) -> str | None:
        stored = self.cred_store.get_api_key(provider_id)
        if stored:
            return stored
        env_names = ENV_API_KEY_MAP.get(provider_id, [f"{provider_id.upper()}_API_KEY"])
        return next((os.environ[name] for name in env_names if os.environ.get(name)), None)

    def _connected_providers(self) -> list[str]:
        connected = self.cred_store.list_stored_providers()
        for provider in (entry["id"] for entry in PROVIDER_CATALOG.values()):
            if provider not in connected and self._provider_api_key(provider):
                connected.append(provider)
        config = self.config_mgr.config
        if (
            config.default_provider == "custom"
            and "custom" not in connected
            and config.base_urls.get("custom")
        ):
            connected.append("custom")
        return connected

    def _save_model_selection(self, provider_id: str, model: str) -> None:
        self.config_mgr.save_config(
            self.config_mgr.config.model_copy(
                update={"default_provider": provider_id, "default_model": model}
            )
        )

    def _save_scoped_models(self) -> None:
        self.config_mgr.save_config(
            self.config_mgr.config.model_copy(update={"scoped_models": list(self.scoped_models)})
        )

    def _model_label(self, model_id: str) -> str:
        provider, model = model_id.split("::", 1)
        return f"{provider}: {model}"

    def _discover_connected_models(self) -> dict[str, str]:
        """Discover models from connected providers for the scoped-model list."""
        providers = self._connected_providers()
        if not providers:
            self.available_model_sources = {}
            self.scoped_models = []
            return {}

        sources: dict[str, str] = {}
        config = self.config_mgr.config
        for provider in providers:
            models = discover_provider_models(
                provider,
                api_key=self._provider_api_key(provider),
                base_url=config.base_urls.get(provider),
            )
            if (
                provider == config.default_provider
                and self.model_name
                and self.model_name not in models
            ):
                models = [self.model_name, *models]
            for model in models:
                sources[f"{provider}::{model}"] = provider

        self.available_model_sources = sources
        self.scoped_models = [model_id for model_id in self.scoped_models if model_id in sources]
        return sources

    def cycle_scoped_model(self) -> None:
        """Select the next scoped model, wrapping at the end."""
        if not self.scoped_models:
            self.console.print(
                "[yellow]No scoped models. Run /scoped-models to discover connected models.[/yellow]\n"
            )
            return
        active_id = f"{self.config_mgr.config.default_provider}::{self.model_name}"
        current = self.scoped_models.index(active_id) if active_id in self.scoped_models else -1
        selected_id = self.scoped_models[(current + 1) % len(self.scoped_models)]
        provider_id = self.available_model_sources[selected_id]
        self.model_name = selected_id.split("::", 1)[1]
        self._save_model_selection(provider_id, self.model_name)
        self._init_harness()
        self.console.print(f"[bold green]✓ Switched model to {self.model_name}[/bold green]\n")

    def interactive_model_picker(self) -> None:
        """Select the active model from the discovered scoped-model list."""
        if not self.scoped_models:
            self.console.print(
                "[yellow]No scoped models. Run /scoped-models to discover connected models first.[/yellow]\n"
            )
            return

        model_options: list[tuple[str, str, str]] = []
        default_idx = 0
        config = self.config_mgr.config
        for model_id in self.scoped_models:
            provider_id = self.available_model_sources.get(model_id)
            if not provider_id:
                continue
            model = model_id.split("::", 1)[1]
            is_active = provider_id == config.default_provider and model == self.model_name
            if is_active:
                default_idx = len(model_options)
            label = self._model_label(model_id) + (" (Active)" if is_active else "")
            model_options.append((model_id, label, ""))

        if not model_options:
            self.console.print(
                "[yellow]No scoped models. Run /scoped-models to refresh the list.[/yellow]\n"
            )
            return

        selected = interactive_select(
            "🤖 Switch Active Model", model_options, default_idx=default_idx
        )
        if not selected:
            return

        provider_id = self.available_model_sources[selected]
        self.model_name = selected.split("::", 1)[1]
        self._save_model_selection(provider_id, self.model_name)
        self._init_harness()
        self.console.print(f"[bold green]✓ Switched model to {self.model_name}[/bold green]\n")

    def _session_file(self, session_id: str | None = None) -> Path:
        """Return the JSONL path for the active Agent and Session."""
        active_id = session_id or self.session_id
        if self._canonical_agent:
            return self.agent_mgr.get_session_path(self.agent_id, active_id)
        prof = self.profile_mgr.get_profile(self.profile_name)
        return self.profile_mgr.get_session_dir(prof.name) / f"{active_id}.jsonl"

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

    def _print_session_resume_hint(self) -> None:
        self.console.print(f"[dim]Session ID: {escape(self.session_id)}[/dim]")
        self.console.print(f"[dim]Resume with: mia --session {escape(self.session_id)}[/dim]\n")

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
        """Render canonical commands with descriptions and aliases."""
        table = Table(
            title=f"🥕 Mia {len(SLASH_COMMANDS)} Canonical Slash Commands",
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
            if self._canonical_agent:
                async for event in self.harness.prompt(prompt):
                    self.stream_renderer.on_event(event)
                    if isinstance(event, StepEndEvent):
                        self.total_tokens += event.input_tokens + event.output_tokens
                    elif isinstance(event, TurnCompleteEvent):
                        self.total_cost_usd += event.total_cost_usd
            else:
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
            self.console.print("\n[yellow]⚠️  Turn halted by user (Ctrl+C).[/yellow]\n")
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
            self._print_session_resume_hint()
            return False

        elif cmd in ("/clear", "/cls"):
            self.console.clear()
            self.print_banner()

        elif cmd in ("/agent", "/profile"):
            legacy = cmd == "/profile"
            if not args:
                active = self.agent_mgr.get_agent(self.agent_id)
                available = ", ".join(agent.agent_id for agent in self.agent_mgr.list_agents())
                label = "profile" if legacy else "Agent"
                self.console.print(
                    f"[bold #FF7A00]Current {label}:[/bold #FF7A00] "
                    f"[bold cyan]{active.display_name} ({active.agent_id})[/bold cyan]"
                )
                self.console.print(f"[dim]Available Agents: {available}[/dim]\n")
            else:
                try:
                    selected = self.agent_mgr.get_agent(args)
                except ValueError as exc:
                    if legacy:
                        available = ", ".join(
                            profile.name for profile in self.profile_mgr.list_profiles()
                        )
                        self.console.print(
                            f"[yellow]Profile '{args}' not found. "
                            f"Available profiles: {available}[/yellow]\n"
                        )
                    else:
                        self.console.print(f"[yellow]{exc}[/yellow]\n")
                else:
                    self.agent_id = selected.agent_id
                    self.profile_name = selected.agent_id
                    self._canonical_agent = not legacy
                    self._approval_callback = (
                        self._request_tool_approval if self._canonical_agent else None
                    )
                    self._init_harness()
                    noun = "Agent" if self._canonical_agent else "profile"
                    self.console.print(
                        f"[bold green]✓ Switched {noun} to {selected.agent_id}[/bold green]\n"
                    )

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
            elif args.lower() == "next":
                self.cycle_scoped_model()
            else:
                self.model_name = args
                self._init_harness()
                self.console.print(
                    f"[bold green]✓ Switched active model to {self.model_name}[/bold green]\n"
                )

        elif cmd == "/scoped-models":
            model_sources = self._discover_connected_models()
            previous_scope = list(self.scoped_models)
            if not model_sources:
                self.console.print(
                    "[yellow]No connected providers or discoverable models.[/yellow]\n"
                )
                return True

            if args.lower() == "all" or not self.scoped_models:
                self.scoped_models = list(model_sources)
            elif args:
                requested = [model.strip() for model in args.split(",") if model.strip()]
                aliases = {
                    self._model_label(model_id).lower(): model_id for model_id in model_sources
                }
                requested = [aliases.get(model.lower(), model) for model in requested]
                unknown = [model for model in requested if model not in model_sources]
                if unknown:
                    self.console.print(
                        f"[yellow]Unknown models: {', '.join(unknown)}. Run /scoped-models to refresh.[/yellow]\n"
                    )
                    return True
                self.scoped_models = requested

            options = [(model_id, self._model_label(model_id), "") for model_id in model_sources]
            selected = interactive_multi_select(
                "Select models for Ctrl+P",
                options,
                selected_ids=self.scoped_models,
            )
            if selected is None or not selected:
                self.scoped_models = previous_scope
                self.console.print("[dim]Scope unchanged.[/dim]\n")
            else:
                self.scoped_models = selected
                self._save_scoped_models()
                self.console.print(
                    f"[bold green]✓ Saved {len(selected)} scoped models.[/bold green]\n"
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
                if res.returncode != 0:
                    error = res.stderr.strip() or f"git diff exited with status {res.returncode}"
                    self.console.print(f"[red]Git diff failed: {escape(error)}[/red]\n")
                else:
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
            if self.harness is None:
                self.console.print(
                    "[yellow]No active context to compact; configure a model first.[/yellow]\n"
                )
            else:
                result = self.harness.compact_context()
                if result is None:
                    self.console.print(
                        "[yellow]Nothing to compact: no conversation history or compactor is configured.[/yellow]\n"
                    )
                else:
                    self.console.print(
                        "[bold green]✓ Context compacted: "
                        f"{result.before_tokens:,} → {result.after_tokens:,} estimated tokens.[/bold green]\n"
                    )

        elif cmd in ("/sessions", "/history"):
            session_dir = (
                self.agent_mgr.get_session_dir(self.agent_id)
                if self._canonical_agent
                else self.profile_mgr.get_session_dir(self.profile_name)
            )
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
                    title="[bold #FF7A00]Basic Repository Context[/bold #FF7A00]",
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
                self._print_session_resume_hint()
                break
