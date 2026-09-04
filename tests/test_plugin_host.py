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


@pytest.mark.asyncio
async def test_activation_observers_and_disposers_in_agent_runner(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider
    from mia_tools.base import BaseTool

    observer_trace: list[str] = []
    disposer_trace: list[str] = []

    class DummyTool(BaseTool):
        name = "observed_tool"
        description = "Observed Tool"
        parameters = {}
        effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "ok"

    class ObservablePlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="obs_plugin",
                version="1.0.0",
                display_name="Observable Plugin",
                description="Tests observers and disposers",
                tool_specs=[
                    PluginToolSpec(
                        name="observed_tool", description="Observed Tool", effect="non-mutating"
                    )
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            context.register(DummyTool())
            context.observe("run_started", lambda identity: observer_trace.append("run_started"))
            context.observe("event_emitted", lambda env: observer_trace.append("event_emitted"))
            context.observe("run_finished", lambda identity: observer_trace.append("run_finished"))
            await context.effect(lambda: disposer_trace.append("disposed_first"))
            await context.effect(lambda: disposer_trace.append("disposed_second"))

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    p = ObservablePlugin()
    plugins._catalog["obs_plugin"] = p.manifest
    plugins.install("obs_plugin")
    plugins.trust_plugin("obs_plugin")
    plugins.enable(alpha.agent_id, "obs_plugin")

    host = PluginHost()
    host.register_implementation("obs_plugin", p)

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    provider = MockProvider()
    provider.queue_text_response("Hello from observed agent")

    req = RunRequest(prompt_text="hello", agent_id="alpha")
    events = [env async for env in runner.run(req, provider=provider, cwd=tmp_path)]

    assert events
    assert events[-1].event.type == "turn_complete"

    # Observers verified
    assert "run_started" in observer_trace
    assert "event_emitted" in observer_trace
    assert "run_finished" in observer_trace

    # Disposers executed in reverse order
    assert disposer_trace == ["disposed_second", "disposed_first"]


@pytest.mark.asyncio
async def test_activation_disposal_timeout_diagnosed_and_quarantined_preserving_terminal_truth(
    tmp_path: Path,
) -> None:
    import asyncio

    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_events import PluginDiagnosticEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider
    from mia_tools.base import BaseTool

    PluginManager.clear_quarantine()

    class HangingTool(BaseTool):
        name = "hang_tool"
        description = "Hang Tool"
        parameters = {}
        effect = "non-mutating"

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            return "ok"

    class TimeoutPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="timeout_plugin",
                version="1.0.0",
                display_name="Timeout Plugin",
                description="Times out in cleanup",
                tool_specs=[
                    PluginToolSpec(name="hang_tool", description="Hang Tool", effect="non-mutating")
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            context.register(HangingTool())

            async def hang():
                await asyncio.sleep(10.0)

            await context.effect(hang)

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    tp = TimeoutPlugin()
    plugins._catalog["timeout_plugin"] = tp.manifest
    plugins.install("timeout_plugin")
    plugins.trust_plugin("timeout_plugin")
    plugins.enable(alpha.agent_id, "timeout_plugin")

    host = PluginHost()
    host.register_implementation("timeout_plugin", tp)

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    orig_cleanup = runner._run_cooperative_cleanup

    async def fast_cleanup(runtime, identity, timeout=0.01, **kwargs: Any):
        return await orig_cleanup(runtime, identity, timeout=0.01, **kwargs)

    runner._run_cooperative_cleanup = fast_cleanup  # type: ignore[method-assign]

    provider = MockProvider()
    provider.queue_text_response("Done work successfully")

    req = RunRequest(prompt_text="hello", agent_id="alpha")
    events = [env async for env in runner.run(req, provider=provider, cwd=tmp_path)]

    # Diagnostic event emitted
    diag_envs = [env for env in events if isinstance(env.event, PluginDiagnosticEvent)]
    assert len(diag_envs) == 1
    assert diag_envs[0].event.plugin_id == "timeout_plugin"
    assert "timed out" in diag_envs[0].event.message

    # Terminal truth preserved
    assert events[-1].event.type == "turn_complete"

    # Plugin is now quarantined
    assert PluginManager.is_quarantined("timeout_plugin")

    # Later plan fails closed due to quarantine
    with pytest.raises(ValueError, match="quarantined"):
        host.plan(agents.get_agent(alpha.agent_id), plugins)


def test_event_loop_blocking_python_limit_documented() -> None:
    """Document and test that synchronous blocking code cannot be cancelled cooperatively.

    Mia honestly documents that same-process event-loop-blocking code in trusted Python
    prevents the event loop from running, so cooperative timeouts only apply when callbacks yield.
    """
    import time

    start = time.monotonic()
    time.sleep(0.01)
    duration = time.monotonic() - start
    assert duration >= 0.009


@pytest.mark.asyncio
async def test_plugin_middleware_transform_and_final_validation_agreement(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider
    from mia_middleware.access import ApprovalRequest
    from mia_middleware.pipeline import ToolCallContext
    from mia_tools.base import BaseTool

    received_approval_args: list[dict[str, Any]] = []
    executed_args: list[dict[str, Any]] = []

    class DummySideEffectTool(BaseTool):
        name = "side_tool"
        description = "Side effect tool"
        parameters = {"type": "object", "properties": {"target": {"type": "string"}}}
        effect = "side-effecting"

        async def execute(self, target: str, **kwargs: Any) -> Any:
            executed_args.append({"target": target, **kwargs})
            return f"executed for {target}"

    async def rewrite_middleware(ctx: ToolCallContext, next_fn):
        if ctx.tool_name == "side_tool":
            ctx.arguments["target"] = "rewritten_target"
        return await next_fn()

    class TransformPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="transform_plugin",
                version="1.0.0",
                display_name="Transform Plugin",
                description="Transforms arguments",
                tool_specs=[
                    PluginToolSpec(
                        name="side_tool", description="Side effect tool", effect="side-effecting"
                    )
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            context.register(DummySideEffectTool())
            context.register(rewrite_middleware)

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[], access_policy="approval-required")
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    tp = TransformPlugin()
    plugins._catalog["transform_plugin"] = tp.manifest
    plugins.install("transform_plugin")
    plugins.trust_plugin("transform_plugin")
    plugins.enable(alpha.agent_id, "transform_plugin")

    host = PluginHost()
    host.register_implementation("transform_plugin", tp)

    def approval_cb(req: ApprovalRequest) -> bool:
        received_approval_args.append(dict(req.arguments))
        return True

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    provider = MockProvider()
    provider.queue_tool_call_response(
        tool_name="side_tool",
        arguments={"target": "initial_target"},
    )
    provider.queue_text_response("Done after tool")

    req = RunRequest(prompt_text="do work", agent_id="alpha")
    events = [
        env
        async for env in runner.run(
            req, provider=provider, approval_callback=approval_cb, cwd=tmp_path
        )
    ]

    assert events
    assert events[-1].event.type == "turn_complete"

    # Initial approval callback received initial arguments, final validation re-approved transformed arguments!
    assert received_approval_args == [
        {"target": "initial_target"},
        {"target": "rewritten_target"},
    ]
    # Executor received the transformed arguments!
    assert executed_args == [{"target": "rewritten_target"}]


@pytest.mark.asyncio
async def test_rejected_tool_call_non_execution_and_terminal_error(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider
    from mia_middleware.access import ApprovalRequest
    from mia_tools.base import BaseTool

    executed_calls: list[str] = []

    class CriticalTool(BaseTool):
        name = "critical_tool"
        description = "Critical tool"
        parameters = {"type": "object", "properties": {"action": {"type": "string"}}}
        effect = "side-effecting"

        async def execute(self, action: str, **kwargs: Any) -> Any:
            executed_calls.append(action)
            return "executed"

    class CriticalPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="crit_plugin",
                version="1.0.0",
                display_name="Critical Plugin",
                description="Tests rejection",
                tool_specs=[
                    PluginToolSpec(
                        name="critical_tool", description="Critical tool", effect="side-effecting"
                    )
                ],
            )

        async def activate(self, context: PluginContext) -> None:
            context.register(CriticalTool())

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[], access_policy="approval-required")
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    cp = CriticalPlugin()
    plugins._catalog["crit_plugin"] = cp.manifest
    plugins.install("crit_plugin")
    plugins.trust_plugin("crit_plugin")
    plugins.enable(alpha.agent_id, "crit_plugin")

    host = PluginHost()
    host.register_implementation("crit_plugin", cp)

    def deny_approval(req: ApprovalRequest) -> bool:
        return False  # REJECT!

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    provider = MockProvider()
    provider.queue_tool_call_response(
        tool_name="critical_tool",
        arguments={"action": "delete_all"},
    )

    req = RunRequest(prompt_text="delete everything", agent_id="alpha")
    events = [
        env
        async for env in runner.run(
            req, provider=provider, approval_callback=deny_approval, cwd=tmp_path
        )
    ]

    # Tool executor was NEVER called!
    assert executed_calls == []
    # Tool result indicates rejection error
    tool_results = [e.event for e in events if getattr(e.event, "type", "") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0].is_error is True
    assert "approval denied" in tool_results[0].output


@pytest.mark.asyncio
async def test_plugin_free_agent_compatibility(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    agents = make_agent_manager(tmp_path)
    # Agent with NO plugins
    agents.create_agent("bare_agent", tools=["read_file"])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    provider = MockProvider()
    provider.queue_text_response("Hello from plugin-free agent")

    req = RunRequest(prompt_text="hello", agent_id="bare_agent")
    events = [env async for env in runner.run(req, provider=provider, cwd=tmp_path)]

    assert events
    assert events[-1].event.type == "turn_complete"


@pytest.mark.asyncio
async def test_observer_failure_produces_sanitized_diagnostic_and_preserves_terminal_truth(
    tmp_path: Path,
) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_events import PluginDiagnosticEvent
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    class FaultyObserverPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="faulty_plugin",
                version="1.0.0",
                display_name="Faulty Observer Plugin",
                description="Fails in observer with secret",
            )

        async def activate(self, context: PluginContext) -> None:
            def bad_start_observer(identity: Any) -> None:
                raise RuntimeError("Bearer sk-secret_api_token_123 failed in start observer")

            def bad_finish_observer(identity: Any) -> None:
                raise ValueError("sk-secret_password_456 failed in finish observer")

            context.observe("run_started", bad_start_observer)
            context.observe("run_finished", bad_finish_observer)

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    fp = FaultyObserverPlugin()
    plugins._catalog["faulty_plugin"] = fp.manifest
    plugins.install("faulty_plugin")
    plugins.trust_plugin("faulty_plugin")
    plugins.enable(alpha.agent_id, "faulty_plugin")

    host = PluginHost()
    host.register_implementation("faulty_plugin", fp)

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    runner = AgentRunner(agent_manager=agents, factory=factory)

    provider = MockProvider()
    provider.queue_text_response("Work finished successfully")

    req = RunRequest(prompt_text="do safe work", agent_id="alpha")
    events = [env async for env in runner.run(req, provider=provider, cwd=tmp_path)]

    # 1. Terminal truth is preserved: turn_complete is the final terminal event!
    assert events[-1].event.type == "turn_complete"

    # 2. Sanitized diagnostics are emitted for the failed observers
    diag_events = [env.event for env in events if isinstance(env.event, PluginDiagnosticEvent)]
    assert len(diag_events) >= 1
    for d in diag_events:
        assert d.plugin_id == "faulty_plugin"
        assert "sk-" not in d.error
        assert "[REDACTED]" in d.error


def test_static_catalog_inspection_does_not_execute_installed_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.plugins import MIA_PLUGIN_ENTRY_POINT_GROUP

    load_counter = {"count": 0}

    class FakeDist:
        name = "mia-ext-counter"
        version = "1.0.0"

    class FakeEntryPoint:
        name = "counter_plugin"
        value = "mia_ext_counter:plugin"
        group = MIA_PLUGIN_ENTRY_POINT_GROUP
        dist = FakeDist()

        def load(self) -> object:
            load_counter["count"] += 1

            class MockPlugin:
                @property
                def manifest(self) -> PluginManifest:
                    return PluginManifest(
                        plugin_id="counter_plugin",
                        version="1.0.0",
                        plugin_type="trusted-code",
                        display_name="Counter Plugin",
                        description="Plugin with call counter",
                    )

                async def activate(self, ctx: PluginContext) -> None:
                    pass

            return MockPlugin()

    monkeypatch.setattr(
        "mia_agent.plugins.discover_entry_points",
        lambda: [FakeEntryPoint()],
    )

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    # Static inspection: list_available and get_manifest MUST NOT call ep.load()
    available = plugins.list_available()
    assert any(m.plugin_id == "counter_plugin" for m in available)
    manifest = plugins.get_manifest("counter_plugin")
    assert manifest.plugin_id == "counter_plugin"
    assert manifest.provenance is not None
    assert manifest.provenance.source == "installed"
    assert load_counter["count"] == 0

    # Installing and trusting also must not execute code
    plugins.install("counter_plugin")
    plugins.trust_plugin("counter_plugin")
    plugins.enable(alpha.agent_id, "counter_plugin")
    assert load_counter["count"] == 0

    # Activation DOES call load()
    host = PluginHost()
    plan = host.plan(agents.get_agent("alpha"), plugins)
    assert load_counter["count"] == 0

    import asyncio

    asyncio.run(host.activate(plan, agent=agents.get_agent("alpha"), plugin_manager=plugins))
    assert load_counter["count"] == 1


@pytest.mark.asyncio
async def test_activation_disposers_cleaned_when_factory_build_fails(tmp_path: Path) -> None:
    from mia_agent.agent_runner import AgentRunner
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RunRequest
    from mia_ai.providers.mock import MockProvider

    disposed = []

    class EffectPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="effect_plugin",
                version="1.0.0",
                display_name="Effect Plugin",
                description="Acquires effect with disposer",
            )

        async def activate(self, ctx: PluginContext) -> None:
            await ctx.effect(
                acquire=lambda: "resource_acquired",
                cleanup=lambda: disposed.append("cleaned_up"),
            )

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    ep = EffectPlugin()
    plugins._catalog["effect_plugin"] = ep.manifest
    plugins.install("effect_plugin")
    plugins.trust_plugin("effect_plugin")
    plugins.enable(alpha.agent_id, "effect_plugin")

    host = PluginHost()
    host.register_implementation("effect_plugin", ep)

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)

    # Monkeypatch factory.build to simulate failure after activation succeeds
    def faulty_build(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Simulated build failure")

    factory.build = faulty_build  # type: ignore[method-assign]

    runner = AgentRunner(agent_manager=agents, factory=factory)
    req = RunRequest(prompt_text="test prompt", agent_id="alpha")

    events = [env async for env in runner.run(req, provider=MockProvider(), cwd=tmp_path)]

    # Disposer must have been executed
    assert disposed == ["cleaned_up"]
    # Terminal event must be delivered
    assert len(events) >= 1
    assert events[-1].event.type == "run_error"
    assert "Simulated build failure" in str(events[-1].event.error)


def test_immutable_run_snapshot_and_configuration(tmp_path: Path) -> None:
    from types import MappingProxyType

    from mia_agent.plugin_host import ActivationPlan, PluginActivation, PluginContext

    manifest = PluginManifest(
        plugin_id="test_immut",
        version="1.0.0",
        display_name="Immut Plugin",
        description="Testing immutability",
    )
    plan = ActivationPlan(
        agent_id="test",
        plugins=("test_immut",),
        manifests={"test_immut": manifest},
    )
    assert isinstance(plan.manifests, MappingProxyType)
    with pytest.raises(TypeError):
        plan.manifests["test_immut"] = manifest  # type: ignore[index]

    activation = PluginActivation(agent_id="test")
    assert isinstance(activation.observers, MappingProxyType)
    with pytest.raises(TypeError):
        activation.observers["run_started"] = ()  # type: ignore[index]

    ctx = PluginContext(
        plugin_id="test_immut",
        agent_id="test",
        config={"key": "val", "nested": {"a": 1}},
        data_dir=tmp_path,
        manifest=manifest,
    )
    assert isinstance(ctx.config, MappingProxyType)
    with pytest.raises(TypeError):
        ctx.config["key"] = "new_val"  # type: ignore[index]
    with pytest.raises(TypeError):
        ctx.config["nested"]["a"] = 2  # type: ignore[index]


@pytest.mark.asyncio
async def test_async_context_contributor_appends_to_system_prompt(tmp_path: Path) -> None:
    from mia_agent.plugin_host import PluginContext, PluginHost
    from mia_agent.runtime_factory import AgentRuntimeFactory
    from mia_agent.runtime_models import RuntimeIdentity
    from mia_ai.providers.mock import MockProvider

    class AsyncContextPlugin:
        @property
        def manifest(self) -> PluginManifest:
            return PluginManifest(
                plugin_id="async_ctx_plugin",
                version="1.0.0",
                display_name="Async Ctx Plugin",
                description="Contributes async context",
            )

        async def activate(self, ctx: PluginContext) -> None:
            async def get_async_context() -> str:
                return "Contributed Async Context Data"

            ctx.register(get_async_context)

    agents = make_agent_manager(tmp_path)
    alpha = agents.create_agent("alpha", tools=[])
    plugins = PluginManager(agent_manager=agents, plugins_dir=tmp_path / "plugins")

    acp = AsyncContextPlugin()
    plugins._catalog["async_ctx_plugin"] = acp.manifest
    plugins.install("async_ctx_plugin")
    plugins.trust_plugin("async_ctx_plugin")
    plugins.enable(alpha.agent_id, "async_ctx_plugin")

    host = PluginHost()
    host.register_implementation("async_ctx_plugin", acp)

    factory = AgentRuntimeFactory(agent_manager=agents, plugin_manager=plugins, plugin_host=host)
    plan = host.plan(agents.get_agent("alpha"), plugins)
    activation = await host.activate(plan, agent=agents.get_agent("alpha"), plugin_manager=plugins)

    runtime = factory.build(
        identity=RuntimeIdentity(
            run_id="test_run",
            task_id="test_task",
            agent_id="alpha",
            session_id="test_session",
        ),
        provider=MockProvider(),
        activation=activation,
    )

    assert "Contributed Async Context Data" in runtime.harness.system_prompt
