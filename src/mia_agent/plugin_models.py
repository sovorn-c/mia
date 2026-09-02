"""Validated models for bundled Plugins and Agent Templates."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mia_agent.agents.model import AccessLevel, normalize_plugin_id

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


__all__ = [
    "CORE_PLUGIN_API_VERSION",
    "AgentTemplate",
    "InstalledPlugin",
    "PluginEffect",
    "PluginManifest",
    "PluginToolSpec",
]
