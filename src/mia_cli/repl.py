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
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from mia_agent.agent_runner import AgentRunner
from mia_agent.agents import AgentManager
from mia_agent.auth.config import (
    ConfigManager,
    MiaConfig,
    discover_provider_models,
    validate_api_key,
)
from mia_agent.auth.openai_auth import OpenAIOAuthManager
from mia_agent.events import StepEndEvent, TurnCompleteEvent
from mia_agent.harness import AgentHarness
from mia_agent.runtime_events import PluginDiagnosticEvent, RunErrorEvent
from mia_agent.runtime_models import AgentRuntime, RunRequest
from mia_agent.session.compactor import estimate_chat_messages_tokens
from mia_agent.session.entries import LeafEntry, MessageEntry, SessionInfoEntry
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.base import LLMProvider
from mia_cli.interactive_input import (
    COMMAND_HINTS,
    LivePromptSession,
    format_status_toolbar,
    interactive_multi_select,
    interactive_select,
)
from mia_cli.renderers.rich_stream import RichStreamRenderer
from mia_middleware.access import ApprovalRequest

SLASH_COMMANDS = [command for command, _ in COMMAND_HINTS]
COMMAND_DESCRIPTIONS: dict[str, str] = dict(COMMAND_HINTS)
_MAX_CLI_DISPLAY_CHARS = 4000


def _safe_cli_text(value: object) -> str:
    """Bound dynamic CLI text and remove terminal escape/control delimiters."""
    text = str(value).replace("\x1b", "").replace("\r", "")
    if len(text) <= _MAX_CLI_DISPLAY_CHARS:
        return text
    return text[: _MAX_CLI_DISPLAY_CHARS - 1] + "…"


COMMAND_ALIASES: dict[str, str] = {
    "/?": "/help",
    "/auth": "/login",
    "/signout": "/logout",
    "/disconnect": "/logout",
    "/llm": "/model",
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

COMMAND_AVAILABILITY: dict[str, str] = {
    "/help": "Always",
    "/login": "Idle only",
    "/logout": "Idle only",
    "/model": "Idle only",
    "/scoped-models": "Idle only",
    "/agent": "Idle only",
    "/queue": "Busy only",
    "/diff": "Always",
    "/cost": "Always",
    "/compact": "Idle only",
    "/sessions": "Always",
    "/resume": "Idle only",
    "/tree": "Idle only",
    "/inspect": "Always",
    "/thinking": "Always",
    "/init": "Always",
    "/clear": "Always",
    "/quit": "Always",
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
    "8": {
        "id": "openai-codex",
        "name": "OpenAI Codex subscription (OAuth)",
        "base_url": "https://chatgpt.com/backend-api",
        "models": [
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.3-codex-spark",
            "gpt-5.2",
        ],
    },
}


class MiaREPL:
    """Stream-first interactive coding agent harness with prompt_toolkit & Pi/Tau inspection."""

    def __init__(
        self,
        *,
        model: str | None = None,
        agent: str | None = None,
        agent_manager: AgentManager | None = None,
        cwd: Path | None = None,
        custom_provider: LLMProvider | None = None,
        session_id: str | None = None,
        prompt_input: Any = None,
        prompt_output: Any = None,
    ) -> None:
        self.console = Console()
        self.cwd = cwd or Path.cwd()
        self.config_mgr = ConfigManager()
        self.cred_store = self.config_mgr.credential_store
        self.agent_mgr = agent_manager or AgentManager()
        self.agent_id = agent or self.agent_mgr.default_agent().agent_id
        self.custom_provider = custom_provider
        self.agent_runner = AgentRunner(
            agent_manager=self.agent_mgr,
            config_manager=self.config_mgr,
        )

        # Never assume a model unless explicitly authenticated or provided
        initial_model = model or (
            None if custom_provider else self.config_mgr.config.default_model or None
        )
        if initial_model and not custom_provider:
            inferred_prov = self.config_mgr.infer_provider(initial_model)
            has_key = self.cred_store.get_api_key(inferred_prov) or self.cred_store.get_oauth(
                inferred_prov
            )
            if not has_key:
                initial_model = None

        self.model_name: str | None = initial_model
        self.available_model_sources: dict[str, str] = {}
        self._model_sources_refreshed = False
        self.scoped_models: list[str] = list(self.config_mgr.config.scoped_models)
        if session_id and (Path(session_id).name != session_id or session_id in {".", ".."}):
            raise ValueError("Invalid session ID")
        self.session_id = session_id or f"session_{os.urandom(4).hex()}"
        self.agent_runtime: AgentRuntime | None = None
        self.harness: AgentHarness | None = None
        self.total_cost_usd = 0.0
        self.total_tokens = 0
        self.show_thinking_trace = False
        self._run_state = "idle"
        self._approval_callback = self._request_tool_approval
        self._active_prompt_task: asyncio.Task[str] | None = None
        self._active_turn_task: asyncio.Task[None] | None = None
        self.queued_follow_up: str | None = None

        self.stream_renderer = RichStreamRenderer(
            console=self.console, show_thinking_trace=self.show_thinking_trace
        )
        self._history_file = Path.home() / ".mia" / "history"

        # Initialize prompt_toolkit session with floating slash completions and status toolbar
        self.prompt_session = LivePromptSession(
            history_file=self._history_file,
            toolbar_callback=self._get_status_toolbar,
            input=prompt_input,
            output=prompt_output,
        )
        self.prompt_session.on_queue_callback = self.queue_follow_up
        self._init_harness()

    def _get_status_toolbar(self) -> Any:
        """Construct truthful status toolbar data matching active runtime state."""
        window_tokens = None
        if self.agent_runtime and self.agent_runtime.effective_settings:
            window_tokens = self.agent_runtime.effective_settings.context_window
        provider_name = (
            "custom" if self.custom_provider else self.config_mgr.config.default_provider
        )
        if not provider_name and self.model_name:
            provider_name = self.config_mgr.infer_provider(self.model_name)
        current_context_tokens = (
            estimate_chat_messages_tokens(self.harness.messages) if self.harness else None
        )
        return format_status_toolbar(
            workspace_name=self.cwd.name or str(self.cwd),
            model_name=self.model_name or "none",
            provider_name=provider_name or None,
            tokens=self.total_tokens,
            window_tokens=window_tokens,
            thinking_enabled=self.show_thinking_trace,
            agent_id=self.agent_id,
            session_id=self.session_id,
            current_context_tokens=current_context_tokens,
            run_state=self.stream_renderer.phase,
            width=self.console.width,
        )

    def _init_harness(self) -> None:
        """Instantiate the selected Agent through the canonical runtime factory."""
        self.agent_runtime = None
        if not self.custom_provider and not self.model_name:
            self.harness = None
            return

        agent = self.agent_mgr.get_agent(self.agent_id)
        if not self.model_name and not agent.model and not self.custom_provider:
            self.harness = None
            return
        self.agent_runtime = self.agent_runner.prepare_runtime(
            agent_id=agent.agent_id,
            provider=self.custom_provider,
            model_override=self.model_name,
            session_id=self.session_id,
            cwd=self.cwd,
            approval_callback=self._approval_callback,
        )
        self.harness = self.agent_runtime.harness

    def _print_approval_request(self, request: ApprovalRequest) -> None:
        """Render only the sanitized, attributable approval summary."""
        tool_name = _safe_cli_text(request.tool_name)
        agent_id = _safe_cli_text(request.agent_id or self.agent_id)
        self.console.print(
            f"[approval-required] Approve {request.effect} Tool {tool_name} for Agent {agent_id}?",
            markup=False,
        )

    async def _request_tool_approval(self, request: ApprovalRequest) -> bool:
        """Read approval through a separate prompt-toolkit buffer and fail closed on every error."""
        saved_draft = self.prompt_session.get_draft()
        self.prompt_session.approval_active = True
        self.stream_renderer.set_tool_approval(request.tool_name)
        self._run_state = "approval"
        app = getattr(self.prompt_session.session, "app", None)
        if app and getattr(app, "is_running", False):
            app.exit(result="")
        self._print_approval_request(request)
        try:
            answer = await self.prompt_session.read_approval_async()
            return answer.strip().lower() in {"y", "yes"}
        except (asyncio.CancelledError, EOFError, KeyboardInterrupt, OSError):
            return False
        except Exception:
            return False
        finally:
            self.prompt_session.restore_draft(saved_draft)
            self.prompt_session.approval_active = False
            if self.stream_renderer.phase == "approval":
                self.stream_renderer.phase = "tool"
            self._run_state = self.stream_renderer.phase

    def interactive_login(self, provider_hint: str | None = None) -> None:
        """Step 1: Choose Authentication Method (API Key or OpenAI Auth)."""
        if provider_hint:
            clean_hint = provider_hint.strip().lower()
            is_oauth = clean_hint in {"oauth", "openai-codex"}
            selected_provider = "openai-codex" if clean_hint == "oauth" else clean_hint
            preset = next(
                (
                    p
                    for p in PROVIDER_CATALOG.values()
                    if selected_provider in (p["id"], p["id"].split("-")[0])
                ),
                None,
            )
            base_url = preset["base_url"] if preset else "https://opencode.ai/zen/go/v1"
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
                selected_provider = "openai-codex"
                preset = next(
                    (p for p in PROVIDER_CATALOG.values() if p["id"] == "openai-codex"), None
                )
                base_url = preset["base_url"] if preset else "https://chatgpt.com/backend-api"
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
                prompt_str = "Enter OpenAI Codex access token (or press Enter to open browser): "
                manual_token = input(prompt_str).strip()
                if manual_token:
                    ok, msg = oauth_mgr.save_codex_access_token(manual_token)
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
        self._refresh_provider_catalog(provider_id)
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
        return self.cred_store.get_api_key(provider_id)

    def _provider_is_connected(self, provider_id: str) -> bool:
        if self._provider_api_key(provider_id):
            return True
        oauth = self.cred_store.get_oauth(provider_id)
        return bool(oauth and (oauth.access or oauth.refresh))

    def _connected_providers(self) -> list[str]:
        known = {entry["id"] for entry in PROVIDER_CATALOG.values()}
        connected = [
            provider
            for provider in self.cred_store.list_stored_providers()
            if provider in known and self._provider_is_connected(provider)
        ]
        for provider in (entry["id"] for entry in PROVIDER_CATALOG.values()):
            if provider not in connected and self._provider_is_connected(provider):
                connected.append(provider)
        config = self.config_mgr.config
        if (
            config.default_provider == "custom"
            and config.base_urls.get("custom")
            and "custom" not in connected
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

    def _prune_disconnected_scope(self) -> None:
        """Hide and persist providers that were disconnected after the last refresh."""
        if not self._model_sources_refreshed:
            return
        connected = set(self._connected_providers())
        sources = {
            model_id: provider
            for model_id, provider in self.available_model_sources.items()
            if provider in connected
        }
        scope = [model_id for model_id in self.scoped_models if model_id in sources]
        if sources != self.available_model_sources or scope != self.scoped_models:
            self.available_model_sources = sources
            self.scoped_models = scope
            self._save_scoped_models()

    def _load_persisted_model_sources(self) -> dict[str, str]:
        """Load connected models from the local catalog without probing providers."""
        previous_scope = list(self.scoped_models)
        providers = self._connected_providers()
        catalog = self.config_mgr.config.model_catalog
        sources = {
            f"{provider}::{model}": provider
            for provider in providers
            for model in catalog.get(provider, [])
        }
        self._model_sources_refreshed = True
        self.available_model_sources = sources
        self.scoped_models = [model_id for model_id in self.scoped_models if model_id in sources]
        if self.scoped_models != previous_scope:
            self._save_scoped_models()
        return sources

    def _refresh_provider_catalog(self, provider_id: str) -> list[str]:
        """Fetch one connected provider's models and persist them under ~/.mia."""
        config = self.config_mgr.config
        oauth = self.cred_store.get_oauth(provider_id)
        models = discover_provider_models(
            provider_id,
            api_key=self._provider_api_key(provider_id),
            base_url=config.base_urls.get(provider_id),
            oauth_access_token=oauth.access if oauth else None,
            account_id=oauth.account_id if oauth else None,
        )
        catalog = {**config.model_catalog, provider_id: list(dict.fromkeys(models))}
        self.config_mgr.save_config(config.model_copy(update={"model_catalog": catalog}))
        return catalog[provider_id]

    def _discover_connected_models(self) -> dict[str, str]:
        """Load stored catalogs and reconcile them with connected providers."""
        previous_scope = list(self.scoped_models)
        providers = self._connected_providers()
        config = self.config_mgr.config
        if not providers:
            self._model_sources_refreshed = True
            self.available_model_sources = {}
            self.scoped_models = []
            if previous_scope:
                self._save_scoped_models()
            return {}

        sources: dict[str, str] = {}
        catalog = dict(config.model_catalog)
        for provider in providers:
            if provider not in catalog:
                catalog[provider] = self._refresh_provider_catalog(provider)
            models = list(catalog.get(provider, []))
            catalog[provider] = list(dict.fromkeys(models))
            for model in models:
                sources[f"{provider}::{model}"] = provider

        if catalog != config.model_catalog:
            self.config_mgr.save_config(config.model_copy(update={"model_catalog": catalog}))
        self._model_sources_refreshed = True
        self.available_model_sources = sources
        self.scoped_models = [model_id for model_id in self.scoped_models if model_id in sources]
        if self.scoped_models != previous_scope:
            self._save_scoped_models()
        return sources

    def cycle_scoped_model(self) -> None:
        """Select the next scoped model, wrapping at the end."""
        self._prune_disconnected_scope()
        if not self.scoped_models:
            self.console.print(
                "[yellow]No scoped models. Run /scoped-models to discover connected models.[/yellow]\n"
            )
            return
        if not self.available_model_sources or any(
            model_id not in self.available_model_sources for model_id in self.scoped_models
        ):
            self._discover_connected_models()
        if not self.scoped_models:
            self.console.print("[yellow]No connected scoped models remain.[/yellow]\n")
            return
        active_id = f"{self.config_mgr.config.default_provider}::{self.model_name}"
        current = self.scoped_models.index(active_id) if active_id in self.scoped_models else -1
        selected_id = self.scoped_models[(current + 1) % len(self.scoped_models)]
        provider_id = self.available_model_sources[selected_id]
        self.model_name = selected_id.split("::", 1)[1]
        self._save_model_selection(provider_id, self.model_name)
        self._init_harness()
        self.console.print(f"[bold green]✓ Switched model to {self.model_name}[/bold green]\n")

    def interactive_agent_picker(self) -> None:
        """Select an Agent from the local searchable Agent list without network activity."""
        saved_draft = self.prompt_session.get_draft()
        try:
            agents = self.agent_mgr.list_agents()
            options = [
                (agent.agent_id, agent.display_name, f"Agent {agent.agent_id}") for agent in agents
            ]
            default_idx = next(
                (index for index, option in enumerate(options) if option[0] == self.agent_id),
                0,
            )
            selected = interactive_select("🤖 Switch Agent", options, default_idx=default_idx)
            if not selected or selected == self.agent_id:
                return
            agent = self.agent_mgr.get_agent(selected)
            self.agent_id = agent.agent_id
            self._approval_callback = self._request_tool_approval
            self._init_harness()
            self.console.print(f"[bold green]✓ Switched Agent to {agent.agent_id}[/bold green]\n")
        finally:
            self.prompt_session.restore_draft(saved_draft)

    def interactive_command_picker(self) -> None:
        """Select a canonical slash command from a local searchable list."""
        saved_draft = self.prompt_session.get_draft()
        try:
            options = [
                (command, command, description)
                for command, description in COMMAND_DESCRIPTIONS.items()
            ]
            selected = interactive_select("⌘ Command", options, default_idx=0)
            if selected:
                self.handle_slash_command(selected)
        finally:
            self.prompt_session.restore_draft(saved_draft)

    def interactive_model_picker(self) -> None:
        """Select the active model from the persisted scoped-model list."""
        saved_draft = self.prompt_session.get_draft()
        try:
            self._load_persisted_model_sources()
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
        finally:
            self.prompt_session.restore_draft(saved_draft)

    def _session_file(self, session_id: str | None = None) -> Path:
        """Return the JSONL path for the active Agent and Session."""
        active_id = session_id or self.session_id
        return self.agent_mgr.get_session_path(self.agent_id, active_id)

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
        saved_draft = self.prompt_session.get_draft()
        try:
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
        finally:
            self.prompt_session.restore_draft(saved_draft)

    def delete_session(self, session_id: str) -> None:
        """Delete a saved session, but never remove the active session file."""
        if session_id == self.session_id:
            raise ValueError("Cannot delete the currently active session")
        session_file = self._session_file(session_id)
        if not session_file.exists():
            raise FileNotFoundError(f"Session '{session_id}' was not found")
        session_file.unlink()

    def interactive_session_resumer(self) -> None:
        """Pick a saved Session for the current Agent and restore its active branch."""
        saved_draft = self.prompt_session.get_draft()
        try:
            session_dir = self.agent_mgr.get_session_dir(self.agent_id)
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
                self.console.print("[dim]No saved Sessions found for this Agent.[/dim]\n")
                return

            chosen = interactive_select(
                "↩ Resume Session (↑/↓ choose, Enter resume, Ctrl+D/d delete)",
                options,
                default_idx=0,
                on_delete=self.delete_session,
            )
            if chosen:
                self.resume_session(chosen)
        finally:
            self.prompt_session.restore_draft(saved_draft)

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

        # Context window computation (truthful, only if measured/configured)
        window_tokens = None
        if self.agent_runtime and self.agent_runtime.effective_settings:
            window_tokens = self.agent_runtime.effective_settings.context_window

        tokens_str = (
            f"{self.total_tokens / 1000:.1f}k"
            if self.total_tokens >= 1000
            else str(self.total_tokens)
        )
        if window_tokens is not None and window_tokens > 0:
            pct = (self.total_tokens / max(1, window_tokens)) * 100
            pct_str = f"{pct:.1f}%" if self.total_tokens > 0 else "0%"
            window_str = (
                f"{window_tokens // 1000}k" if window_tokens >= 1000 else str(window_tokens)
            )
            token_display = f"{tokens_str}/{window_str} ({pct_str})"
        else:
            token_display = f"{tokens_str}"

        run_state = getattr(self, "_run_state", "idle")
        if self.stream_renderer.plain_mode:
            self.console.print(
                f"[Mia v0.6.0] Workspace: {ws_name} | Agent: {self.agent_id} | Model: {model_display} | "
                f"Session: {self.session_id} | Tokens: {token_display} | State: [{run_state}]",
                markup=False,
            )
            return

        width = self.console.width
        if width and width <= 60:
            compact_text = Text.assemble(
                ("📁 ", "dim #9CA3AF"),
                (f"{ws_name} ", "bold white"),
                ("│ 🤖 ", "dim #9CA3AF"),
                (f"{self.agent_id} ", "bold cyan"),
                ("│ 🧠 ", "dim #9CA3AF"),
                (f"{model_display} ", model_style),
                ("│ ", "dim #9CA3AF"),
                (f"[{run_state}]", "bold #FF7A00"),
            )
            self.console.print(
                Panel(
                    compact_text,
                    title="[bold #FF7A00]🥕 Mia v0.6.0[/bold #FF7A00]",
                    border_style="#2D3342",
                    padding=(0, 1),
                )
            )
            return

        thinking_text = "on" if self.show_thinking_trace else "off"
        thinking_style = "bold #FF7A00" if self.show_thinking_trace else "dim #9CA3AF"

        banner_content = Text.assemble(
            ("📁 ", "dim #9CA3AF"),
            (f"{ws_name}  ", "bold white"),
            ("│  🤖 ", "dim #9CA3AF"),
            (f"{self.agent_id}  ", "bold cyan"),
            ("│  🧠 ", "dim #9CA3AF"),
            (f"{model_display}  ", model_style),
            ("│  🆔 ", "dim #9CA3AF"),
            (f"{self.session_id[:12]}  ", "dim #9CA3AF"),
            ("│  ⚡ ", "dim #9CA3AF"),
            (f"{token_display}  ", "dim #9CA3AF"),
            ("│  💭 ", "dim #9CA3AF"),
            (f"{thinking_text}  ", thinking_style),
            ("│  ", "dim #9CA3AF"),
            (f"[{run_state}]  ", "bold #FF7A00"),
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
                title="[bold #FF7A00]🥕 Mia v0.6.0[/bold #FF7A00]",
                border_style="#2D3342",
                padding=(0, 1),
            )
        )

    def print_command_menu(self, filter_prefix: str | None = None) -> None:
        """Render canonical commands with descriptions and aliases."""
        if not filter_prefix:
            actions_table = Table(
                title="Essential Actions & Keyboard Equivalents",
                border_style="#2D3342",
                show_header=True,
                header_style="bold #FF7A00",
            )
            actions_table.add_column("Action", style="white", width=26)
            actions_table.add_column("Key / Command Equivalent", style="bold #FF7A00")
            actions_table.add_column("Availability", style="dim cyan", width=14)
            actions_table.add_row("Submit prompt", "Enter", "Idle only")
            actions_table.add_row("Insert newline", "Ctrl+J / Alt+Enter", "Always")
            actions_table.add_row("Clear prompt / Cancel", "Ctrl+C / Esc", "Always")
            actions_table.add_row("Help & Discovery", "/help or /?", "Always")
            actions_table.add_row("Switch Agent", "/agent <id>", "Idle only")
            actions_table.add_row("Switch model", "Ctrl+L or /model", "Idle only")
            actions_table.add_row("Cycle scoped models", "Ctrl+P or /model next", "Idle only")
            actions_table.add_row("Queue one follow-up", "Ctrl+Q or /queue <text>", "Busy only")
            actions_table.add_row("Inspect audit details", "Ctrl+O or /inspect", "Always")
            actions_table.add_row("Session tree navigator", "Esc Esc or /tree", "Idle only")
            actions_table.add_row("Quit / Exit", "/quit or /exit", "Always")
            self.console.print(actions_table)
            self.console.print()

        table = Table(
            title=f"🥕 Mia {len(SLASH_COMMANDS)} Canonical Slash Commands",
            border_style="#2D3342",
            show_header=True,
            header_style="bold #FF7A00",
        )
        table.add_column("Command", style="bold #FF7A00", width=22)
        table.add_column("Usage & Description", style="white")
        table.add_column("Availability", style="dim cyan", width=14)

        for cmd, desc in COMMAND_DESCRIPTIONS.items():
            if not filter_prefix or cmd.startswith(filter_prefix):
                table.add_row(cmd, desc, COMMAND_AVAILABILITY.get(cmd, "Always"))

        self.console.print(table)
        self.console.print(
            "[dim]Tip: Type any partial command or press [bold white]Tab[/bold white] to autocomplete.[/dim]\n"
        )

    def queue_follow_up(self, prompt: str | None = None) -> bool:
        """Move one explicit follow-up into the single busy-run queue slot."""
        if not self.prompt_session.is_busy:
            self.console.print("[queue unavailable] A follow-up can only be queued during a Run.\n")
            return False
        if self.queued_follow_up is not None:
            self.console.print(
                "[queue occupied] A follow-up is already queued; cancel the Run to restore it.\n"
            )
            return False
        candidate = prompt if prompt is not None else self.prompt_session.get_draft()
        if prompt is None and candidate.strip().lower().startswith("/queue"):
            candidate = ""
        if not candidate or not candidate.strip():
            self.console.print("[queue empty] Add a follow-up draft before queueing.\n")
            return False
        self.queued_follow_up = candidate
        self.prompt_session.set_draft("")
        self.console.print("[queued] One follow-up will run after a successful settlement.\n")
        return True

    def _restore_queued_follow_up(self) -> None:
        """Restore an unsuccessful Run's queued follow-up exactly once."""
        if self.queued_follow_up is None:
            return
        queued = self.queued_follow_up
        self.queued_follow_up = None
        self.prompt_session.restore_draft(queued)
        self.console.print(
            "[queue restored] Follow-up returned to the draft after Run failure/cancel.\n"
        )

    def _take_queued_follow_up(self) -> str | None:
        queued = self.queued_follow_up
        self.queued_follow_up = None
        return queued

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
                    self.stream_renderer.phase = "cancelled"
                    self._run_state = "cancelled"
                    self.console.print(
                        "[yellow]Turn cancelled. Please configure a model with /login to start coding.[/yellow]\n"
                    )
                    return
            else:
                self._init_harness()

        assert self.harness is not None
        assert self.agent_runtime is not None

        self._run_state = "thinking"
        self.prompt_session.is_busy = True
        successful_settlement = False
        try:
            self.stream_renderer.show_thinking_trace = self.show_thinking_trace
            request = RunRequest(
                prompt_text=prompt,
                agent_id=self.agent_id,
                model_override=self.model_name,
                session_id=self.session_id,
                cwd=self.cwd,
            )
            async with contextlib.aclosing(
                self.agent_runner.run(
                    request,
                    provider=self.custom_provider,
                    approval_callback=self._approval_callback,
                )
            ) as stream:
                async for envelope in stream:
                    event = envelope.event
                    if isinstance(event, RunErrorEvent):
                        self.stream_renderer.on_event(event)
                        self._run_state = self.stream_renderer.phase
                        continue
                    if isinstance(event, PluginDiagnosticEvent):
                        continue
                    self.stream_renderer.on_event(event)
                    self._run_state = self.stream_renderer.phase
                    if isinstance(event, StepEndEvent):
                        self.total_tokens += event.input_tokens + event.output_tokens
                    elif isinstance(event, TurnCompleteEvent):
                        self.total_cost_usd += event.total_cost_usd
                        successful_settlement = self.stream_renderer.phase == "success"
            if successful_settlement:
                follow_up = self._take_queued_follow_up()
                if follow_up is not None:
                    await self.execute_turn(follow_up)
            else:
                self._restore_queued_follow_up()
            if self.agent_runner.last_runtime is not None:
                self.agent_runtime = self.agent_runner.last_runtime
                self.harness = self.agent_runtime.harness

        except asyncio.CancelledError:
            self.stream_renderer.phase = "cancelled"
            self._run_state = "cancelled"
            self._restore_queued_follow_up()
            self.stream_renderer._stop_status()
            if self.stream_renderer.plain_mode:
                self.console.print("[cancelled] Turn halted by user (Ctrl+C).", markup=False)
            else:
                self.console.print("\n[yellow]⚠️  Turn halted by user (Ctrl+C).[/yellow]\n")
        except Exception as exc:
            self.stream_renderer.phase = "failure"
            self._run_state = "failure"
            self._restore_queued_follow_up()
            self.stream_renderer._stop_status()
            safe_error = _safe_cli_text(exc)
            if self.stream_renderer.plain_mode:
                self.console.print(f"[error] Error during execution: {safe_error}", markup=False)
            else:
                self.console.print(
                    Text(f"\nError during execution: {safe_error}\n", style="bold red")
                )
        finally:
            self.prompt_session.is_busy = False
            self._run_state = "idle"

    def handle_slash_command(self, cmd_line: str) -> bool:
        """Handle slash commands with alias resolution and prefix matching."""
        clean = cmd_line.strip()
        parts = clean.split(" ", 1)
        raw_cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        cmd = COMMAND_ALIASES.get(raw_cmd, raw_cmd)

        if self.prompt_session.is_busy and cmd in (
            "/agent",
            "/model",
            "/llm",
            "/scoped-models",
            "/resume",
            "/compact",
            "/compress",
            "/tree",
            "/branch",
            "/login",
            "/auth",
            "/logout",
            "/signout",
            "/disconnect",
        ):
            self.console.print(f"[yellow]Cannot change {raw_cmd} while a Run is active.[/yellow]\n")
            return True

        if cmd in ("/", "/?", "/help"):
            if args.lower() in {"pick", "select", "search"}:
                self.interactive_command_picker()
            else:
                self.print_command_menu()
            return True

        elif cmd in ("/login", "/auth"):
            self.interactive_login(args)
            return True

        elif cmd == "/queue":
            self.queue_follow_up(args or None)
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

        elif cmd == "/agent":
            if args.lower() in {"pick", "select"}:
                self.interactive_agent_picker()
            elif not args:
                active = self.agent_mgr.get_agent(self.agent_id)
                available = ", ".join(agent.agent_id for agent in self.agent_mgr.list_agents())
                self.console.print(
                    f"[bold #FF7A00]Current Agent:[/bold #FF7A00] "
                    f"[bold cyan]{active.display_name} ({active.agent_id})[/bold cyan]"
                )
                self.console.print(f"[dim]Available Agents: {available}[/dim]\n")
            else:
                try:
                    selected_agent = self.agent_mgr.get_agent(args)
                except ValueError as exc:
                    self.console.print(f"[yellow]{exc}[/yellow]\n")
                else:
                    self.agent_id = selected_agent.agent_id
                    self._approval_callback = self._request_tool_approval
                    self._init_harness()
                    self.console.print(
                        f"[bold green]✓ Switched Agent to {selected_agent.agent_id}[/bold green]\n"
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

            if args.lower() == "all":
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
            session_dir = self.agent_mgr.get_session_dir(self.agent_id)
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
            saved_draft = self.prompt_session.get_draft()
            try:
                self.stream_renderer.render_audit_log()
            finally:
                self.prompt_session.restore_draft(saved_draft)

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
                if self._active_prompt_task is None or self._active_prompt_task.done():
                    self._active_prompt_task = asyncio.create_task(
                        self.prompt_session.read_prompt_async("› ")
                    )

                user_input = await self._active_prompt_task
                self._active_prompt_task = None

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    should_continue = self.handle_slash_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Set busy state and start turn
                self.prompt_session.is_busy = True
                turn_task = asyncio.create_task(self.execute_turn(user_input))
                self._active_turn_task = turn_task
                self.prompt_session.on_cancel_callback = lambda t=turn_task: t.cancel()

                # Start concurrent draft prompt reader while turn executes
                self._active_prompt_task = asyncio.create_task(
                    self.prompt_session.read_prompt_async("› ")
                )

                try:
                    while not turn_task.done():
                        if (
                            self._active_prompt_task is None
                            and not self.prompt_session.approval_active
                        ):
                            self._active_prompt_task = asyncio.create_task(
                                self.prompt_session.read_prompt_async("› ")
                            )
                        wait_tasks: list[asyncio.Task[Any]] = [turn_task]
                        if self._active_prompt_task is not None:
                            wait_tasks.append(self._active_prompt_task)
                        done, _ = await asyncio.wait(
                            wait_tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if self._active_prompt_task in done and not turn_task.done():
                            prompt_task = self._active_prompt_task
                            self._active_prompt_task = None
                            if not prompt_task.cancelled():
                                exc = prompt_task.exception()
                                if exc is not None and isinstance(
                                    exc, (EOFError, KeyboardInterrupt)
                                ):
                                    turn_task.cancel()
                                    raise exc
                                prompt_result = prompt_task.result()
                                if prompt_result.startswith("/queue"):
                                    self.handle_slash_command(prompt_result)
                            if (
                                self.prompt_session.is_busy
                                and not self.prompt_session.approval_active
                            ):
                                self._active_prompt_task = asyncio.create_task(
                                    self.prompt_session.read_prompt_async("› ")
                                )
                    # Await turn completion
                    await turn_task
                finally:
                    self.prompt_session.is_busy = False
                    self.prompt_session.on_cancel_callback = None
                    self._active_turn_task = None

            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Exiting Mia session... Goodbye![/dim]")
                self._print_session_resume_hint()
                break
