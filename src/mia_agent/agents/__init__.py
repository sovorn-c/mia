"""Canonical Agent identity and registry APIs."""

from mia_agent.agents.manager import AgentManager, default_agents_dir
from mia_agent.agents.model import (
    BUILTIN_AGENTS,
    LEGACY_PERMISSION_MAP,
    AccessLevel,
    Agent,
    normalize_agent_id,
    normalize_plugin_id,
)

__all__ = [
    "AccessLevel",
    "Agent",
    "AgentManager",
    "BUILTIN_AGENTS",
    "default_agents_dir",
    "LEGACY_PERMISSION_MAP",
    "normalize_agent_id",
    "normalize_plugin_id",
]
