"""Contract tests for bundled Plugin installation, enablement, and runtime composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.agents import Agent, AgentManager
from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.events import ToolCallEvent, ToolResultEvent
from mia_agent.orchestration import AgentRuntimeFactory, RuntimeIdentity
from mia_agent.plugins import NotesPlugin, PluginManager
from mia_ai.providers.mock import MockProvider
from mia_middleware.telemetry import AuditLogMiddleware
from mia_tools.notes import NoteListTool


def make_agent_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(
        agents_dir=tmp_path / "agents",
        profiles_dir=tmp_path / "profiles",
        sessions_base_dir=tmp_path / "legacy-sessions",
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
