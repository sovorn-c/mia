"""ProfileManager discovering and configuring built-in and user agent profiles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mia_agent.profiles.model import AgentProfile

BUILTIN_PROFILES: dict[str, AgentProfile] = {
    "coding": AgentProfile(
        name="coding",
        description="Full-stack AI software engineer with file editing, diffs, and shell execution.",
        system_prompt=(
            "You are Mia, an expert AI software engineer. You write clean, robust code, "
            "follow test-driven development, inspect files before editing, and explain changes clearly."
        ),
        temperature=0.2,
        tools=["read_file", "write_file", "edit_file", "bash"],
        execution_mode="native",
        permission="standard",
    ),
    "architect": AgentProfile(
        name="architect",
        description="Read-only system architect for codebase exploration, ADR drafting, and design reviews.",
        system_prompt=(
            "You are Mia Architect, a Principal Software Architect. You analyze complex system designs, "
            "evaluate architectural trade-offs, draft ADRs, and review codebases with deep modularity in mind. "
            "You operate in read-only mode and do not modify files directly."
        ),
        temperature=0.4,
        tools=["read_file"],
        execution_mode="native",
        permission="read_only",
    ),
    "code_mode": AgentProfile(
        name="code_mode",
        description="DeepSeek Harness Programmatic Code Mode where the agent writes Python scripts to batch tool calls.",
        system_prompt=(
            "You are Mia in Code Mode. You can batch multiple tool calls programmatically "
            "in a single turn using the run_code environment to minimize token round-trips."
        ),
        temperature=0.0,
        tools=["run_code", "read_file", "write_file", "edit_file", "bash"],
        execution_mode="code",
        permission="standard",
    ),
    "minimal": AgentProfile(
        name="minimal",
        description="Fast direct conversation, brainstorming, and reasoning with zero tool overhead.",
        system_prompt="You are Mia, a helpful and concise AI assistant.",
        temperature=0.7,
        tools=[],
        execution_mode="native",
        permission="no_tools",
    ),
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
