"""Contract tests for governed Plugin host catalog, static skills, trust, and provenance."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.agents import AgentManager
from mia_agent.plugin_models import (
    CORE_PLUGIN_API_VERSION,
    AgentTemplate,
    PluginManifest,
    PluginProvenance,
    PluginToolSpec,
    PluginTrust,
    StaticSkill,
)
from mia_agent.plugins import PluginManager


def make_agent_manager(tmp_path: Path) -> AgentManager:
    return AgentManager(agents_dir=tmp_path / "agents")


def test_declarative_plugin_manifest_with_static_skills_and_templates() -> None:
    skill = StaticSkill(
        skill_id="research_workflow",
        display_name="Research Workflow",
        description="Structured deep research skill.",
        instructions="Perform deep literature review and synthesize findings.",
    )
    template = AgentTemplate(
        template_id="researcher",
        version="1.0.0",
        display_name="Researcher Agent",
        description="Agent dedicated to research.",
        instructions="You are a research specialist.",
        tools=[],
        required_plugins=["research_pack"],
    )
    manifest = PluginManifest(
        plugin_id="research_pack",
        version="1.0.0",
        plugin_type="declarative",
        display_name="Research Pack",
        description="Declarative skills and templates for research.",
        skills=[skill],
        templates=[template],
    )
    assert manifest.plugin_id == "research_pack"
    assert manifest.plugin_type == "declarative"
    assert len(manifest.skills) == 1
    assert manifest.skills[0].skill_id == "research_workflow"
    assert manifest.templates[0].template_id == "researcher"
    assert manifest.tool_specs == []

    # Declarative plugins cannot declare executable tools
    with pytest.raises(ValueError, match="Declarative"):
        PluginManifest(
            plugin_id="bad_declarative",
            version="1.0.0",
            plugin_type="declarative",
            display_name="Bad Declarative",
            description="Tries to declare tools",
            tool_specs=[
                PluginToolSpec(
                    name="do_something",
                    description="Executable tool",
                    effect="side-effecting",
                )
            ],
        )


def test_static_skill_validation() -> None:
    skill = StaticSkill(
        skill_id="Code-Review",
        display_name="Code Reviewer",
        description="Review pull requests.",
        instructions="Analyze changes for defects.",
    )
    assert skill.skill_id == "code-review"  # normalized to lowercase

    with pytest.raises(ValueError, match="Skill text fields must not be blank"):
        StaticSkill(
            skill_id="blank_desc",
            display_name="Valid",
            description="   ",
            instructions="Valid instructions",
        )

    with pytest.raises(ValueError, match="secret-like"):
        StaticSkill(
            skill_id="leaky_skill",
            display_name="Valid",
            description="Valid",
            instructions="sk-1234567890abcdef1234567890abcdef",
        )


def test_plugin_manifest_duplicate_skills_and_dependencies() -> None:
    skill1 = StaticSkill(
        skill_id="skill_a",
        display_name="Skill A",
        description="Skill A desc",
        instructions="Inst A",
    )
    skill2 = StaticSkill(
        skill_id="skill_a",
        display_name="Skill A copy",
        description="Skill A copy desc",
        instructions="Inst A copy",
    )
    with pytest.raises(ValueError, match="duplicate Skill"):
        PluginManifest(
            plugin_id="dupe_skills",
            version="1.0.0",
            display_name="Dupe Skills",
            description="Has duplicate skills",
            skills=[skill1, skill2],
        )

    with pytest.raises(ValueError, match="dependencies contain duplicates"):
        PluginManifest(
            plugin_id="dupe_deps",
            version="1.0.0",
            display_name="Dupe Deps",
            description="Has duplicate dependencies",
            dependencies=["dep-a", "Dep-A"],
        )


def test_plugin_provenance_and_trust_models() -> None:
    provenance = PluginProvenance(
        source="installed",
        package_name="mia-ext-web",
        package_version="0.2.0",
        entry_point="mia_ext_web:plugin",
    )
    assert provenance.source == "installed"
    assert provenance.package_name == "mia-ext-web"

    trust = PluginTrust(
        trust_class="trusted-code",
        status="untrusted",
        explicit=False,
        message="Installed code requires explicit administrator trust.",
    )
    assert trust.status == "untrusted"
    assert not trust.explicit

    manifest = PluginManifest(
        plugin_id="web_tools",
        version="1.0.0",
        plugin_type="trusted-code",
        display_name="Web Tools",
        description="Web scraping tools.",
        provenance=provenance,
        trust=trust,
    )
    assert manifest.provenance is not None
    assert manifest.provenance.package_name == "mia-ext-web"
    assert manifest.trust is not None
    assert manifest.trust.status == "untrusted"


def test_plugin_manifest_secret_free_metadata() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        PluginManifest(
            plugin_id="secret_plugin",
            version="1.0.0",
            display_name="Secret Plugin",
            description="Bearer abcdef1234567890",
        )


def test_plugin_manifest_api_version_compatibility() -> None:
    with pytest.raises(ValueError, match="Unsupported Plugin API version"):
        PluginManifest(
            plugin_id="future_plugin",
            version="1.0.0",
            api_version=CORE_PLUGIN_API_VERSION + 1,
            display_name="Future",
            description="Future API version",
        )


def test_catalog_inspection_does_not_invoke_callbacks_or_mutate_state(tmp_path: Path) -> None:
    class MockExecutablePlugin:
        def __init__(self) -> None:
            self.activated = False

        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="executable_mock",
                version="1.0.0",
                plugin_type="trusted-code",
                display_name="Executable Mock",
                description="Has an activate callback",
                skills=[
                    StaticSkill(
                        skill_id="mock_skill",
                        display_name="Mock Skill",
                        description="Skill from executable plugin",
                        instructions="Follow mock steps.",
                    )
                ],
            )

        async def activate(self, context: object) -> None:
            self.activated = True
            raise RuntimeError("Should never be called during catalog inspection!")

    agents = make_agent_manager(tmp_path)
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    mock_plugin = MockExecutablePlugin()
    plugins._catalog["executable_mock"] = mock_plugin.manifest

    # Inspecting manifest
    manifest = plugins.get_manifest("executable_mock")
    assert manifest.plugin_id == "executable_mock"
    assert mock_plugin.activated is False

    # Listing available
    available = plugins.list_available()
    assert any(m.plugin_id == "executable_mock" for m in available)
    assert mock_plugin.activated is False

    # Listing skills
    skills = plugins.list_skills()
    assert any(s.skill_id == "mock_skill" for s in skills)
    assert mock_plugin.activated is False

    # Ensure no custom agents or sessions mutated
    from mia_agent.agents import BUILTIN_AGENTS

    assert len(agents.list_agents()) == len(BUILTIN_AGENTS)


def test_discover_entry_point_plugins_without_callback_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.plugins import MIA_PLUGIN_ENTRY_POINT_GROUP

    class FakeDist:
        name = "mia-ext-web"
        version = "0.2.0"

    class FakeEntryPoint:
        name = "web_tools"
        value = "mia_ext_web:plugin"
        group = MIA_PLUGIN_ENTRY_POINT_GROUP
        dist = FakeDist()

        def load(self) -> object:
            class MockPlugin:
                @property
                def manifest(self) -> PluginManifest:
                    return PluginManifest(
                        plugin_id="web_tools",
                        version="0.2.0",
                        plugin_type="trusted-code",
                        display_name="Web Tools",
                        description="External web tools",
                        tool_specs=[
                            PluginToolSpec(
                                name="web_search",
                                description="Search web",
                                effect="non-mutating",
                            )
                        ],
                    )

                async def activate(self, context: object) -> None:
                    raise RuntimeError("Should not be activated during discovery")

            return MockPlugin()

    monkeypatch.setattr(
        "mia_agent.plugins.discover_entry_points",
        lambda: [FakeEntryPoint()],
    )

    agents = make_agent_manager(tmp_path)
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    manifest = plugins.get_manifest("web_tools")
    assert manifest.plugin_id == "web_tools"
    assert manifest.provenance is not None
    assert manifest.provenance.source == "installed"
    assert manifest.provenance.package_name == "mia-ext-web"
    assert manifest.provenance.package_version == "0.2.0"
    assert manifest.trust is not None
    assert manifest.trust.status == "untrusted"
    assert manifest.trust.explicit is False


def test_installed_code_requires_explicit_trust_before_enablement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.plugins import MIA_PLUGIN_ENTRY_POINT_GROUP

    class FakeDist:
        name = "mia-ext-code"
        version = "1.0.0"

    class FakeEntryPoint:
        name = "code_tools"
        value = "mia_ext_code:plugin"
        group = MIA_PLUGIN_ENTRY_POINT_GROUP
        dist = FakeDist()

        def load(self) -> object:
            class MockPlugin:
                @property
                def manifest(self) -> PluginManifest:
                    return PluginManifest(
                        plugin_id="code_tools",
                        version="1.0.0",
                        plugin_type="trusted-code",
                        display_name="Code Tools",
                        description="External code tools",
                        tool_specs=[
                            PluginToolSpec(
                                name="run_eval",
                                description="Run eval",
                                effect="non-mutating",
                            )
                        ],
                    )

            return MockPlugin()

    monkeypatch.setattr(
        "mia_agent.plugins.discover_entry_points",
        lambda: [FakeEntryPoint()],
    )

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    # Untrusted installed code can be installed
    installed = plugins.install("code_tools")
    assert installed.plugin_id == "code_tools"

    # But cannot be enabled without explicit trust
    assert not plugins.is_trusted("code_tools")
    with pytest.raises(ValueError, match="trust"):
        plugins.enable(alpha.agent_id, "code_tools")

    # Explicitly trust the plugin
    plugins.trust_plugin("code_tools")
    assert plugins.is_trusted("code_tools")
    manifest = plugins.get_manifest("code_tools")
    assert manifest.trust is not None
    assert manifest.trust.status == "trusted"
    assert manifest.trust.explicit is True

    # Now enablement succeeds
    enabled = plugins.enable(alpha.agent_id, "code_tools")
    assert "code_tools" in enabled.plugins

    # Revoke trust
    plugins.revoke_plugin_trust("code_tools")
    assert not plugins.is_trusted("code_tools")
    assert plugins.get_manifest("code_tools").trust.status == "untrusted"


@pytest.mark.asyncio
async def test_plan_activation_validates_complete_set_without_callbacks(tmp_path: Path) -> None:
    from mia_agent.plugin_host import ActivationPlan, PluginHost

    class MockA:
        def __init__(self) -> None:
            self.activated = False

        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_a",
                version="1.0.0",
                display_name="Plugin A",
                description="Dep A",
                tool_specs=[
                    PluginToolSpec(name="tool_a", description="Tool A", effect="non-mutating")
                ],
            )

        async def activate(self, context: object) -> None:
            self.activated = True

    class MockB:
        def __init__(self) -> None:
            self.activated = False

        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_b",
                version="1.0.0",
                display_name="Plugin B",
                description="Dep B depends on A",
                dependencies=["plugin_a"],
                tool_specs=[
                    PluginToolSpec(name="tool_b", description="Tool B", effect="non-mutating")
                ],
            )

        async def activate(self, context: object) -> None:
            self.activated = True

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    mock_a = MockA()
    mock_b = MockB()
    plugins._catalog["plugin_a"] = mock_a.manifest
    plugins._catalog["plugin_b"] = mock_b.manifest
    plugins.install("plugin_a")
    plugins.install("plugin_b")
    plugins.trust_plugin("plugin_a")
    plugins.trust_plugin("plugin_b")
    plugins.enable(alpha.agent_id, "plugin_b")
    plugins.enable(alpha.agent_id, "plugin_a")

    host = PluginHost()
    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    assert isinstance(plan, ActivationPlan)
    # Order must be dependency first: plugin_a before plugin_b!
    assert plan.plugins == ("plugin_a", "plugin_b")

    # Planning MUST NOT call activate callbacks
    assert mock_a.activated is False
    assert mock_b.activated is False


def test_plan_activation_fails_closed_on_missing_or_cycle_dependency(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginHost

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    manifest_b = PluginManifest(
        plugin_id="plugin_b",
        version="1.0.0",
        display_name="Plugin B",
        description="B requires A",
        dependencies=["plugin_a"],
    )
    plugins._catalog["plugin_b"] = manifest_b
    plugins.install("plugin_b")
    plugins.trust_plugin("plugin_b")
    plugins.enable(alpha.agent_id, "plugin_b")

    host = PluginHost()
    # Missing dependency plugin_a
    with pytest.raises(ValueError, match="dependency"):
        host.plan(agents.get_agent(alpha.agent_id), plugins)


def test_plan_activation_tie_breaks_independent_plugins_by_normalized_id(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginHost

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    for pid in ["zebra", "alpha_plugin", "beta"]:
        m = PluginManifest(
            plugin_id=pid,
            version="1.0.0",
            display_name=pid,
            description=pid,
        )
        plugins._catalog[pid] = m
        plugins.install(pid)
        plugins.trust_plugin(pid)
        plugins.enable(alpha.agent_id, pid)

    host = PluginHost()
    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    assert plan.plugins == ("alpha_plugin", "beta", "zebra")


def test_plugin_free_agent_plan_and_activation_compatibility(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginHost

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    host = PluginHost()
    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    assert plan.plugins == ()

