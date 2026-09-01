"""Native Agent registry with additive legacy Profile compatibility."""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any

from .model import BUILTIN_AGENTS, LEGACY_PERMISSION_MAP, Agent, normalize_agent_id

if TYPE_CHECKING:
    from mia_agent.profiles.model import AgentProfile

DEFAULT_AGENT_HOME = Path.home() / ".mia" / "agents"
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

        self.agents_dir = (agents_dir or DEFAULT_AGENT_HOME).expanduser().resolve()
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
        key = self._canonical_id(agent_id)
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
        return self._copy_builtin("mia")

    def list_agents(self) -> list[Agent]:
        """List built-ins followed by native and legacy Agents in stable ID order."""
        agents: dict[str, Agent] = {
            agent_id: self._copy_builtin(agent_id) for agent_id, agent in BUILTIN_AGENTS.items()
        }

        for definition in sorted(self.agents_dir.glob(f"*/{AGENT_DEFINITION_FILE}")):
            try:
                agent = self._load_native(definition)
            except ValueError:
                raise
            if agent.agent_id not in BUILTIN_AGENTS:
                agents[agent.agent_id] = agent

        for profile in self._legacy_profiles():
            if profile.name not in agents:
                agents[profile.name] = self._project_legacy(profile)

        return sorted(agents.values(), key=lambda agent: agent.agent_id)

    def create_agent(
        self,
        agent: Agent | str,
        *,
        display_name: str | None = None,
        **fields: Any,
    ) -> Agent:
        """Create and persist a non-built-in Agent; legacy IDs may be shadowed natively."""
        candidate = self._coerce_agent(agent, display_name=display_name, fields=fields)
        if candidate.agent_id in BUILTIN_AGENTS:
            raise ValueError(f"Cannot create or overwrite built-in Agent '{candidate.agent_id}'.")
        target = self.agent_path(candidate.agent_id)
        if target.exists():
            raise ValueError(f"Agent '{candidate.agent_id}' already exists")
        self._write_agent(candidate)
        return candidate

    def save_agent(self, agent: Agent) -> Path:
        """Atomically save a native Agent and leave any legacy source untouched."""
        candidate = Agent.model_validate(agent.model_dump())
        if candidate.agent_id in BUILTIN_AGENTS:
            raise ValueError(f"Cannot create or overwrite built-in Agent '{candidate.agent_id}'.")
        return self._write_agent(candidate)

    def delete_agent(self, agent_id: str) -> bool:
        """Delete one native Agent and never delete a built-in or legacy Profile."""
        key = self._canonical_id(agent_id)
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

    def set_default(self, agent_id: str) -> Agent:
        """Persist the default Agent selection after validating it exists."""
        agent = self.get_agent(agent_id)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(self.agents_dir / DEFAULT_SELECTION_FILE, agent.agent_id + "\n")
        return agent

    def use_agent(self, agent_id: str) -> Agent:
        """Canonical command-oriented spelling for selecting the default Agent."""
        return self.set_default(agent_id)

    def inspect_agent(self, agent_id: str) -> dict[str, Any]:
        """Return an inspection record with source and collision diagnostics."""
        key = self._canonical_id(agent_id)
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
        return self.agents_dir / self._canonical_id(agent_id)

    def agent_path(self, agent_id: str) -> Path:
        """Return the native definition path for an Agent."""
        return self.agent_home(agent_id) / AGENT_DEFINITION_FILE

    def get_session_dir(self, agent_id: str, create: bool = True) -> Path:
        """Return the native or legacy Session directory for one Agent."""
        key = self._canonical_id(agent_id)
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
        _, source, _ = self._resolve(self._canonical_id(agent_id))
        if source in {"builtin", "native"} or native.exists():
            if create:
                native.parent.mkdir(parents=True, exist_ok=True)
            return native
        legacy = self.sessions_base_dir / self._canonical_id(agent_id) / f"{session_key}.jsonl"
        if create:
            legacy.parent.mkdir(parents=True, exist_ok=True)
        return legacy

    def filter_tools(self, agent: Agent, available_tools: Sequence[Any]) -> list[Any]:
        """Filter visible Tools by the Agent's declared capability scope."""
        if agent.tools is None:
            return list(available_tools)
        allowed = set(agent.tools)
        return [tool for tool in available_tools if getattr(tool, "name", None) in allowed]

    def _resolve(self, key: str) -> tuple[Agent, str, bool]:
        collision = self._native_path_for_key(key).exists() and self._legacy_path(key).exists()
        if key in BUILTIN_AGENTS:
            return self._copy_builtin(key), "builtin", collision or self._legacy_path(key).exists()

        native_path = self._native_path_for_key(key)
        if native_path.exists():
            return self._load_native(native_path), "native", collision

        legacy = self._legacy_profile(key)
        if legacy is not None:
            return self._project_legacy(legacy), "legacy", False

        available = ", ".join(agent.agent_id for agent in self.list_agents())
        raise ValueError(f"Agent '{key}' not found. Available Agents: {available}")

    def _load_native(self, path: Path) -> Agent:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Agent.model_validate(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Failed to load Agent definition '{path}': {exc}") from exc

    def _write_agent(self, agent: Agent) -> Path:
        target = self.agent_path(agent.agent_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = agent.model_dump(mode="json", exclude_none=True)
        self._atomic_write_json(target, payload)
        return target

    @staticmethod
    def _coerce_agent(
        agent: Agent | str,
        *,
        display_name: str | None,
        fields: dict[str, Any],
    ) -> Agent:
        if isinstance(agent, Agent):
            if display_name is not None or fields:
                data = agent.model_dump()
                data.update(fields)
                if display_name is not None:
                    data["display_name"] = display_name
                return Agent.model_validate(data)
            return agent
        data = dict(fields)
        if display_name is not None:
            data["display_name"] = display_name
        return Agent(agent_id=agent, **data)

    def _legacy_profile(self, key: str) -> AgentProfile | None:
        from mia_agent.profiles.model import AgentProfile

        path = self._legacy_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AgentProfile.model_validate(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Failed to load legacy Profile '{key}': {exc}") from exc

    def _legacy_profiles(self) -> list[AgentProfile]:
        from mia_agent.profiles.model import AgentProfile

        if not self.profiles_dir.exists():
            return []
        profiles: list[AgentProfile] = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                profiles.append(
                    AgentProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
                )
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        return profiles

    @staticmethod
    def _project_legacy(profile: AgentProfile) -> Agent:
        metadata = dict(profile.metadata)
        if profile.execution_mode != "native":
            metadata["execution_mode"] = profile.execution_mode
        return Agent(
            agent_id=profile.name,
            display_name=profile.name.replace("_", " ").title(),
            description=profile.description,
            instructions=profile.system_prompt,
            model=profile.model,
            temperature=profile.temperature,
            max_steps_per_turn=profile.max_steps_per_turn,
            tools=profile.tools,
            access_policy=LEGACY_PERMISSION_MAP[profile.permission],
            compaction_threshold_ratio=profile.compaction_threshold_ratio,
            context_window_tokens=profile.context_window_tokens,
            middlewares=list(profile.middlewares),
            metadata=metadata,
        )

    def _legacy_path(self, key: str) -> Path:
        return self.profiles_dir / f"{key}.json"

    def _native_path_for_key(self, key: str) -> Path:
        return self.agents_dir / key / AGENT_DEFINITION_FILE

    def _canonical_id(self, value: str) -> str:
        key = normalize_agent_id(value)
        return "code-mode" if key == "code_mode" else key

    def _copy_builtin(self, key: str) -> Agent:
        return BUILTIN_AGENTS[key].model_copy(deep=True)

    def _selected_id(self) -> str | None:
        selection = self.agents_dir / DEFAULT_SELECTION_FILE
        try:
            value = selection.read_text(encoding="utf-8").strip()
            return self._canonical_id(value) if value else None
        except (OSError, ValueError):
            return None

    def _clear_default(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            (self.agents_dir / DEFAULT_SELECTION_FILE).unlink()

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        with NamedTemporaryFile(
            "w", dir=path.parent, prefix=".agent-", suffix=".tmp", encoding="utf-8", delete=False
        ) as temp:
            json.dump(payload, temp, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
            temporary_path = Path(temp.name)
        temporary_path.replace(path)

    @staticmethod
    def _atomic_write_text(path: Path, value: str) -> None:
        with NamedTemporaryFile(
            "w", dir=path.parent, prefix=".default-", suffix=".tmp", encoding="utf-8", delete=False
        ) as temp:
            temp.write(value)
            temp.flush()
            os.fsync(temp.fileno())
            temporary_path = Path(temp.name)
        temporary_path.replace(path)


__all__ = [
    "AGENT_DEFINITION_FILE",
    "AgentManager",
    "DEFAULT_AGENT_HOME",
]
