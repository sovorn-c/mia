"""Native Agent registry with additive legacy Profile compatibility."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .legacy import (
    canonical_id,
    copy_builtin,
    legacy_path,
    legacy_profile,
    legacy_profiles,
    native_path_for_key,
    project_legacy,
)
from .model import BUILTIN_AGENTS, Agent, normalize_agent_id
from .storage import atomic_write_text, coerce_agent, load_native, write_agent


def default_agents_dir() -> Path:
    return Path.home() / ".mia" / "agents"


DEFAULT_AGENT_HOME = default_agents_dir()
DEFAULT_SELECTION_FILE = ".default-agent"
AGENT_DEFINITION_FILE = "agent.json"


class AgentManager:
    """Resolve and persist canonical Agents without rewriting legacy user data."""

    def __init__(
        self,
        agents_dir: Path | None = None,
        *,
        profiles_dir: Path | None = None,
        sessions_base_dir: Path | None = None,
        profile_manager: Any | None = None,
    ) -> None:
        from mia_agent.profiles.manager import (
            ProfileManager,
            default_profiles_dir,
            default_sessions_base_dir,
        )

        self.agents_dir = (agents_dir or default_agents_dir()).expanduser().resolve()
        self.profiles_dir = (profiles_dir or default_profiles_dir()).expanduser().resolve()
        self.sessions_base_dir = (
            (sessions_base_dir or default_sessions_base_dir()).expanduser().resolve()
        )
        self.profile_manager = profile_manager or ProfileManager(
            profiles_dir=self.profiles_dir,
            sessions_base_dir=self.sessions_base_dir,
        )
        self.profiles_dir = self.profile_manager.profiles_dir
        self.sessions_base_dir = self.profile_manager.sessions_base_dir

    def get_agent(self, agent_id: str | None = None) -> Agent:
        """Resolve one Agent, defaulting to the built-in personal Mia Agent."""
        if agent_id is None:
            return self.default_agent()
        key = canonical_id(agent_id)
        agent, _, _ = self._resolve(key)
        return agent

    def resolve(self, agent_id: str | None = None) -> Agent:
        """Compatibility spelling for Agent resolution."""
        return self.get_agent(agent_id)

    def default_agent(self) -> Agent:
        """Return the selected Agent, or Mia when no valid selection is saved."""
        selection = self.agents_dir / DEFAULT_SELECTION_FILE
        if selection.exists():
            try:
                selected = selection.read_text(encoding="utf-8").strip()
                if selected:
                    return self.get_agent(selected)
            except (OSError, ValueError):
                pass
        return copy_builtin("mia")

    def list_agents(self) -> list[Agent]:
        """List built-ins followed by native and legacy Agents in stable ID order."""
        agents: dict[str, Agent] = {
            agent_id: copy_builtin(agent_id) for agent_id, agent in BUILTIN_AGENTS.items()
        }

        for definition in sorted(self.agents_dir.glob(f"*/{AGENT_DEFINITION_FILE}")):
            try:
                agent = load_native(definition)
            except ValueError:
                raise
            if agent.agent_id not in BUILTIN_AGENTS:
                agents[agent.agent_id] = agent

        for profile in legacy_profiles(self):
            if profile.name not in agents:
                agents[profile.name] = project_legacy(profile)

        return sorted(agents.values(), key=lambda agent: agent.agent_id)

    def create_agent(
        self,
        agent: Agent | str,
        *,
        display_name: str | None = None,
        **fields: Any,
    ) -> Agent:
        """Create and persist a non-built-in Agent; legacy IDs may be shadowed natively."""
        confirm_value = fields.pop("confirm_full_access", None)
        if confirm_value is None:
            confirm_value = fields.pop("full_access_confirmed", False)
        confirm_full_access = bool(confirm_value)
        candidate = coerce_agent(agent, display_name=display_name, fields=fields)
        if candidate.access_policy == "full-access":
            if not confirm_full_access and not candidate.full_access_confirmed:
                raise ValueError("full-access Agent creation requires explicit confirmation")
            candidate = candidate.model_copy(update={"full_access_confirmed": True})
        if candidate.agent_id in BUILTIN_AGENTS:
            raise ValueError(f"Cannot create or overwrite built-in Agent '{candidate.agent_id}'.")
        target = self.agent_path(candidate.agent_id)
        if target.exists():
            raise ValueError(f"Agent '{candidate.agent_id}' already exists")
        write_agent(self, candidate)
        return candidate

    def save_agent(self, agent: Agent, *, confirm_full_access: bool = False) -> Path:
        """Atomically save a native Agent and leave any legacy source untouched."""
        candidate = Agent.model_validate(agent.model_dump())
        if candidate.access_policy == "full-access":
            if not confirm_full_access and not candidate.full_access_confirmed:
                raise ValueError("full-access Agent persistence requires explicit confirmation")
            candidate = candidate.model_copy(update={"full_access_confirmed": True})
        if candidate.agent_id in BUILTIN_AGENTS:
            raise ValueError(f"Cannot create or overwrite built-in Agent '{candidate.agent_id}'.")
        return write_agent(self, candidate)

    def delete_agent(self, agent_id: str) -> bool:
        """Delete one native Agent and never delete a built-in or legacy Profile."""
        key = canonical_id(agent_id)
        if key in BUILTIN_AGENTS:
            raise ValueError(f"Cannot delete built-in Agent '{agent_id}'.")
        target_dir = self.agent_home(key)
        target = target_dir / AGENT_DEFINITION_FILE
        if not target.exists():
            return False
        target.unlink()
        with contextlib.suppress(OSError):
            target_dir.rmdir()
        if self._selected_id() == key:
            self._clear_default()
        return True

    def set_default(self, agent_id: str, *, confirm_full_access: bool = False) -> Agent:
        """Persist the default Agent selection after validating it exists."""
        agent = self.get_agent(agent_id)
        if agent.access_policy == "full-access" and not (
            confirm_full_access or agent.full_access_confirmed
        ):
            raise ValueError("selecting a full-access Agent requires explicit confirmation")
        if (
            confirm_full_access
            and agent.access_policy == "full-access"
            and not agent.full_access_confirmed
        ):
            agent = agent.model_copy(update={"full_access_confirmed": True})
            if agent.agent_id not in BUILTIN_AGENTS:
                write_agent(self, agent)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.agents_dir / DEFAULT_SELECTION_FILE, agent.agent_id + "\n")
        return agent

    def use_agent(self, agent_id: str, *, confirm_full_access: bool = False) -> Agent:
        """Canonical command-oriented spelling for selecting the default Agent."""
        return self.set_default(agent_id, confirm_full_access=confirm_full_access)

    def get(self, agent_id: str | None = None) -> Agent:
        """Short command-oriented spelling for resolving an Agent."""
        return self.get_agent(agent_id)

    def create(self, agent: Agent | str, **fields: Any) -> Agent:
        """Short command-oriented spelling for creating an Agent."""
        return self.create_agent(agent, **fields)

    def save(self, agent: Agent, **kwargs: Any) -> Path:
        """Short command-oriented spelling for saving an Agent."""
        return self.save_agent(agent, **kwargs)

    def delete(self, agent_id: str) -> bool:
        """Short command-oriented spelling for deleting an Agent."""
        return self.delete_agent(agent_id)

    def inspect_agent(self, agent_id: str) -> dict[str, Any]:
        """Return an inspection record with source and collision diagnostics."""
        key = canonical_id(agent_id)
        agent, source, collision = self._resolve(key)
        return {
            "agent": agent,
            "source": source,
            "collision": collision,
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
        }

    def show_agent(self, agent_id: str) -> dict[str, Any]:
        """Compatibility spelling for inspection output."""
        return self.inspect_agent(agent_id)

    def agent_home(self, agent_id: str) -> Path:
        """Return the path-safe native home for an Agent."""
        return self.agents_dir / canonical_id(agent_id)

    def agent_path(self, agent_id: str) -> Path:
        """Return the native definition path for an Agent."""
        return self.agent_home(agent_id) / AGENT_DEFINITION_FILE

    def get_session_dir(self, agent_id: str, create: bool = True) -> Path:
        """Return the native or legacy Session directory for one Agent."""
        key = canonical_id(agent_id)
        _, source, _ = self._resolve(key)
        if source in {"builtin", "native"}:
            path = self.agent_home(key) / "sessions"
        else:
            path = self.sessions_base_dir / key
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def get_session_path(self, agent_id: str, session_id: str, create: bool = True) -> Path:
        """Choose native Session storage first, falling back to a legacy Session if present."""
        session_key = normalize_agent_id(session_id)
        native = self.agent_home(agent_id) / "sessions" / f"{session_key}.jsonl"
        _, source, _ = self._resolve(canonical_id(agent_id))
        if source in {"builtin", "native"} or native.exists():
            if create:
                native.parent.mkdir(parents=True, exist_ok=True)
            return native
        legacy = self.sessions_base_dir / canonical_id(agent_id) / f"{session_key}.jsonl"
        if create:
            legacy.parent.mkdir(parents=True, exist_ok=True)
        return legacy

    def filter_tools(self, agent: Agent, available_tools: Sequence[Any]) -> list[Any]:
        """Filter visible Tools by capability scope and read-only access."""
        if agent.tools is None:
            filtered = list(available_tools)
        else:
            allowed = set(agent.tools)
            filtered = [tool for tool in available_tools if getattr(tool, "name", None) in allowed]
        if agent.access_policy != "read-only":
            return filtered
        from mia_middleware.access import tool_effect

        return [
            tool
            for tool in filtered
            if tool_effect(getattr(tool, "name", ""), {"effect": getattr(tool, "effect", None)})
            == "non-mutating"
        ]

    def _resolve(self, key: str) -> tuple[Agent, str, bool]:
        collision = native_path_for_key(self, key).exists() and legacy_path(self, key).exists()
        if key in BUILTIN_AGENTS:
            return copy_builtin(key), "builtin", collision or legacy_path(self, key).exists()

        native_path = native_path_for_key(self, key)
        if native_path.exists():
            return load_native(native_path), "native", collision

        legacy = legacy_profile(self, key)
        if legacy is not None:
            return project_legacy(legacy), "legacy", False

        available = ", ".join(agent.agent_id for agent in self.list_agents())
        raise ValueError(f"Agent '{key}' not found. Available Agents: {available}")

    def _selected_id(self) -> str | None:
        selection = self.agents_dir / DEFAULT_SELECTION_FILE
        try:
            value = selection.read_text(encoding="utf-8").strip()
            return canonical_id(value) if value else None
        except (OSError, ValueError):
            return None

    def _clear_default(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            (self.agents_dir / DEFAULT_SELECTION_FILE).unlink()


__all__ = [
    "AGENT_DEFINITION_FILE",
    "AgentManager",
    "DEFAULT_AGENT_HOME",
    "default_agents_dir",
]
