"""Bundled Plugin contracts and explicit local installation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mia_agent.agents.model import AccessLevel, Agent, normalize_plugin_id
from mia_agent.agents.storage import atomic_write_json

if TYPE_CHECKING:
    from mia_agent.agents.manager import AgentManager

PluginEffect = Literal["non-mutating", "side-effecting"]
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_SECRET_KEY_PARTS = ("api_key", "apikey", "token", "secret", "authorization", "password")
_SECRET_VALUE_RE = re.compile(r"(?i)(?:bearer\s+|sk-|ghp_|xoxb-)[^\s,;]+")
CORE_PLUGIN_API_VERSION = 1


def _validate_secret_free(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower().replace("-", "_")
            if any(part in key_text for part in _SECRET_KEY_PARTS):
                raise ValueError(f"{path} contains credential-like field '{key}'")
            _validate_secret_free(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, nested in enumerate(value):
            _validate_secret_free(nested, f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        raise ValueError(f"{path} contains a secret-like value")


class PluginToolSpec(BaseModel):
    """Validated metadata for one Plugin-contributed Tool."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    effect: PluginEffect

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError(
                "Plugin Tool names must use lowercase letters, numbers, and underscores"
            )
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Plugin Tool descriptions must not be blank")
        return value


class AgentTemplate(BaseModel):
    """Strict allowlist of reusable public Agent defaults."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    version: str
    display_name: str
    description: str
    instructions: str
    access_policy: AccessLevel = "approval-required"
    tools: list[str] = Field(default_factory=list)
    required_plugins: list[str] = Field(default_factory=list)
    plugin_config: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, value: str) -> str:
        return normalize_plugin_id(value)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        value = value.strip()
        if not _VERSION_RE.fullmatch(value):
            raise ValueError("Template version must use MAJOR.MINOR.PATCH")
        return value

    @field_validator("display_name", "description", "instructions")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Template text fields must not be blank")
        return value

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: list[str]) -> list[str]:
        tools = [tool.strip() for tool in value]
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*", tool) for tool in tools):
            raise ValueError(
                "Template Tool names must use lowercase letters, numbers, and underscores"
            )
        if len(tools) != len(set(tools)):
            raise ValueError("Template Tool names contain duplicates")
        return tools

    @field_validator("plugin_config")
    @classmethod
    def validate_plugin_config(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for plugin_id, config in value.items():
            key = normalize_plugin_id(plugin_id)
            if key in normalized:
                raise ValueError(f"Template Plugin configuration contains duplicate '{key}'")
            _validate_secret_free(config, f"plugin_config.{key}")
            normalized[key] = config
        return normalized

    @field_validator("required_plugins")
    @classmethod
    def validate_required_plugins(cls, value: list[str]) -> list[str]:
        normalized = [normalize_plugin_id(plugin_id) for plugin_id in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Template Plugin requirements contain duplicates")
        return normalized

    @field_validator("access_policy")
    @classmethod
    def reject_full_access(cls, value: AccessLevel) -> AccessLevel:
        if value == "full-access":
            raise ValueError("Agent Templates cannot request full-access")
        return value

    @model_validator(mode="after")
    def validate_configuration_requirements(self) -> AgentTemplate:
        unknown = set(self.plugin_config) - set(self.required_plugins)
        if unknown:
            raise ValueError("Template Plugin configuration has an unmet required Plugin")
        return self


class PluginManifest(BaseModel):
    """Strict, serializable description of one bundled Plugin."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    plugin_id: str
    version: str
    api_version: int = CORE_PLUGIN_API_VERSION
    display_name: str
    description: str
    tool_specs: list[PluginToolSpec] = Field(default_factory=list)
    templates: list[AgentTemplate] = Field(default_factory=list)

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        return normalize_plugin_id(value)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        value = value.strip()
        if not _VERSION_RE.fullmatch(value):
            raise ValueError("Plugin version must use MAJOR.MINOR.PATCH")
        return value

    @field_validator("display_name", "description")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Plugin display name and description must not be blank")
        return value

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: int) -> int:
        if value != CORE_PLUGIN_API_VERSION:
            raise ValueError(f"Unsupported Plugin API version: {value}")
        return value

    @model_validator(mode="after")
    def validate_tool_names(self) -> PluginManifest:
        names = [tool.name for tool in self.tool_specs]
        if len(names) != len(set(names)):
            raise ValueError(f"Plugin '{self.plugin_id}' declares duplicate Tool names")
        template_ids = [template.template_id for template in self.templates]
        if len(template_ids) != len(set(template_ids)):
            raise ValueError(f"Plugin '{self.plugin_id}' declares duplicate Template IDs")
        return self

    @property
    def tools(self) -> list[str]:
        """Return declared Tool names for inspection and capability checks."""
        return [tool.name for tool in self.tool_specs]


class InstalledPlugin(BaseModel):
    """Durable local record for an explicitly installed bundled Plugin."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    version: str
    api_version: int = CORE_PLUGIN_API_VERSION

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        return normalize_plugin_id(value)


class NotesPlugin:
    """Bundled Notes contribution used by the initial Plugin vertical slice."""

    plugin_id = "notes"

    @property
    def manifest(self) -> PluginManifest:
        return PluginManager._notes_manifest()

    def build_tools(
        self,
        *,
        agent_id: str,
        data_dir: Path,
        config: dict[str, Any],
    ) -> list[Any]:
        """Build Notes Tools against the one data root selected by Mia Core."""
        del agent_id, config
        from mia_tools.notes import NoteCreateTool, NoteListTool, NoteReadTool

        return [
            NoteCreateTool(data_dir),
            NoteListTool(data_dir),
            NoteReadTool(data_dir),
        ]


class PluginManager:
    """Manage the small bundled catalog and explicit local installation state."""

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
        self._catalog = {"notes": NotesPlugin().manifest}

    def list_available(self) -> list[PluginManifest]:
        """List bundled Plugin manifests in stable ID order."""
        return [self._catalog[key] for key in sorted(self._catalog)]

    def list_installed(self) -> list[InstalledPlugin]:
        """Read explicit installation records, failing closed on malformed state."""
        if not self.state_path.exists():
            return []
        try:
            import json

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
        """Return one bundled manifest or an actionable unknown-ID error."""
        key = normalize_plugin_id(plugin_id)
        try:
            return self._catalog[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._catalog))
            raise ValueError(
                f"Plugin '{key}' is unavailable. Available Plugins: {available}"
            ) from exc

    def install(self, plugin_id: str) -> InstalledPlugin:
        """Install one bundled Plugin idempotently without network or code loading."""
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

        inspection = self.agent_manager.inspect_agent(agent_id)
        if inspection["source"] == "builtin":
            raise ValueError("Cannot enable Plugins for immutable built-in Agents")
        agent = Agent.model_validate(inspection["agent"])
        if manifest.plugin_id in agent.plugins:
            return agent
        updated = Agent.model_validate(
            agent.model_dump(mode="python") | {"plugins": [*agent.plugins, manifest.plugin_id]}
        )
        self.agent_manager.save_agent(updated)
        return self.agent_manager.get_agent(agent.agent_id)

    def enable_for_agent(self, agent_id: str, plugin_id: str) -> Agent:
        """Explicit spelling for callers managing per-Agent Plugin state."""
        return self.enable(agent_id, plugin_id)

    def configure(self, agent_id: str, plugin_id: str, config: dict[str, Any]) -> Agent:
        """Validate and persist configuration for an enabled Plugin."""
        manifest = self.get_manifest(plugin_id)
        self._installed_record(manifest)
        inspection = self.agent_manager.inspect_agent(agent_id)
        if inspection["source"] == "builtin":
            raise ValueError("Cannot configure Plugins for immutable built-in Agents")
        agent = Agent.model_validate(inspection["agent"])
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
        inspection = self.agent_manager.inspect_agent(agent_id)
        if inspection["source"] == "builtin":
            raise ValueError("Cannot disable Plugins for immutable built-in Agents")
        agent = Agent.model_validate(inspection["agent"])
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

    def create_from_template(self, template_id: str, agent_id: str) -> Agent:
        """Explicit spelling for Template instantiation callers."""
        return self.instantiate(template_id, agent_id)

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

    def resolve_tools(self, agent: Any) -> list[Any]:
        """Build every enabled Plugin Tool against the resolved Agent boundary."""
        installed = {record.plugin_id: record for record in self.list_installed()}
        tools: list[Any] = []
        for plugin_id in agent.plugins:
            manifest = self.get_manifest(plugin_id)
            record = installed.get(manifest.plugin_id)
            if record is None:
                raise ValueError(
                    f"Plugin '{manifest.plugin_id}' is not installed; install it first"
                )
            if record.version != manifest.version or record.api_version != manifest.api_version:
                raise ValueError(f"Installed Plugin '{manifest.plugin_id}' is incompatible")
            plugin = NotesPlugin() if manifest.plugin_id == "notes" else None
            if plugin is None:
                raise ValueError(f"Plugin '{manifest.plugin_id}' has no bundled implementation")
            plugin_tools = plugin.build_tools(
                agent_id=agent.agent_id,
                data_dir=self.agent_manager.agent_home(agent.agent_id)
                / "plugins"
                / manifest.plugin_id,
                config=getattr(agent, "plugin_config", {}).get(manifest.plugin_id, {}),
            )
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
            tools.extend(plugin_tools)
        return tools

    @staticmethod
    def _notes_manifest() -> PluginManifest:
        return PluginManifest(
            plugin_id="notes",
            version="1.0.0",
            display_name="Notes",
            description="Private Agent-owned local notes.",
            templates=[
                AgentTemplate(
                    template_id="notes-agent",
                    version="1.0.0",
                    display_name="Notes Agent",
                    description="A focused Agent for private local notes.",
                    instructions="You are a careful Agent for creating and retrieving private notes.",
                    tools=[],
                    required_plugins=["notes"],
                    plugin_config={"notes": {"notebook_name": "Personal"}},
                )
            ],
            tool_specs=[
                PluginToolSpec(
                    name="note_create",
                    description="Create a private note for this Agent.",
                    effect="side-effecting",
                ),
                PluginToolSpec(
                    name="note_list",
                    description="List private notes owned by this Agent.",
                    effect="non-mutating",
                ),
                PluginToolSpec(
                    name="note_read",
                    description="Read one private note owned by this Agent.",
                    effect="non-mutating",
                ),
            ],
        )


__all__ = [
    "CORE_PLUGIN_API_VERSION",
    "AgentTemplate",
    "InstalledPlugin",
    "PluginEffect",
    "NotesPlugin",
    "PluginManager",
    "PluginManifest",
    "PluginToolSpec",
    "normalize_plugin_id",
]
