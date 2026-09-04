"""Contract tests for bundled Plugin installation, enablement, and runtime composition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.events import ToolCallEvent, ToolResultEvent
from mia_agent.plugins import NotesPlugin, PluginManager
from mia_agent.runtime_factory import AgentRuntimeFactory
from mia_agent.runtime_models import RuntimeIdentity
from mia_ai.providers.mock import MockProvider
from mia_middleware.telemetry import AuditLogMiddleware
from mia_tools.notes import NoteListTool


def make_agent_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(
        agents_dir=tmp_path / "agents",
    )


def test_agent_plugin_configuration_is_normalized_and_secret_free() -> None:
    agent = Agent(
        agent_id="alpha",
        plugin_config={"Notes": {"notebook_name": "Personal"}},
    )
    assert agent.plugin_config == {"notes": {"notebook_name": "Personal"}}
    with pytest.raises(ValueError, match="credential-like"):
        Agent(agent_id="alpha", plugin_config={"notes": {"api_key": "secret"}})
    with pytest.raises(ValueError, match="secret-like"):
        Agent(agent_id="alpha", plugin_config={"notes": {"notebook_name": "sk-secret"}})


def test_agent_plugin_ids_are_normalized_and_unique() -> None:
    assert Agent(agent_id="alpha", plugins=["Notes"]).plugins == ["notes"]
    with pytest.raises(ValueError, match="duplicate"):
        Agent(agent_id="alpha", plugins=["notes", "Notes"])
    with pytest.raises(ValueError, match="Plugin ID"):
        Agent(agent_id="alpha", plugins=["../notes"])


def test_malformed_installed_plugin_state_fails_closed(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.state_path.parent.mkdir(parents=True)
    plugins.state_path.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="state is invalid"):
        plugins.list_installed()


def test_incompatible_installed_plugin_state_fails_before_tool_build(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable(alpha.agent_id, "notes")
    plugins.state_path.write_text(
        '{"plugins": [{"plugin_id": "notes", "version": "9.9.9", "api_version": 1}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incompatible"):
        plugins.resolve_tools(agents.get_agent(alpha.agent_id))


def test_bundled_notes_plugin_installs_without_network(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    available = plugins.list_available()
    assert available[0].plugin_id == "notes"
    assert available[0].version == "1.0.0"
    assert available[0].tools == ["note_create", "note_list", "note_read"]
    assert plugins.list_installed() == []

    installed = plugins.install("notes")

    assert installed.plugin_id == "notes"
    assert [item.plugin_id for item in plugins.list_installed()] == ["notes"]
    assert plugins.install("notes") == installed
    assert (tmp_path / "plugins" / "installed.json").exists()


def test_installed_plugin_can_be_enabled_for_one_named_agent(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")

    enabled = plugins.enable("alpha", "notes")

    assert enabled.agent_id == alpha.agent_id
    assert enabled.plugins == ["notes"]
    assert agents.get_agent("alpha").plugins == ["notes"]
    assert agents.get_agent("alpha").tools == []
    with pytest.raises(ValueError, match="built-in"):
        plugins.enable("mia", "notes")


def test_enabled_plugin_can_be_configured_and_disabled_without_data_loss(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable("alpha", "notes")

    configured = plugins.configure("alpha", "notes", {"notebook_name": "Work"})
    assert configured.plugin_config == {"notes": {"notebook_name": "Work"}}

    disabled = plugins.disable("alpha", "notes")
    assert disabled.plugins == []
    assert disabled.plugin_config == {"notes": {"notebook_name": "Work"}}
    assert agents.get_agent("alpha").plugins == []


def test_enabled_plugin_tools_are_composed_into_agent_runtime(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable("alpha", "notes")
    factory = AgentRuntimeFactory(
        agent_manager=agents,
        plugin_manager=plugins,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )

    runtime = factory.build(
        identity=RuntimeIdentity(
            agent_id="alpha",
            run_id="run-1",
            task_id="root",
            session_id="session-1",
        ),
        provider=MockProvider(),
        cwd=tmp_path,
    )

    assert [tool.name for tool in runtime.harness.tools] == [
        "note_create",
        "note_list",
        "note_read",
    ]
    assert [tool.plugin_id for tool in runtime.harness.tools] == ["notes"] * 3


def test_plugin_manager_rejects_undeclared_tool_contributions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable(alpha.agent_id, "notes")

    monkeypatch.setattr(
        NotesPlugin,
        "build_tools",
        lambda _self, **kwargs: [NoteListTool(kwargs["data_dir"])],
    )
    with pytest.raises(ValueError, match="declared"):
        plugins.resolve_tools(agents.get_agent("alpha"))


def test_runtime_rejects_duplicate_tool_names_before_provider_execution(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("alpha", tools=[])

    class DuplicatePluginManager(PluginManager):
        def resolve_tools(self, agent: Agent) -> list[NoteListTool]:
            data_dir = self.agent_manager.agent_home(agent.agent_id) / "plugins" / "notes"
            return [NoteListTool(data_dir), NoteListTool(data_dir)]

    plugins = DuplicatePluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    with pytest.raises(ValueError, match="duplicate Tool"):
        AgentRuntimeFactory(
            agent_manager=agents,
            plugin_manager=plugins,
            config_manager=ConfigManager(
                config_path=tmp_path / "config.json",
                credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
            ),
        ).build(
            identity=RuntimeIdentity(
                agent_id="alpha",
                run_id="run-1",
                task_id="root",
                session_id="session-1",
            ),
            provider=MockProvider(),
            cwd=tmp_path,
        )


@pytest.mark.asyncio
async def test_plugin_tool_uses_existing_access_policy_pipeline(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable("alpha", "notes")
    provider = MockProvider()
    provider.queue_tool_call_response(
        "note_create",
        {"title": "Private", "content": "Approval protected"},
    )
    provider.queue_text_response("created")
    approvals = []
    runtime = AgentRuntimeFactory(
        agent_manager=agents,
        plugin_manager=plugins,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    ).build(
        identity=RuntimeIdentity(
            agent_id="alpha",
            run_id="run-1",
            task_id="root",
            session_id="session-1",
        ),
        provider=provider,
        cwd=tmp_path,
        approval_callback=lambda request: approvals.append(request) or True,
    )

    events = [event async for event in runtime.harness.prompt("create a note")]

    call = next(event for event in events if isinstance(event, ToolCallEvent))
    result = next(event for event in events if isinstance(event, ToolResultEvent))
    assert call.plugin_id == "notes"
    assert result.is_error is False
    assert result.plugin_id == "notes"
    assert approvals[0].tool_name == "note_create"
    assert approvals[0].effect == "side-effecting"
    audit = next(
        middleware
        for middleware in runtime.harness.pipeline.middlewares
        if isinstance(middleware, AuditLogMiddleware)
    )
    assert audit.logs[0].plugin_id == "notes"
    assert list((tmp_path / "agents" / "alpha" / "plugins" / "notes").glob("*.json"))


@pytest.mark.asyncio
async def test_read_only_agent_only_receives_non_mutating_notes_tools(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("observer", access_policy="read-only", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable("observer", "notes")
    provider = MockProvider()
    provider.queue_text_response("notes are readable")

    runtime = AgentRuntimeFactory(
        agent_manager=agents,
        plugin_manager=plugins,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    ).build(
        identity=RuntimeIdentity(
            agent_id="observer",
            run_id="run-1",
            task_id="root",
            session_id="session-1",
        ),
        provider=provider,
        cwd=tmp_path,
    )

    [event async for event in runtime.harness.prompt("list notes")]
    assert runtime.agent.tools == ["note_list", "note_read"]
    assert [tool["name"] for tool in provider.recorded_calls[0]["tools"]] == [
        "note_list",
        "note_read",
    ]


def test_plugin_tools_staged_complete_set_fails_closed(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    # Agent with notes and an uninstalled or broken plugin
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    # Directly set plugins list on agent to include a nonexistent plugin
    broken_agent = alpha.model_copy(update={"plugins": ["notes", "missing_plugin"]})
    agents.save_agent(broken_agent)

    factory = AgentRuntimeFactory(
        agent_manager=agents,
        plugin_manager=plugins,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )

    with pytest.raises(ValueError, match="missing_plugin"):
        factory.build(
            identity=RuntimeIdentity(
                agent_id="alpha",
                run_id="r1",
                task_id="root",
                session_id="s1",
            ),
            provider=MockProvider(),
            cwd=tmp_path,
        )


def test_plugin_free_agent_compatibility_intact(tmp_path: Path) -> None:
    agents = make_agent_manager(tmp_path)
    agents.create_agent("plain", tools=["read_file", "write_file"])
    factory = AgentRuntimeFactory(
        agent_manager=agents,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )
    runtime = factory.build(
        identity=RuntimeIdentity(
            agent_id="plain",
            run_id="r1",
            task_id="root",
            session_id="s1",
        ),
        provider=MockProvider(),
        cwd=tmp_path,
    )
    # Plain agent should only have its declared tools
    tool_names = [tool.name for tool in runtime.harness.tools]
    assert tool_names == ["read_file", "write_file"]
    for tool in runtime.harness.tools:
        assert getattr(tool, "plugin_id", None) is None


@pytest.mark.asyncio
async def test_cooperative_cleanup_disposer_failure_emits_diagnostic_preserving_success(
    tmp_path: Path,
) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.events import TurnCompleteEvent
    from mia_agent.runtime_events import PluginDiagnosticEvent
    from mia_agent.runtime_models import RunRequest

    agents = make_agent_manager(tmp_path)
    agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
    plugins.install("notes")
    plugins.enable("alpha", "notes")

    provider = MockProvider()
    provider.queue_text_response("Done without issues")

    def failing_disposer() -> None:
        raise RuntimeError("database connection failed during teardown")

    failing_disposer.plugin_id = "notes"  # type: ignore[attr-defined]

    factory = AgentRuntimeFactory(
        agent_manager=agents,
        plugin_manager=plugins,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
    )
    # Monkey-patch build to include failing disposer
    orig_build = factory.build

    def build_with_disposer(*args: Any, **kwargs: Any) -> Any:
        kwargs["disposers"] = [failing_disposer]
        return orig_build(*args, **kwargs)

    factory.build = build_with_disposer  # type: ignore[method-assign]

    runner = AgentRunner(
        agent_manager=agents,
        config_manager=ConfigManager(
            config_path=tmp_path / "config.json",
            credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
        ),
        factory=factory,
    )

    envelopes = [
        env
        async for env in runner.run(
            RunRequest(prompt_text="do work", agent_id="alpha"),
            provider=provider,
            cwd=tmp_path,
        )
    ]

    # Diagnostic event must be emitted
    diag_env = next(env for env in envelopes if isinstance(env.event, PluginDiagnosticEvent))
    assert diag_env.event.plugin_id == "notes"
    assert diag_env.event.phase == "cleanup"
    assert "database connection failed" in (diag_env.event.error or "")

    # Terminal event must remain TurnCompleteEvent with domain success preserved
    terminal_env = envelopes[-1]
    assert isinstance(terminal_env.event, TurnCompleteEvent)
    assert terminal_env.event.stop_reason == "stop"


@pytest.mark.asyncio
async def test_cooperative_cleanup_timeout_quarantines_plugin(tmp_path: Path) -> None:
    import asyncio

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.runtime_events import PluginDiagnosticEvent

    PluginManager.clear_quarantine()
    try:
        agents = make_agent_manager(tmp_path)
        agents.create_agent("alpha", tools=[])
        plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")
        plugins.install("notes")
        plugins.enable("alpha", "notes")

        provider = MockProvider()
        provider.queue_text_response("Done")

        async def hanging_disposer() -> None:
            await asyncio.sleep(10.0)

        hanging_disposer.plugin_id = "notes"  # type: ignore[attr-defined]

        factory = AgentRuntimeFactory(
            agent_manager=agents,
            plugin_manager=plugins,
            config_manager=ConfigManager(
                config_path=tmp_path / "config.json",
                credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
            ),
        )

        runner = AgentRunner(
            agent_manager=agents,
            config_manager=ConfigManager(
                config_path=tmp_path / "config.json",
                credential_store=FileCredentialStore(path=tmp_path / "credentials.json"),
            ),
            factory=factory,
        )

        # Execute cleanup directly with very small timeout to trigger TimeoutError
        identity = RuntimeIdentity(agent_id="alpha", run_id="r1", task_id="root", session_id="s1")
        runtime = factory.build(
            identity=identity, provider=provider, cwd=tmp_path, disposers=[hanging_disposer]
        )

        diagnostics = await runner._run_cooperative_cleanup(runtime, identity, timeout=0.01)
        assert len(diagnostics) == 1
        diag_event = diagnostics[0].event
        assert isinstance(diag_event, PluginDiagnosticEvent)
        assert diag_event.plugin_id == "notes"
        assert "timed out" in diag_event.message

        # Plugin is now quarantined
        assert PluginManager.is_quarantined("notes")

        # Later runtime build fails closed due to quarantine
        with pytest.raises(ValueError, match="quarantined"):
            factory.build(identity=identity, provider=provider, cwd=tmp_path)
    finally:
        PluginManager.clear_quarantine()
