"""Canonical durable Agent definitions and access vocabulary."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AccessLevel = Literal["read-only", "approval-required", "full-access"]

_SECRET_KEY_PARTS = ("api_key", "apikey", "token", "secret", "authorization", "password")
_SECRET_VALUE_RE = re.compile(r"(?i)(?:bearer\s+|sk-|ghp_|xoxb-)[^\s,;]+")
_AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def normalize_agent_id(value: str) -> str:
    """Normalize a user-facing Agent ID and reject values unsafe for path use."""
    if not isinstance(value, str):
        raise ValueError("Agent ID must be text")
    candidate = value.strip().lower()
    if not candidate:
        raise ValueError("Agent ID must not be blank")
    if "/" in candidate or "\\" in candidate or candidate in {".", ".."}:
        raise ValueError(
            f"Unsafe Agent ID '{value}': path separators and traversal are not allowed"
        )
    candidate = re.sub(r"\s+", "-", candidate)
    if not _AGENT_ID_RE.fullmatch(candidate):
        raise ValueError(
            f"Unsafe Agent ID '{value}': use letters, numbers, hyphens, and underscores"
        )
    return candidate


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


def _validate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Reject credential-shaped metadata before it can be persisted or displayed."""

    def visit(item: Any, path: str = "metadata") -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                key_text = str(key).lower().replace("-", "_")
                if any(part in key_text for part in _SECRET_KEY_PARTS):
                    raise ValueError(f"{path} contains credential-like field '{key}'")
                visit(nested, f"{path}.{key}")
        elif isinstance(item, (list, tuple, set, frozenset)):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")
        elif isinstance(item, str) and _SECRET_VALUE_RE.search(item):
            raise ValueError(f"{path} contains a secret-like value")

    visit(value)
    return value


class Agent(BaseModel):
    """Validated, durable identity and configuration for one Agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_name: str = ""
    description: str = ""
    instructions: str = "You are Mia, a helpful local AI Agent."
    model: str | None = None
    provider: str | None = None
    account: str | None = None
    temperature: float = 0.7
    max_steps_per_turn: int = 25
    tools: list[str] | None = None
    plugins: list[str] = Field(default_factory=list)
    plugin_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    access_policy: AccessLevel = "approval-required"
    full_access_confirmed: bool = False
    delegation_targets: list[str] = Field(default_factory=list)
    memory_path: str | None = None
    channel_identity: str | None = None
    middlewares: list[str] = Field(
        default_factory=lambda: ["security_guard", "audit_log", "cost_budget"]
    )
    compaction_threshold_ratio: float | None = None
    context_window_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        return normalize_agent_id(value)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("delegation_targets")
    @classmethod
    def validate_delegation_targets(cls, value: list[str]) -> list[str]:
        return [normalize_agent_id(target) for target in value]

    @field_validator("plugins")
    @classmethod
    def validate_plugins(cls, value: list[str]) -> list[str]:
        normalized = [normalize_plugin_id(plugin_id) for plugin_id in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Agent Plugin IDs contain duplicates")
        return normalized

    @field_validator("plugin_config")
    @classmethod
    def validate_plugin_config(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for plugin_id, config in value.items():
            key = normalize_plugin_id(plugin_id)
            if key in normalized:
                raise ValueError(f"Agent Plugin configuration contains duplicate '{key}'")
            normalized[key] = _validate_metadata(config)
        return normalized

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_metadata(value)

    @model_validator(mode="after")
    def set_default_display_name(self) -> Agent:
        if not self.display_name:
            self.display_name = self.agent_id.replace("_", " ").replace("-", " ").title()
        return self


BUILTIN_AGENTS: dict[str, Agent] = {
    "mia": Agent(
        agent_id="mia",
        display_name="Mia",
        description="Your general-purpose personal Agent for local work and reasoning.",
        instructions=(
            "You are Mia, a helpful general-purpose local AI Agent. "
            "Reason clearly, protect user data, and ask before side effects."
        ),
        tools=["read_file", "write_file", "edit_file", "bash"],
        access_policy="approval-required",
    ),
    "coding": Agent(
        agent_id="coding",
        display_name="Coding",
        description="Full-stack software engineering Agent with file editing and shell tools.",
        instructions=(
            "You are Mia, an expert AI software engineer. You write clean, robust code, "
            "follow test-driven development, inspect files before editing, and explain changes clearly."
        ),
        temperature=0.2,
        tools=["read_file", "write_file", "edit_file", "bash"],
        access_policy="approval-required",
    ),
    "architect": Agent(
        agent_id="architect",
        display_name="Mia Architect",
        description="Read-only system architect for exploration, ADRs, and design reviews.",
        instructions=(
            "You are Mia Architect, a Principal Software Architect. You analyze complex system designs, "
            "evaluate trade-offs, draft ADRs, and review codebases without modifying files."
        ),
        temperature=0.4,
        tools=["read_file"],
        access_policy="read-only",
    ),
    "minimal": Agent(
        agent_id="minimal",
        display_name="Minimal",
        description="Fast direct conversation with no enabled Tools.",
        instructions="You are Mia, a helpful and concise AI assistant.",
        tools=[],
        access_policy="approval-required",
    ),
    "research": Agent(
        agent_id="research",
        display_name="Research",
        description="Research Agent with a private specialist-and-synthesis strategy.",
        instructions="Research carefully, separate evidence from assumptions, and cite findings.",
        tools=["read_file"],
        access_policy="read-only",
    ),
}

__all__ = [
    "AccessLevel",
    "Agent",
    "BUILTIN_AGENTS",
    "normalize_agent_id",
]
