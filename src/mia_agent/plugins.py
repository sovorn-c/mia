"""Bundled Plugin contracts and explicit local installation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mia_agent.agents.storage import atomic_write_json

if TYPE_CHECKING:
    from mia_agent.agents.manager import AgentManager

PluginEffect = Literal["non-mutating", "side-effecting"]
_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
CORE_PLUGIN_API_VERSION = 1


def normalize_plugin_id(value: str) -> str:
    """Normalize a Plugin ID and reject values unsafe for local state paths."""
    if not isinstance(value, str):
        raise ValueError("Plugin ID must be text")
    candidate = value.strip().lower()
    if not candidate or "/" in candidate or "\\" in candidate or candidate in {".", ".."}:
        raise ValueError("Plugin ID must be a non-blank path-safe identifier")
    if not _PLUGIN_ID_RE.fullmatch(candidate):
        raise ValueError("Plugin ID must use letters, numbers, hyphens, and underscores")
    return candidate


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


class PluginManifest(BaseModel):
    """Strict, serializable description of one bundled Plugin."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    plugin_id: str
    version: str
    api_version: int = CORE_PLUGIN_API_VERSION
    display_name: str
    description: str
    tool_specs: list[PluginToolSpec] = Field(default_factory=list)

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

    def enable(self, agent_id: str, plugin_id: str) -> Any:
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
        agent = inspection["agent"]
        if manifest.plugin_id in agent.plugins:
            return agent
        self.agent_manager.save_agent(
            agent.model_copy(update={"plugins": [*agent.plugins, manifest.plugin_id]})
        )
        return self.agent_manager.get_agent(agent.agent_id)

    def enable_for_agent(self, agent_id: str, plugin_id: str) -> Any:
        """Explicit spelling for callers managing per-Agent Plugin state."""
        return self.enable(agent_id, plugin_id)

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
            tools.extend(
                plugin.build_tools(
                    agent_id=agent.agent_id,
                    data_dir=self.agent_manager.agent_home(agent.agent_id)
                    / "plugins"
                    / manifest.plugin_id,
                    config=getattr(agent, "plugin_config", {}).get(manifest.plugin_id, {}),
                )
            )
        return tools

    @staticmethod
    def _notes_manifest() -> PluginManifest:
        return PluginManifest(
            plugin_id="notes",
            version="1.0.0",
            display_name="Notes",
            description="Private Agent-owned local notes.",
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
    "InstalledPlugin",
    "PluginEffect",
    "NotesPlugin",
    "PluginManager",
    "PluginManifest",
    "PluginToolSpec",
    "normalize_plugin_id",
]
