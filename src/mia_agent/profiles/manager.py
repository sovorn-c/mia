"""ProfileManager discovering and configuring built-in and user agent profiles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mia_agent.agents.model import BUILTIN_AGENTS
from mia_agent.profiles.model import AgentProfile


def _profile_from_agent(agent_id: str, *, legacy_name: str | None = None) -> AgentProfile:
    agent = BUILTIN_AGENTS[agent_id]
    execution_mode = str(agent.metadata.get("execution_mode", "native"))
    if execution_mode not in {"native", "code"}:
        execution_mode = "native"
    return AgentProfile(
        name=legacy_name or agent.agent_id,
        description=agent.description,
        system_prompt=agent.instructions,
        model=agent.model,
        temperature=agent.temperature,
        max_steps_per_turn=agent.max_steps_per_turn,
        tools=agent.tools,
        execution_mode=execution_mode,  # type: ignore[arg-type]
        permission=agent.permission,  # type: ignore[arg-type]
        compaction_threshold_ratio=agent.compaction_threshold_ratio,
        context_window_tokens=agent.context_window_tokens,
        middlewares=list(agent.middlewares),
        metadata=dict(agent.metadata),
    )


# Compatibility projections. Agent definitions are the source of truth.
BUILTIN_PROFILES: dict[str, AgentProfile] = {
    "coding": _profile_from_agent("coding"),
    "architect": _profile_from_agent("architect"),
    "code_mode": _profile_from_agent("code-mode", legacy_name="code_mode"),
    "minimal": _profile_from_agent("minimal"),
}


def default_profiles_dir() -> Path:
    return Path.home() / ".mia" / "profiles"


def default_sessions_base_dir() -> Path:
    return Path.home() / ".mia" / "sessions"


class ProfileManager:
    """Discovers, loads, and manages AgentProfiles."""

    def __init__(
        self,
        profiles_dir: Path | None = None,
        sessions_base_dir: Path | None = None,
    ) -> None:
        self.profiles_dir = profiles_dir or default_profiles_dir()
        self.sessions_base_dir = sessions_base_dir or default_sessions_base_dir()

    def get_profile(self, name: str) -> AgentProfile:
        """Retrieve profile by name (checking built-ins then user custom profiles)."""
        key = name.lower().strip()
        # 1. Check built-in profiles
        if key in BUILTIN_PROFILES:
            return BUILTIN_PROFILES[key]

        # 2. Check user profiles directory
        if self.profiles_dir.exists():
            json_file = self.profiles_dir / f"{key}.json"
            if json_file.exists():
                try:
                    with open(json_file, encoding="utf-8") as f:
                        data = json.load(f)
                        return AgentProfile.model_validate(data)
                except Exception as exc:
                    raise ValueError(f"Failed to load user profile '{name}': {exc}") from exc

        raise ValueError(
            f"Profile '{name}' not found. Available profiles: {', '.join(p.name for p in self.list_profiles())}"
        )

    def list_profiles(self) -> list[AgentProfile]:
        """List all available profiles (built-in + user)."""
        profiles: dict[str, AgentProfile] = dict(BUILTIN_PROFILES)

        if self.profiles_dir.exists():
            for p in self.profiles_dir.glob("*.json"):
                key = p.stem.lower()
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f)
                        profiles[key] = AgentProfile.model_validate(data)
                except Exception:
                    continue

        return sorted(profiles.values(), key=lambda p: p.name)

    def save_user_profile(self, profile: AgentProfile) -> Path:
        """Save or update a custom user profile."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        target = self.profiles_dir / f"{profile.name.lower()}.json"
        with open(target, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, indent=2)
        return target

    def delete_user_profile(self, name: str) -> bool:
        """Delete a custom user profile."""
        key = name.lower().strip()
        if key in BUILTIN_PROFILES:
            raise ValueError(f"Cannot delete built-in system profile '{name}'.")
        target = self.profiles_dir / f"{key}.json"
        if target.exists():
            target.unlink()
            return True
        return False

    def get_session_dir(self, profile_name: str, create: bool = True) -> Path:
        """Get the isolated session storage directory for the given profile."""
        path = self.sessions_base_dir / profile_name.lower().strip()
        if create:
            import contextlib

            with contextlib.suppress(OSError):
                path.mkdir(parents=True, exist_ok=True)
        return path

    def filter_tools(self, profile: AgentProfile, available_tools: Sequence[Any]) -> list[Any]:
        """Filter a list of tool objects according to the profile's allowed tools."""
        if profile.tools is None:
            return list(available_tools)

        allowed = set(profile.tools)
        filtered: list[Any] = []
        for tool in available_tools:
            name = getattr(tool, "name", None)
            if name in allowed:
                filtered.append(tool)
        return filtered
