"""Native Agent registry and Agent-owned persistence."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .model import BUILTIN_AGENTS, Agent, normalize_agent_id
from .storage import atomic_write_text, coerce_agent, load_native, write_agent


def default_agents_dir() -> Path:
    return Path.home() / ".mia" / "agents"


DEFAULT_AGENT_HOME = default_agents_dir()
DEFAULT_SELECTION_FILE = ".default-agent"
AGENT_DEFINITION_FILE = "agent.json"


class AgentManager:
    """Resolve, persist, and select built-in or native Agents."""

    def __init__(self, agents_dir: Path | None = None) -> None:
        configured = (agents_dir or default_agents_dir()).expanduser().absolute()
        if configured.is_symlink():
            raise ValueError("Agent storage root must not be a symlink")
        self.agents_dir = configured.parent.resolve() / configured.name

    def get_agent(self, agent_id: str | None = None) -> Agent:
        """Resolve one Agent, defaulting to the selected or built-in Mia Agent."""
        if agent_id is None:
            return self.default_agent()
        return self._resolve(normalize_agent_id(agent_id))

    def default_agent(self) -> Agent:
        """Return the selected Agent, or Mia when no valid selection is saved."""
        selection = self._owned_path(self.agents_dir / DEFAULT_SELECTION_FILE)
        try:
            selected = selection.read_text(encoding="utf-8").strip()
        except OSError:
            selected = ""
        if selected:
            try:
                return self.get_agent(selected)
            except ValueError:
                pass
        return BUILTIN_AGENTS["mia"].model_copy(deep=True)

    def list_agents(self) -> list[Agent]:
        """List built-in and native Agents in stable ID order."""
        agents = {
            agent_id: agent.model_copy(deep=True) for agent_id, agent in BUILTIN_AGENTS.items()
        }
        for definition in sorted(self.agents_dir.glob(f"*/{AGENT_DEFINITION_FILE}")):
            agent = load_native(self._owned_path(definition))
            if agent.agent_id not in BUILTIN_AGENTS:
                agents[agent.agent_id] = agent
        return sorted(agents.values(), key=lambda agent: agent.agent_id)

    def create_agent(
        self,
        agent: Agent | str,
        *,
        display_name: str | None = None,
        **fields: Any,
    ) -> Agent:
        """Create and persist one non-built-in Agent."""
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
        """Atomically save one native Agent."""
        candidate = Agent.model_validate(agent.model_dump())
        if candidate.access_policy == "full-access":
            if not confirm_full_access and not candidate.full_access_confirmed:
                raise ValueError("full-access Agent persistence requires explicit confirmation")
            candidate = candidate.model_copy(update={"full_access_confirmed": True})
        if candidate.agent_id in BUILTIN_AGENTS:
            raise ValueError(f"Cannot create or overwrite built-in Agent '{candidate.agent_id}'.")
        return write_agent(self, candidate)

    def delete_agent(self, agent_id: str) -> bool:
        """Delete one native Agent without touching built-ins."""
        key = normalize_agent_id(agent_id)
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
        selection = self._owned_path(self.agents_dir / DEFAULT_SELECTION_FILE)
        atomic_write_text(selection, agent.agent_id + "\n")
        return agent

    def use_agent(self, agent_id: str, *, confirm_full_access: bool = False) -> Agent:
        """Select the default Agent for future Runs."""
        return self.set_default(agent_id, confirm_full_access=confirm_full_access)

    def agent_home(self, agent_id: str) -> Path:
        """Return the path-safe home for one Agent."""
        return self._owned_path(self.agents_dir / normalize_agent_id(agent_id))

    def agent_path(self, agent_id: str) -> Path:
        """Return the native Agent definition path."""
        return self._owned_path(self.agent_home(agent_id) / AGENT_DEFINITION_FILE)

    def get_session_dir(self, agent_id: str, create: bool = True) -> Path:
        """Return the Agent-owned Session directory."""
        path = self._owned_path(self.agent_home(agent_id) / "sessions")
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def get_session_path(self, agent_id: str, session_id: str, create: bool = True) -> Path:
        """Return the Agent-owned JSONL Session path."""
        path = self.get_session_dir(agent_id, create=create) / (
            f"{normalize_agent_id(session_id)}.jsonl"
        )
        return self._owned_path(path)

    def filter_tools(self, agent: Agent, available_tools: Sequence[Any]) -> list[Any]:
        """Filter visible Tools by Agent capability scope and access policy."""
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

    def _resolve(self, key: str) -> Agent:
        if key in BUILTIN_AGENTS:
            return BUILTIN_AGENTS[key].model_copy(deep=True)
        native_path = self.agent_path(key)
        if native_path.exists():
            return load_native(native_path)
        available = ", ".join(agent.agent_id for agent in self.list_agents())
        raise ValueError(f"Agent '{key}' not found. Available Agents: {available}")

    def _selected_id(self) -> str | None:
        selection = self._owned_path(self.agents_dir / DEFAULT_SELECTION_FILE)
        try:
            value = selection.read_text(encoding="utf-8").strip()
            return normalize_agent_id(value) if value else None
        except (OSError, ValueError):
            return None

    def _clear_default(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._owned_path(self.agents_dir / DEFAULT_SELECTION_FILE).unlink()

    def _owned_path(self, path: Path) -> Path:
        """Reject symlink components and paths outside the Agent storage root."""
        try:
            relative = path.relative_to(self.agents_dir)
        except ValueError as exc:
            raise ValueError("Agent storage path escapes its configured root") from exc

        current = self.agents_dir
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Agent storage paths must not contain symlinks")

        try:
            path.resolve().relative_to(self.agents_dir)
        except ValueError as exc:
            raise ValueError("Agent storage path escapes its configured root") from exc
        return path


__all__ = [
    "AGENT_DEFINITION_FILE",
    "AgentManager",
    "DEFAULT_AGENT_HOME",
    "default_agents_dir",
]
