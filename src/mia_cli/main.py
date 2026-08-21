"""Typer CLI entrypoint for Mia AI coding agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.session.compactor import ContextCompactor
from mia_agent.session.jsonl import JsonlSessionStore
from mia_agent.session.tree import SessionTree
from mia_ai.providers.anthropic import AnthropicProvider
from mia_ai.providers.base import LLMProvider
from mia_ai.providers.openai_compatible import OpenAICompatibleProvider
from mia_cli.renderers.rich_stream import RichStreamRenderer
from mia_middleware.pipeline import ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware
from mia_middleware.telemetry import AuditLogMiddleware, CostBudgetMiddleware
from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool

app = typer.Typer(
    name="mia",
    help="Mia (Modular Intelligent Agent) - High-Performance AI Coding Agent Harness.",
    no_args_is_help=True,
)
profile_app = typer.Typer(help="Manage agent profiles and presets.")
sessions_app = typer.Typer(help="Inspect and manage saved session trees.")

app.add_typer(profile_app, name="profile")
app.add_typer(sessions_app, name="sessions")

console = Console()


def get_default_tools(cwd: Path | None = None) -> list[object]:
    """Instantiate standard built-in coding tools."""
    return [
        ReadFileTool(cwd=cwd),
        WriteFileTool(cwd=cwd),
        EditFileTool(cwd=cwd),
        BashTool(cwd=cwd),
    ]


def build_pipeline_from_profile(profile_middlewares: list[str]) -> ToolPipeline:
    """Instantiate middleware pipeline from profile specification."""
    middlewares: list[Any] = []
    if "security_guard" in profile_middlewares:
        middlewares.append(SecurityGuardMiddleware())
    if "cost_budget" in profile_middlewares:
        middlewares.append(CostBudgetMiddleware())
    if "audit_log" in profile_middlewares:
        middlewares.append(AuditLogMiddleware())
    return ToolPipeline(middlewares)


async def _run_agent_loop(
    prompt_text: str,
    profile_name: str = "coding",
    model_override: str | None = None,
    session_id: str | None = None,
    compaction_threshold: float | None = None,
    context_window: int | None = None,
    cwd: Path | None = None,
) -> None:
    work_dir = cwd or Path.cwd()

    # 1. Resolve Profile
    profile_manager = ProfileManager()
    profile = profile_manager.get_profile(profile_name)

    # 2. Resolve Model & Credentials
    config_mgr = ConfigManager()
    target_model = model_override or profile.model or "claude-3-5-sonnet"
    provider_name, model_name, api_key, base_url = config_mgr.resolve_credentials(
        model=target_model
    )

    # 3. Instantiate Provider
    provider: LLMProvider
    if provider_name == "anthropic":
        provider = AnthropicProvider(api_key=api_key, base_url=base_url)
    else:
        provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url)

    # 4. Resolve Tools & Pipeline
    all_tools = get_default_tools(cwd=work_dir)
    active_tools = profile_manager.filter_tools(profile, all_tools)
    pipeline = build_pipeline_from_profile(profile.middlewares)

    # 5. Resolve Session Store & History
    session_dir = profile_manager.get_session_dir(profile.name)
    actual_session_id = session_id or f"session_{int(asyncio.get_event_loop().time())}"
    session_file = session_dir / f"{actual_session_id}.jsonl"
    session_store = JsonlSessionStore(session_file)

    initial_messages = []
    if session_file.exists():
        entries = session_store.load_entries()
        tree = SessionTree(entries)
        initial_messages = tree.extract_messages_from_path(tree.get_active_path())

    compaction_ratio = (
        compaction_threshold
        if compaction_threshold is not None
        else (
            profile.compaction_threshold_ratio
            if profile.compaction_threshold_ratio is not None
            else config_mgr.config.compaction_threshold_ratio
        )
    )
    window_tokens = (
        context_window
        if context_window is not None
        else (
            profile.context_window_tokens
            if profile.context_window_tokens is not None
            else config_mgr.config.context_window_tokens
        )
    )
    compactor = ContextCompactor(
        context_window_tokens=window_tokens,
        compaction_threshold_ratio=compaction_ratio,
    )

    # 6. Instantiate Harness
    harness = AgentHarness(
        provider=provider,
        model=model_name,
        system_prompt=profile.system_prompt,
        tools=active_tools,
        pipeline=pipeline,
        max_steps_per_turn=profile.max_steps_per_turn,
        session_id=actual_session_id,
        messages=initial_messages,
        session_store=session_store,
        compactor=compactor,
    )

    # 7. Run and stream output
    renderer = RichStreamRenderer(console=console)
    async for event in harness.prompt(prompt_text):
        renderer.on_event(event)


@app.command(name="run")
def run_command(
    prompt: Annotated[str, typer.Option("--prompt", "-p", help="User instruction prompt")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Active profile name")] = "coding",
    model: Annotated[str | None, typer.Option("--model", "-m", help="LLM model identifier")] = None,
    resume: Annotated[
        str | None, typer.Option("--resume", "-r", help="Session ID to resume")
    ] = None,
    compaction_threshold: Annotated[
        float | None,
        typer.Option(
            "--compaction-threshold",
            "-c",
            help="Context compaction ratio threshold (e.g. 0.3 for 30%)",
        ),
    ] = None,
    context_window: Annotated[
        int | None,
        typer.Option("--context-window", "-w", help="Context window token limit (e.g. 128000)"),
    ] = None,
) -> None:
    """Execute a coding task with Mia in headless streaming mode."""
    if not prompt:
        prompt = typer.prompt("Prompt")
    asyncio.run(
        _run_agent_loop(
            prompt_text=prompt,
            profile_name=profile,
            model_override=model,
            session_id=resume,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
        )
    )


@app.command(name="login")
def login_command(
    provider: Annotated[
        str, typer.Argument(help="Provider name (e.g. anthropic, openai, deepseek)")
    ],
    key: Annotated[str | None, typer.Option("--key", "-k", help="API key")] = None,
) -> None:
    """Store provider credentials locally in ~/.mia/credentials.json."""
    api_key = key or typer.prompt(f"Enter API key for {provider}", hide_input=True)
    store = FileCredentialStore()
    store.set_api_key(provider, api_key)
    console.print(
        f"[bold green]✓ Successfully stored credentials for {provider.lower()}.[/bold green]"
    )


@profile_app.command(name="list")
def list_profiles_command() -> None:
    """List all available built-in and user profiles."""
    manager = ProfileManager()
    profiles = manager.list_profiles()

    table = Table(title="Mia Agent Profiles")
    table.add_column("Profile", style="bold cyan")
    table.add_column("Tools", style="green")
    table.add_column("Mode", style="magenta")
    table.add_column("Description", style="white")

    for p in profiles:
        tools_str = ", ".join(p.tools) if p.tools else "(none)"
        table.add_row(p.name, tools_str, p.execution_mode, p.description)

    console.print(table)


@sessions_app.command(name="list")
def list_sessions_command(
    profile: Annotated[
        str, typer.Option("--profile", help="Profile to filter sessions")
    ] = "coding",
) -> None:
    """List saved sessions for a given profile."""
    manager = ProfileManager()
    session_dir = manager.get_session_dir(profile)
    if not session_dir.exists():
        console.print(f"[dim]No sessions found for profile '{profile}'.[/dim]")
        return

    session_files = list(session_dir.glob("*.jsonl"))
    if not session_files:
        console.print(f"[dim]No sessions found for profile '{profile}'.[/dim]")
        return

    table = Table(title=f"Saved Sessions ({profile})")
    table.add_column("Session ID", style="bold cyan")
    table.add_column("File Size", style="dim")
    table.add_column("Path", style="dim")

    for sf in session_files:
        size_kb = sf.stat().st_size / 1024.0
        table.add_row(sf.stem, f"{size_kb:.1f} KB", str(sf))

    console.print(table)
