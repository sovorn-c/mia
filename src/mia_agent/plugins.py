"""Bundled Plugin catalog and explicit local installation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mia_agent.agents import BUILTIN_AGENTS
from mia_agent.agents.model import Agent, normalize_plugin_id
from mia_agent.agents.storage import atomic_write_json
from mia_agent.plugin_catalog import NotesPlugin
from mia_agent.plugin_models import (
    CORE_PLUGIN_API_VERSION,
    AgentTemplate,
    InstalledPlugin,
    PluginEffect,
    PluginManifest,
    PluginProvenance,
    PluginToolSpec,
    PluginTrust,
    PluginTrustStatus,
    StaticSkill,
    _validate_secret_free,
)
from mia_tools.base import BaseTool

if TYPE_CHECKING:
    from mia_agent.agents.manager import AgentManager


MIA_PLUGIN_ENTRY_POINT_GROUP = "mia.plugins"


def discover_entry_points() -> list[Any]:
    """Discover installed Plugin entry points from the allowlisted Mia group."""
    from importlib.metadata import entry_points

    return list(entry_points(group=MIA_PLUGIN_ENTRY_POINT_GROUP))


_QUARANTINED_PLUGINS: set[str] = set()


class PluginManager:
    """Manage the bundled and discovered catalog and explicit local installation/trust state."""

    @classmethod
    def quarantine_plugin(cls, plugin_id: str) -> None:
        """Quarantine a plugin until process restart due to cleanup timeout or critical failure."""
        _QUARANTINED_PLUGINS.add(normalize_plugin_id(plugin_id))

    @classmethod
    def is_quarantined(cls, plugin_id: str) -> bool:
        """Check if a plugin is quarantined."""
        return normalize_plugin_id(plugin_id) in _QUARANTINED_PLUGINS

    @classmethod
    def clear_quarantine(cls) -> None:
        """Reset quarantined plugins (primarily for test isolation)."""
        _QUARANTINED_PLUGINS.clear()

    def __init__(
        self,
        agent_manager: AgentManager | None = None,
        *,
        plugins_dir: Path | None = None,
    ) -> None:
        if agent_manager is None:
            from mia_agent.agents import AgentManager as CanonicalAgentManager

            agent_manager = CanonicalAgentManager()
        self.agent_manager = agent_manager
        default_dir = self.agent_manager.agents_dir.parent / "plugins"
        self.plugins_dir = (plugins_dir or default_dir).expanduser().resolve()
        self.state_path = self.plugins_dir / "installed.json"
        self.trust_path = self.plugins_dir / "trust.json"
        self._catalog: dict[str, PluginManifest] = {"notes": NotesPlugin().manifest}

    def list_trusted(self) -> list[str]:
        """Read explicitly trusted Plugin IDs."""
        if not self.trust_path.exists():
            return []
        try:
            payload = json.loads(self.trust_path.read_text(encoding="utf-8"))
            trusted = payload.get("trusted", [])
            if not isinstance(trusted, list):
                return []
            return [normalize_plugin_id(p) for p in trusted]
        except Exception:
            return []

    def trust_plugin(self, plugin_id: str) -> None:
        """Grant explicit trust to an installed-code Plugin."""
        norm_id = normalize_plugin_id(plugin_id)
        trusted = set(self.list_trusted())
        trusted.add(norm_id)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.trust_path, {"trusted": sorted(trusted)})

    def revoke_plugin_trust(self, plugin_id: str) -> None:
        """Revoke explicit trust from an installed-code Plugin."""
        norm_id = normalize_plugin_id(plugin_id)
        trusted = set(self.list_trusted())
        trusted.discard(norm_id)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.trust_path, {"trusted": sorted(trusted)})

    def is_trusted(self, plugin_id: str) -> bool:
        """Check whether a Plugin has effective trust."""
        norm_id = normalize_plugin_id(plugin_id)
        if norm_id == "notes":
            return True
        manifest = self.get_manifest(norm_id)
        if manifest.provenance and manifest.provenance.source == "bundled":
            return True
        if manifest.plugin_type == "declarative":
            return True
        return norm_id in self.list_trusted()

    def _get_effective_catalog(self) -> dict[str, PluginManifest]:
        catalog: dict[str, PluginManifest] = dict(self._catalog)
        trusted_ids = set(self.list_trusted())
        try:
            discovered_eps = discover_entry_points()
        except Exception:
            discovered_eps = []

        for ep in discovered_eps:
            norm_id = normalize_plugin_id(getattr(ep, "name", ""))
            if norm_id in catalog:
                continue
            try:
                plugin_obj = ep.load()
                manifest_obj = getattr(plugin_obj, "manifest", plugin_obj)
                if callable(manifest_obj):
                    manifest_obj = manifest_obj()
                if not isinstance(manifest_obj, PluginManifest):
                    continue
                dist = getattr(ep, "dist", None)
                pkg_name = getattr(dist, "name", None) if dist else None
                pkg_ver = getattr(dist, "version", None) if dist else None
                ep_val = getattr(ep, "value", None)
                provenance = PluginProvenance(
                    source="installed",
                    package_name=pkg_name,
                    package_version=pkg_ver,
                    entry_point=ep_val,
                )
                is_explicit_trusted = norm_id in trusted_ids
                if manifest_obj.plugin_type == "declarative":
                    trust = PluginTrust(
                        trust_class="declarative",
                        status="declarative",
                        explicit=True,
                        message="Declarative static catalog resources.",
                    )
                else:
                    trust = PluginTrust(
                        trust_class="trusted-code",
                        status="trusted" if is_explicit_trusted else "untrusted",
                        explicit=is_explicit_trusted,
                        message="Explicit trust granted"
                        if is_explicit_trusted
                        else "Installed code requires explicit administrator trust before enablement.",
                    )
                catalog[norm_id] = manifest_obj.model_copy(
                    update={"provenance": provenance, "trust": trust}
                )
            except Exception:
                continue

        # Dynamically update trust status for catalog entries
        for key, manifest in list(catalog.items()):
            if key == "notes" or (manifest.provenance and manifest.provenance.source == "bundled"):
                continue
            if manifest.plugin_type == "declarative":
                continue
            is_explicit_trusted = key in trusted_ids
            status: PluginTrustStatus = "trusted" if is_explicit_trusted else "untrusted"
            msg = (
                "Explicit trust granted"
                if is_explicit_trusted
                else "Installed code requires explicit administrator trust before enablement."
            )
            trust = PluginTrust(
                trust_class=manifest.plugin_type,
                status=status,
                explicit=is_explicit_trusted,
                message=msg,
            )
            catalog[key] = manifest.model_copy(update={"trust": trust})
        return catalog

    def list_available(self) -> list[PluginManifest]:
        """List bundled and discovered Plugin manifests in stable ID order."""
        catalog = self._get_effective_catalog()
        return [catalog[key] for key in sorted(catalog)]

    def list_installed(self) -> list[InstalledPlugin]:
        """Read explicit installation records, failing closed on malformed state."""
        if not self.state_path.exists():
            return []
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            records = payload["plugins"]
            if not isinstance(records, list):
                raise TypeError("plugins must be a list")
            installed = [InstalledPlugin.model_validate(record) for record in records]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Installed Plugin state is invalid: {exc}") from exc
        if len({record.plugin_id for record in installed}) != len(installed):
            raise ValueError("Installed Plugin state contains duplicate Plugin IDs")
        return installed

    def get_manifest(self, plugin_id: str) -> PluginManifest:
        """Return one manifest or an actionable unknown-ID error."""
        key = normalize_plugin_id(plugin_id)
        catalog = self._get_effective_catalog()
        try:
            return catalog[key]
        except KeyError as exc:
            available = ", ".join(sorted(catalog))
            raise ValueError(
                f"Plugin '{key}' is unavailable. Available Plugins: {available}"
            ) from exc

    def install(self, plugin_id: str) -> InstalledPlugin:
        """Install one Plugin idempotently without network or code loading."""
        manifest = self.get_manifest(plugin_id)
        records = self.list_installed()
        existing = next(
            (record for record in records if record.plugin_id == manifest.plugin_id), None
        )
        if existing is not None:
            if existing != InstalledPlugin(
                plugin_id=manifest.plugin_id,
                version=manifest.version,
                api_version=manifest.api_version,
            ):
                raise ValueError(f"Installed Plugin '{manifest.plugin_id}' has incompatible state")
            return existing
        installed = InstalledPlugin(
            plugin_id=manifest.plugin_id,
            version=manifest.version,
            api_version=manifest.api_version,
        )
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.state_path,
            {"plugins": [record.model_dump(mode="json") for record in [*records, installed]]},
        )
        return installed

    def enable(self, agent_id: str, plugin_id: str) -> Agent:
        """Enable an installed Plugin for one persisted, non-built-in Agent."""
        manifest = self.get_manifest(plugin_id)
        installed = {record.plugin_id: record for record in self.list_installed()}
        record = installed.get(manifest.plugin_id)
        if record is None:
            raise ValueError(f"Plugin '{manifest.plugin_id}' is not installed; install it first")
        if record.version != manifest.version or record.api_version != manifest.api_version:
            raise ValueError(f"Installed Plugin '{manifest.plugin_id}' is incompatible")

        if manifest.plugin_type == "trusted-code" and not self.is_trusted(manifest.plugin_id):
            raise ValueError(
                f"Plugin '{manifest.plugin_id}' is not trusted; explicit administrator trust is required before enablement"
            )

        agent = self.agent_manager.get_agent(agent_id)
        if agent.agent_id in BUILTIN_AGENTS:
            raise ValueError("Cannot enable Plugins for immutable built-in Agents")
        if manifest.plugin_id in agent.plugins:
            return agent
        updated = Agent.model_validate(
            agent.model_dump(mode="python") | {"plugins": [*agent.plugins, manifest.plugin_id]}
        )
        self.agent_manager.save_agent(updated)
        return self.agent_manager.get_agent(agent.agent_id)

    def configure(self, agent_id: str, plugin_id: str, config: dict[str, Any]) -> Agent:
        """Validate and persist configuration for an enabled Plugin."""
        manifest = self.get_manifest(plugin_id)
        self._installed_record(manifest)
        agent = self.agent_manager.get_agent(agent_id)
        if agent.agent_id in BUILTIN_AGENTS:
            raise ValueError("Cannot configure Plugins for immutable built-in Agents")
        if manifest.plugin_id not in agent.plugins:
            raise ValueError(
                f"Plugin '{manifest.plugin_id}' is not enabled for Agent '{agent.agent_id}'"
            )
        if manifest.plugin_id == "notes":
            self._validate_notes_config(config)
        updated_config = dict(agent.plugin_config)
        updated_config[manifest.plugin_id] = dict(config)
        updated = Agent.model_validate(
            agent.model_dump(mode="python") | {"plugin_config": updated_config}
        )
        self.agent_manager.save_agent(updated)
        return self.agent_manager.get_agent(agent.agent_id)

    def disable(self, agent_id: str, plugin_id: str) -> Agent:
        """Disable one Plugin for later Runs while retaining its configuration and data."""
        manifest = self.get_manifest(plugin_id)
        self._installed_record(manifest)
        agent = self.agent_manager.get_agent(agent_id)
        if agent.agent_id in BUILTIN_AGENTS:
            raise ValueError("Cannot disable Plugins for immutable built-in Agents")
        if manifest.plugin_id not in agent.plugins:
            return agent
        updated = Agent.model_validate(
            agent.model_dump(mode="python")
            | {"plugins": [item for item in agent.plugins if item != manifest.plugin_id]}
        )
        self.agent_manager.save_agent(updated)
        return self.agent_manager.get_agent(agent.agent_id)

    def list_templates(self) -> list[AgentTemplate]:
        """List bundled Agent Templates without installing or executing them."""
        templates = [
            template for manifest in self.list_available() for template in manifest.templates
        ]
        return sorted(templates, key=lambda template: template.template_id)

    def get_template(self, template_id: str) -> AgentTemplate:
        """Return one bundled Template or an actionable unknown-ID error."""
        key = normalize_plugin_id(template_id)
        for template in self.list_templates():
            if template.template_id == key:
                return template
        available = ", ".join(template.template_id for template in self.list_templates())
        raise ValueError(f"Agent Template '{key}' is unavailable. Available Templates: {available}")

    def list_skills(self) -> list[StaticSkill]:
        """List static Skills declared by available Plugins without executing code."""
        skills = [skill for manifest in self.list_available() for skill in manifest.skills]
        return sorted(skills, key=lambda skill: skill.skill_id)

    def get_skill(self, skill_id: str) -> StaticSkill:
        """Return one declared static Skill or an actionable unknown-ID error."""
        key = normalize_plugin_id(skill_id)
        for skill in self.list_skills():
            if skill.skill_id == key:
                return skill
        available = ", ".join(skill.skill_id for skill in self.list_skills())
        raise ValueError(f"Static Skill '{key}' is unavailable. Available Skills: {available}")

    def instantiate(self, template_id: str, agent_id: str) -> Agent:
        """Create a fresh Agent from a bundled Template after all preflight checks."""
        template = self.get_template(template_id)
        manifests = [self.get_manifest(plugin_id) for plugin_id in template.required_plugins]
        for manifest in manifests:
            self._installed_record(manifest)
            if manifest.plugin_id == "notes":
                self._validate_notes_config(template.plugin_config.get("notes", {}))
        return self.agent_manager.create_agent(
            agent_id,
            display_name=template.display_name,
            description=template.description,
            instructions=template.instructions,
            access_policy=template.access_policy,
            tools=list(template.tools),
            plugins=list(template.required_plugins),
            plugin_config={key: dict(value) for key, value in template.plugin_config.items()},
            full_access_confirmed=False,
        )

    def _installed_record(self, manifest: PluginManifest) -> InstalledPlugin:
        for record in self.list_installed():
            if record.plugin_id == manifest.plugin_id:
                if record.version != manifest.version or record.api_version != manifest.api_version:
                    raise ValueError(f"Installed Plugin '{manifest.plugin_id}' is incompatible")
                return record
        raise ValueError(f"Plugin '{manifest.plugin_id}' is not installed; install it first")

    @staticmethod
    def _validate_notes_config(config: dict[str, Any]) -> None:
        if set(config) - {"notebook_name"}:
            raise ValueError("Notes configuration only supports notebook_name")
        if "notebook_name" not in config:
            return
        name = config["notebook_name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("notebook_name must be non-blank text")
        if len(name.strip()) > 100 or "/" in name or "\\" in name:
            raise ValueError("notebook_name must be a short display name, not a path")
        _validate_secret_free(name, "notebook_name")

    def resolve_tools(self, agent: Agent) -> list[BaseTool]:
        """Build every enabled Plugin Tool against the resolved Agent boundary."""
        tools: list[BaseTool] = []
        seen_names: set[str] = set()
        for plugin_id in sorted(set(agent.plugins)):
            resolved = self._resolve_plugin_tools(agent, plugin_id)
            for tool in resolved:
                if tool.name in seen_names:
                    raise ValueError(
                        f"Plugin contribution collision: duplicate Tool name '{tool.name}'"
                    )
                seen_names.add(tool.name)
            tools.extend(resolved)
        return tools

    def _resolve_plugin_tools(self, agent: Agent, plugin_id: str) -> list[BaseTool]:
        manifest = self.get_manifest(plugin_id)
        if self.is_quarantined(manifest.plugin_id):
            raise ValueError(
                f"Plugin '{manifest.plugin_id}' is quarantined due to previous cleanup timeout"
            )
        self._installed_record(manifest)
        plugin = NotesPlugin() if manifest.plugin_id == "notes" else None
        if plugin is None:
            raise ValueError(f"Plugin '{manifest.plugin_id}' has no bundled implementation")
        plugin_tools = plugin.build_tools(
            agent_id=agent.agent_id,
            data_dir=self.agent_manager.agent_home(agent.agent_id) / "plugins" / manifest.plugin_id,
            config=getattr(agent, "plugin_config", {}).get(manifest.plugin_id, {}),
        )
        self._validate_tool_contributions(manifest, plugin_tools)
        return plugin_tools

    @staticmethod
    def _validate_tool_contributions(
        manifest: PluginManifest, plugin_tools: list[BaseTool]
    ) -> None:
        expected = {spec.name: spec.effect for spec in manifest.tool_specs}
        actual = [getattr(tool, "name", "") for tool in plugin_tools]
        if set(actual) != set(expected) or len(actual) != len(expected):
            raise ValueError(f"Plugin '{manifest.plugin_id}' returned undeclared Tools")
        for tool in plugin_tools:
            if getattr(tool, "plugin_id", None) != manifest.plugin_id:
                raise ValueError(f"Plugin '{manifest.plugin_id}' returned unattributed Tools")
            if getattr(tool, "effect", None) != expected[tool.name]:
                raise ValueError(
                    f"Plugin '{manifest.plugin_id}' returned a Tool with an undeclared effect"
                )


__all__ = [
    "CORE_PLUGIN_API_VERSION",
    "MIA_PLUGIN_ENTRY_POINT_GROUP",
    "AgentTemplate",
    "InstalledPlugin",
    "PluginEffect",
    "NotesPlugin",
    "PluginManager",
    "PluginManifest",
    "PluginProvenance",
    "PluginToolSpec",
    "PluginTrust",
    "PluginTrustStatus",
    "StaticSkill",
    "discover_entry_points",
    "normalize_plugin_id",
]
