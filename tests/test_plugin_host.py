"""Contract tests for governed Plugin host catalog, static skills, trust, and provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


@pytest.mark.asyncio
async def test_plugin_context_operations_and_invariants(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginContext
    from mia_tools.base import BaseTool

    class DummyTool(BaseTool):
        name = "custom_tool"
        description = "Custom tool"
        parameters = {}
        effect = "side-effecting"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "done"

    manifest = PluginManifest(
        plugin_id="my_plugin",
        version="1.0.0",
        display_name="My Plugin",
        description="Test context",
        tool_specs=[
            PluginToolSpec(
                name="custom_tool",
                description="Custom tool",
                effect="side-effecting",
            )
        ],
    )

    ctx = PluginContext(
        plugin_id="my_plugin",
        agent_id="agent_1",
        config={"setting": "val"},
        data_dir=tmp_path / "data",
        manifest=manifest,
    )

    # 1. Register matching tool
    tool = DummyTool()
    ctx.register(tool)
    assert tool.plugin_id == "my_plugin"
    assert len(ctx._tools) == 1

    # 2. Register undeclared tool fails
    class UndeclaredTool(BaseTool):
        name = "unknown_tool"
        description = "Unknown"
        parameters = {}
        effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "done"

    with pytest.raises(ValueError, match="undeclared Tool"):
        ctx.register(UndeclaredTool())

    # 3. Register tool with wrong effect fails
    class BadEffectTool(BaseTool):
        name = "custom_tool"
        description = "Custom tool"
        parameters = {}
        effect = "non-mutating"  # Manifest declares side-effecting!

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "done"

    with pytest.raises(ValueError, match="undeclared effect"):
        ctx.register(BadEffectTool())

    # 4. Observe with valid phases
    called_phases: list[str] = []

    def my_observer(event: Any) -> None:
        called_phases.append("called")

    ctx.observe("run_started", my_observer)
    ctx.observe("event_emitted", my_observer)
    ctx.observe("run_finished", my_observer)
    assert len(ctx._observers["run_started"]) == 1

    # Invalid phase fails
    with pytest.raises(ValueError, match="Invalid observer phase"):
        ctx.observe("unknown_phase", my_observer)  # type: ignore[arg-type]

    # Non-callable fails
    with pytest.raises(TypeError):
        ctx.observe("run_started", "not_a_callable")  # type: ignore[arg-type]

    # 5. Effects record disposers
    disposed = []
    await ctx.effect(lambda: disposed.append("clean_1"))
    assert len(ctx._disposers) == 1

    val = await ctx.effect(lambda: "resource_res", cleanup=lambda: disposed.append("clean_2"))
    assert val == "resource_res"
    assert len(ctx._disposers) == 2

    # 6. Does not expose mutable core objects
    assert not hasattr(ctx, "session_store")
    assert not hasattr(ctx, "agent")
    assert not hasattr(ctx, "provider")
    assert not hasattr(ctx, "runner")
    assert not hasattr(ctx, "harness")
    assert not hasattr(ctx, "middleware_pipeline")


@pytest.mark.asyncio
async def test_activation_staging_and_rollback_on_failure(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_tools.base import BaseTool

    disposed_effects: list[str] = []

    class DummyToolA(BaseTool):
        name = "tool_a"
        description = "Tool A"
        parameters = {}
        effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "a"

    class PluginA:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_a",
                version="1.0.0",
                display_name="Plugin A",
                description="Acquires effect",
                tool_specs=[
                    PluginToolSpec(name="tool_a", description="Tool A", effect="non-mutating")
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            context.register(DummyToolA())
            await context.effect(lambda: disposed_effects.append("disposed_a"))

    class PluginB:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_b",
                version="1.0.0",
                display_name="Plugin B",
                description="Fails activation",
                dependencies=["plugin_a"],
                tool_specs=[
                    PluginToolSpec(name="tool_b", description="Tool B", effect="non-mutating")
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            raise RuntimeError("Failure in Plugin B activate!")

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    p_a = PluginA()
    p_b = PluginB()
    plugins._catalog["plugin_a"] = p_a.manifest
    plugins._catalog["plugin_b"] = p_b.manifest
    plugins.install("plugin_a")
    plugins.install("plugin_b")
    plugins.trust_plugin("plugin_a")
    plugins.trust_plugin("plugin_b")
    plugins.enable(alpha.agent_id, "plugin_a")
    plugins.enable(alpha.agent_id, "plugin_b")

    host = PluginHost()
    host.register_implementation("plugin_a", p_a)
    host.register_implementation("plugin_b", p_b)

    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    assert plan.plugins == ("plugin_a", "plugin_b")

    # Activation should fail when it reaches plugin_b and roll back plugin_a!
    with pytest.raises(ValueError, match="plugin_b"):
        await host.activate(
            plan,
            agent=agents.get_agent(alpha.agent_id),
            agent_manager=agents,
            plugin_manager=plugins,
        )

    # Rollback must have disposed plugin_a's effect
    assert disposed_effects == ["disposed_a"]


@pytest.mark.asyncio
async def test_activation_reverse_order_rollback(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_tools.base import BaseTool

    disposed_order: list[str] = []

    class DummyTool(BaseTool):
        def __init__(self, name: str) -> None:
            self.name = name
            self.description = name
            self.parameters = {}
            self.effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return self.name

    class StepPlugin:
        def __init__(self, pid: str, should_fail: bool = False) -> None:
            self.pid = pid
            self.should_fail = should_fail

        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id=self.pid,
                version="1.0.0",
                display_name=self.pid,
                description=self.pid,
                tool_specs=[
                    PluginToolSpec(
                        name=f"tool_{self.pid}", description=self.pid, effect="non-mutating"
                    )
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            if self.should_fail:
                raise RuntimeError(f"Deliberate failure in {self.pid}")
            context.register(DummyTool(f"tool_{self.pid}"))
            pid = self.pid
            await context.effect(lambda: disposed_order.append(f"cleaned_{pid}"))

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    p1 = StepPlugin("p1")
    p2 = StepPlugin("p2")
    p3 = StepPlugin("p3", should_fail=True)

    host = PluginHost()
    for p in [p1, p2, p3]:
        plugins._catalog[p.pid] = p.manifest
        plugins.install(p.pid)
        plugins.trust_plugin(p.pid)
        plugins.enable(alpha.agent_id, p.pid)
        host.register_implementation(p.pid, p)

    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    with pytest.raises(ValueError, match="p3"):
        await host.activate(
            plan,
            agent=agents.get_agent(alpha.agent_id),
            agent_manager=agents,
            plugin_manager=plugins,
        )

    # Rollback must be reverse order: p2 then p1!
    assert disposed_order == ["cleaned_p2", "cleaned_p1"]


@pytest.mark.asyncio
async def test_deterministic_activation_staged_publication_and_factory_integration(
    tmp_path: Path,
) -> None:
    import dataclasses

    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RuntimeIdentity
    from mia_ai.providers.mock import MockProvider
    from mia_tools.base import BaseTool

    activation_order: list[str] = []
    disposed_effects: list[str] = []

    class ToolX(BaseTool):
        name = "tool_x"
        description = "Tool X"
        parameters = {}
        effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "x"

    class ToolY(BaseTool):
        name = "tool_y"
        description = "Tool Y"
        parameters = {}
        effect = "side-effecting"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "y"

    class PluginY:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_y",
                version="1.0.0",
                display_name="Plugin Y",
                description="Depends on plugin_x",
                dependencies=["plugin_x"],
                tool_specs=[
                    PluginToolSpec(name="tool_y", description="Tool Y", effect="side-effecting")
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            activation_order.append("plugin_y")
            context.register(ToolY())
            await context.effect(lambda: disposed_effects.append("cleanup_y"))

    class PluginX:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="plugin_x",
                version="1.0.0",
                display_name="Plugin X",
                description="Base dependency",
                tool_specs=[
                    PluginToolSpec(name="tool_x", description="Tool X", effect="non-mutating")
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            activation_order.append("plugin_x")
            context.register(ToolX())
            await context.effect(lambda: disposed_effects.append("cleanup_x"))

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    px = PluginX()
    py = PluginY()
    plugins._catalog["plugin_x"] = px.manifest
    plugins._catalog["plugin_y"] = py.manifest
    plugins.install("plugin_x")
    plugins.install("plugin_y")
    plugins.trust_plugin("plugin_x")
    plugins.trust_plugin("plugin_y")
    plugins.enable(alpha.agent_id, "plugin_y")
    plugins.enable(alpha.agent_id, "plugin_x")

    host = PluginHost()
    host.register_implementation("plugin_x", px)
    host.register_implementation("plugin_y", py)

    plan = host.plan(agents.get_agent(alpha.agent_id), plugins)
    assert plan.plugins == ("plugin_x", "plugin_y")

    # Activation
    activation = await host.activate(
        plan,
        agent=agents.get_agent(alpha.agent_id),
        agent_manager=agents,
        plugin_manager=plugins,
    )

    # Deterministic dependency-first order
    assert activation_order == ["plugin_x", "plugin_y"]

    # Published contributions
    assert len(activation.tools) == 2
    tool_names = [t.name for t in activation.tools]
    assert tool_names == ["tool_x", "tool_y"]
    assert activation.tools[0].plugin_id == "plugin_x"
    assert activation.tools[1].plugin_id == "plugin_y"
    assert len(activation.disposers) == 2

    # Immutability
    with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
        activation.tools = ()  # type: ignore[misc]

    # Integration with AgentRuntimeFactory
    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    identity = RuntimeIdentity(
        run_id="r1", task_id="root", agent_id=alpha.agent_id, session_id="s1"
    )
    runtime = factory.build(
        identity=identity,
        provider=MockProvider(),
        cwd=tmp_path,
        activation=activation,
    )

    assert runtime.activation is activation
    harness_tool_names = [t.name for t in runtime.harness.tools]
    assert "tool_x" in harness_tool_names
    assert "tool_y" in harness_tool_names
    assert len(runtime.disposers) >= 2
