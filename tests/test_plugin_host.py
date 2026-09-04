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

    # Ensure no agents or sessions mutated
    assert agents.list_agents() == []
