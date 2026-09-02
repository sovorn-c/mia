"""Typer CLI entrypoint for Mia AI coding agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mia_agent.agents import AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.orchestration import (
    AgentRunner,
    AgentRuntimeFactory,
    ModeRuntime,
    OrchestrationErrorEvent,
)
from mia_agent.plugins import PluginManager
from mia_agent.profiles.manager import ProfileManager
from mia_cli.renderers.rich_stream import RichStreamRenderer
from mia_middleware.access import ApprovalCallback, ApprovalRequest

app = typer.Typer(
    name="mia",
    help="Mia (Modular Intelligent Agent) - High-Performance AI Coding Agent Harness.",
    no_args_is_help=False,
)
profile_app = typer.Typer(help="Manage legacy profile aliases.")
agent_app = typer.Typer(help="Create, inspect, and select named Agents.")
sessions_app = typer.Typer(help="Inspect and manage saved session trees.")
plugin_app = typer.Typer(help="Install and manage bundled Plugins.")
template_app = typer.Typer(help="Inspect and instantiate Agent Templates.")

app.add_typer(agent_app, name="agent")
app.add_typer(profile_app, name="profile")
app.add_typer(sessions_app, name="sessions")
app.add_typer(plugin_app, name="plugin")
app.add_typer(template_app, name="template")

console = Console()


def _plugin_manager() -> PluginManager:
    return PluginManager(agent_manager=AgentManager())


def _confirm_tool(request: ApprovalRequest) -> bool:
    """Render a sanitized approval prompt for print-mode side effects."""
    console.print(
        f"[yellow]Agent {request.agent_id} requests {request.effect} Tool "
        f"{request.tool_name}.[/yellow]"
    )
    return typer.confirm("Approve this Tool call?", default=False)


async def _run_agent_loop(
    prompt_text: str,
    profile_name: str | None = None,
    agent_name: str | None = "mia",
    model_override: str | None = None,
    session_id: str | None = None,
    compaction_threshold: float | None = None,
    context_window: int | None = None,
    cwd: Path | None = None,
    mode_name: str = "single",
    approval_callback: ApprovalCallback | None = None,
) -> None:
    renderer = RichStreamRenderer(console=console)
    if agent_name is not None:
        manager = AgentManager()
        runner = AgentRunner(
            factory=AgentRuntimeFactory(agent_manager=manager),
            agent_manager=manager,
        )
        async for envelope in runner.prompt(
            prompt_text,
            agent_id=agent_name,
            model_override=model_override,
            session_id=session_id,
            cwd=cwd,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
            approval_callback=approval_callback,
        ):
            if isinstance(envelope.event, OrchestrationErrorEvent):
                renderer._stop_status()
                console.print(
                    f"[bold red]Orchestration error ({envelope.event.stage}): "
                    f"{envelope.event.error}[/bold red]"
                )
                continue
            renderer.on_event(envelope.event)
        return

    legacy_runtime = ModeRuntime()
    async for envelope in legacy_runtime.prompt(
        prompt_text,
        mode_name=mode_name,
        profile_name=profile_name or "coding",
        model_override=model_override,
        session_id=session_id,
        cwd=cwd,
        compaction_threshold=compaction_threshold,
        context_window=context_window,
        approval_callback=approval_callback,
    ):
        if isinstance(envelope.event, OrchestrationErrorEvent):
            renderer._stop_status()
            console.print(
                f"[bold red]Orchestration error ({envelope.event.stage}): "
                f"{envelope.event.error}[/bold red]"
            )
            continue
        renderer.on_event(envelope.event)


@app.command(name="run")
def run_command(
    prompt: Annotated[str, typer.Option("--prompt", "-p", help="User instruction prompt")] = "",
    agent: Annotated[str | None, typer.Option("--agent", help="Active Agent ID")] = "mia",
    profile: Annotated[str | None, typer.Option("--profile", help="Legacy profile alias")] = None,
    mode: Annotated[str, typer.Option("--mode", help="Legacy orchestration mode alias")] = "single",
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
    """Execute one prompt through a named Agent in headless streaming mode."""
    if not prompt:
        prompt = typer.prompt("Prompt")
    if profile is not None or mode != "single":
        Console(stderr=True).print(
            "[yellow]Warning: --profile/--mode are compatibility aliases; use --agent.[/yellow]"
        )
        agent = None
    asyncio.run(
        _run_agent_loop(
            prompt_text=prompt,
            profile_name=profile,
            agent_name=agent,
            model_override=model,
            session_id=resume,
            compaction_threshold=compaction_threshold,
            context_window=context_window,
            mode_name=mode,
            approval_callback=_confirm_tool,
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


@agent_app.command(name="create")
def create_agent_command(
    agent_id: Annotated[str, typer.Argument(help="Path-safe Agent ID")],
    name: Annotated[str | None, typer.Option("--name", help="Agent display name")] = None,
    instructions: Annotated[str, typer.Option("--instructions", help="System instructions")] = "",
    tools: Annotated[str | None, typer.Option("--tools", help="Comma-separated Tool names")] = None,
    access: Annotated[
        str, typer.Option("--access", help="read-only, approval-required, or full-access")
    ] = "approval-required",
    confirm_full_access: Annotated[
        bool, typer.Option("--confirm-full-access", help="Explicitly opt into full-access")
    ] = False,
) -> None:
    """Create a durable named Agent."""
    try:
        agent = AgentManager().create_agent(
            agent_id,
            display_name=name,
            instructions=instructions or "You are a helpful local AI Agent.",
            tools=[tool.strip() for tool in tools.split(",") if tool.strip()] if tools else None,
            access_policy=access,
            confirm_full_access=confirm_full_access,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="AGENT_ID") from exc
    console.print(
        f"[bold green]✓ Created Agent {agent.agent_id} ({agent.display_name}).[/bold green]"
    )


@agent_app.command(name="list")
def list_agents_command() -> None:
    """List built-in and saved Agents."""
    manager = AgentManager()
    selected = manager.default_agent().agent_id
    table = Table(title="Mia Agents")
    table.add_column("Agent", style="bold cyan")
    table.add_column("Name", style="white")
    table.add_column("Access", style="magenta")
    table.add_column("Tools", style="green")
    for agent in manager.list_agents():
        marker = "* " if agent.agent_id == selected else ""
        table.add_row(
            marker + agent.agent_id,
            agent.display_name,
            agent.access_policy,
            ", ".join(agent.tools) if agent.tools else "(none)",
        )
    console.print(table)


@agent_app.command(name="show")
def show_agent_command(
    agent_id: Annotated[str, typer.Argument(help="Agent ID")],
) -> None:
    """Inspect one Agent without displaying credential values."""
    try:
        inspection = AgentManager().inspect_agent(agent_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="AGENT_ID") from exc
    agent = inspection["agent"]
    console.print(f"[bold cyan]{agent.display_name}[/bold cyan] ({agent.agent_id})")
    console.print(f"Description: {agent.description}")
    console.print(f"Access: {agent.access_policy}")
    console.print(f"Tools: {', '.join(agent.tools) if agent.tools else '(none)'}")
    console.print(f"Plugins: {', '.join(agent.plugins) if agent.plugins else '(none)'}")
    console.print(f"Source: {inspection['source']}")
    if inspection["collision"]:
        console.print(
            "[yellow]Collision: native Agent takes precedence over legacy Profile.[/yellow]"
        )


@agent_app.command(name="use")
def use_agent_command(
    agent_id: Annotated[str, typer.Argument(help="Agent ID to select by default")],
    confirm_full_access: Annotated[
        bool, typer.Option("--confirm-full-access", help="Explicitly opt into full-access")
    ] = False,
) -> None:
    """Select the default Agent for future runs."""
    try:
        agent = AgentManager().set_default(agent_id, confirm_full_access=confirm_full_access)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="AGENT_ID") from exc
    console.print(f"[bold green]✓ Default Agent is now {agent.agent_id}.[/bold green]")


@agent_app.command(name="delete")
def delete_agent_command(
    agent_id: Annotated[str, typer.Argument(help="Agent ID to delete")],
) -> None:
    """Delete a saved non-built-in Agent."""
    try:
        deleted = AgentManager().delete_agent(agent_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="AGENT_ID") from exc
    if not deleted:
        raise typer.BadParameter(f"Agent '{agent_id}' was not found", param_hint="AGENT_ID")
    console.print(f"[bold green]✓ Deleted Agent {agent_id}.[/bold green]")


@plugin_app.command(name="list")
def list_plugins_command() -> None:
    """List bundled and explicitly installed Plugins."""
    manager = _plugin_manager()
    installed = {item.plugin_id for item in manager.list_installed()}
    table = Table(title="Mia Plugins")
    table.add_column("Plugin", style="bold cyan")
    table.add_column("Version", style="magenta")
    table.add_column("Status", style="green")
    for manifest in manager.list_available():
        table.add_row(
            manifest.plugin_id,
            manifest.version,
            "installed" if manifest.plugin_id in installed else "available",
        )
    console.print(table)


@plugin_app.command(name="show")
def show_plugin_command(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID")],
) -> None:
    """Inspect one bundled Plugin manifest."""
    try:
        manifest = _plugin_manager().get_manifest(plugin_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PLUGIN_ID") from exc
    console.print(f"[bold cyan]{manifest.display_name}[/bold cyan] ({manifest.plugin_id})")
    console.print(f"Version: {manifest.version}")
    console.print(f"Description: {manifest.description}")
    console.print(f"Tools: {', '.join(manifest.tools) if manifest.tools else '(none)'}")


@plugin_app.command(name="install")
def install_plugin_command(
    plugin_id: Annotated[str, typer.Argument(help="Bundled Plugin ID")],
) -> None:
    """Install one bundled Plugin locally."""
    try:
        installed = _plugin_manager().install(plugin_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PLUGIN_ID") from exc
    console.print(f"[bold green]✓ Installed Plugin {installed.plugin_id}.[/bold green]")


@plugin_app.command(name="enable")
def enable_plugin_command(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID")],
    agent_id: Annotated[str, typer.Option("--agent", help="Agent to enable the Plugin for")],
) -> None:
    """Enable an installed Plugin for one named Agent."""
    try:
        agent = _plugin_manager().enable(agent_id, plugin_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PLUGIN_ID") from exc
    console.print(f"[bold green]✓ Enabled {plugin_id} for Agent {agent.agent_id}.[/bold green]")


@plugin_app.command(name="configure")
def configure_plugin_command(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID")],
    agent_id: Annotated[str, typer.Option("--agent", help="Agent to configure")],
    notebook_name: Annotated[
        str | None, typer.Option("--notebook-name", help="Notes notebook display name")
    ] = None,
) -> None:
    """Configure an enabled Plugin for one named Agent."""
    config = {} if notebook_name is None else {"notebook_name": notebook_name}
    try:
        agent = _plugin_manager().configure(agent_id, plugin_id, config)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PLUGIN_ID") from exc
    console.print(f"[bold green]✓ Configured {plugin_id} for Agent {agent.agent_id}.[/bold green]")


@plugin_app.command(name="disable")
def disable_plugin_command(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID")],
    agent_id: Annotated[str, typer.Option("--agent", help="Agent to disable the Plugin for")],
) -> None:
    """Disable a Plugin for later Runs of one named Agent."""
    try:
        agent = _plugin_manager().disable(agent_id, plugin_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PLUGIN_ID") from exc
    console.print(f"[bold green]✓ Disabled {plugin_id} for Agent {agent.agent_id}.[/bold green]")


@template_app.command(name="list")
def list_templates_command() -> None:
    """List bundled Agent Templates."""
    templates = _plugin_manager().list_templates()
    table = Table(title="Mia Agent Templates")
    table.add_column("Template", style="bold cyan")
    table.add_column("Version", style="magenta")
    table.add_column("Plugins", style="green")
    for template in templates:
        table.add_row(
            template.template_id,
            template.version,
            ", ".join(template.required_plugins) if template.required_plugins else "(none)",
        )
    console.print(table)


@template_app.command(name="show")
def show_template_command(
    template_id: Annotated[str, typer.Argument(help="Template ID")],
) -> None:
    """Inspect one bundled Agent Template."""
    try:
        template = _plugin_manager().get_template(template_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="TEMPLATE_ID") from exc
    console.print(f"[bold cyan]{template.display_name}[/bold cyan] ({template.template_id})")
    console.print(f"Version: {template.version}")
    console.print(f"Description: {template.description}")
    console.print(f"Access: {template.access_policy}")
    console.print(f"Plugins: {', '.join(template.required_plugins) or '(none)'}")


@template_app.command(name="create")
def create_template_agent_command(
    template_id: Annotated[str, typer.Argument(help="Template ID")],
    agent_id: Annotated[str, typer.Argument(help="New Agent ID")],
) -> None:
    """Create a new Agent from one bundled Template."""
    try:
        agent = _plugin_manager().instantiate(template_id, agent_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="AGENT_ID") from exc
    console.print(
        f"[bold green]✓ Created Agent {agent.agent_id} from Template {template_id}.[/bold green]"
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
    agent: Annotated[str | None, typer.Option("--agent", help="Default Agent ID")] = None,
    profile: Annotated[
        str, typer.Option("--profile", "-p", help="Legacy Agent profile alias")
    ] = "coding",
    session: Annotated[
        str | None,
        typer.Option("--session", help="Resume an interactive session by ID"),
    ] = None,
) -> None:
    """Default callback: launch interactive Mia REPL harness."""
    if ctx.invoked_subcommand is None:
        if session and (Path(session).name != session or session in {".", ".."}):
            raise typer.BadParameter("must be a session ID, not a path", param_hint="--session")

        from mia_cli.repl import MiaREPL

        profile_source = ctx.get_parameter_source("profile")
        profile_supplied = profile_source is not None and profile_source.name == "COMMANDLINE"
        if (session and agent is None) or (profile_supplied and agent is None):
            Console(stderr=True).print(
                "[yellow]Warning: --profile is deprecated; use --agent instead.[/yellow]"
            )
            # Preserve the old constructor shape for compatibility scripts.
            repl = MiaREPL(model=model, profile=profile, session_id=session)
        else:
            repl = MiaREPL(model=model, agent=agent or "mia", session_id=session)
        repl.run()
