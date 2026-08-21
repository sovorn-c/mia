"""Typer CLI entrypoint for Mia AI coding agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.orchestration import ModeRuntime, OrchestrationErrorEvent
from mia_agent.profiles.manager import ProfileManager
from mia_cli.renderers.rich_stream import RichStreamRenderer

app = typer.Typer(
    name="mia",
    help="Mia (Modular Intelligent Agent) - High-Performance AI Coding Agent Harness.",
    no_args_is_help=False,
)
profile_app = typer.Typer(help="Manage agent profiles and presets.")
sessions_app = typer.Typer(help="Inspect and manage saved session trees.")

app.add_typer(profile_app, name="profile")
app.add_typer(sessions_app, name="sessions")

console = Console()


async def _run_agent_loop(
    prompt_text: str,
    profile_name: str = "coding",
    model_override: str | None = None,
    session_id: str | None = None,
    compaction_threshold: float | None = None,
    context_window: int | None = None,
    cwd: Path | None = None,
    mode_name: str = "single",
) -> None:
    runtime = ModeRuntime()
    renderer = RichStreamRenderer(console=console)
    async for envelope in runtime.prompt(
        prompt_text,
        mode_name=mode_name,
        profile_name=profile_name,
        model_override=model_override,
        session_id=session_id,
        cwd=cwd,
        compaction_threshold=compaction_threshold,
        context_window=context_window,
    ):
        if isinstance(envelope.event, OrchestrationErrorEvent):
            console.print(
                f"[bold red]Orchestration error ({envelope.event.stage}): "
                f"{envelope.event.error}[/bold red]"
            )
            continue
        renderer.on_event(envelope.event)


@app.command(name="run")
def run_command(
    prompt: Annotated[str, typer.Option("--prompt", "-p", help="User instruction prompt")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Active profile name")] = "coding",
    mode: Annotated[str, typer.Option("--mode", help="Orchestration mode name")] = "single",
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
            mode_name=mode,
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


@app.command(name="tui")
def tui_command(
    model: Annotated[str | None, typer.Option("--model", "-m", help="Default model")] = None,
) -> None:
    """Launch the full-screen Mia Textual TUI."""
    from mia_cli.tui.app import MiaApp

    config_mgr = ConfigManager()
    target_model = model or config_mgr.config.default_model
    tui_app = MiaApp(model_name=target_model)
    tui_app.run()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Default model")] = None,
    profile: Annotated[str, typer.Option("--profile", "-p", help="Agent profile")] = "coding",
) -> None:
    """Default callback: launch interactive Mia REPL harness."""
    if ctx.invoked_subcommand is None:
        from mia_cli.repl import MiaREPL

        repl = MiaREPL(model=model, profile=profile)
        repl.run()
