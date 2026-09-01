"""Canonical Agent identity and registry APIs."""

from mia_agent.agents.model import (
    AccessLevel,
    BUILTIN_AGENTS,
    LEGACY_PERMISSION_MAP,
    Agent,
    normalize_agent_id,
)


def __getattr__(name: str) -> object:
    if name == "AgentManager":
        from mia_agent.agents.manager import AgentManager

        return AgentManager
    raise AttributeError(name)


__all__ = [
    "AccessLevel",
    "Agent",
    "AgentManager",
    "BUILTIN_AGENTS",
    "LEGACY_PERMISSION_MAP",
    "normalize_agent_id",
]
