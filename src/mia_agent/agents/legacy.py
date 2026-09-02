"""Legacy Profile projection helpers for the Agent registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from mia_agent.profiles.model import AgentProfile

if TYPE_CHECKING:
    from .manager import AgentManager

from .model import BUILTIN_AGENTS, LEGACY_PERMISSION_MAP, Agent, normalize_agent_id


def legacy_profile(manager: AgentManager, key: str) -> AgentProfile | None:
    path = legacy_path(manager, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentProfile.model_validate(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Failed to load legacy Profile '{key}': {exc}") from exc


def legacy_profiles(manager: AgentManager) -> list[AgentProfile]:
    if not manager.profiles_dir.exists():
        return []
    profiles: list[AgentProfile] = []
    for path in sorted(manager.profiles_dir.glob("*.json")):
        try:
            profiles.append(
                AgentProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return profiles


def project_legacy(profile: AgentProfile) -> Agent:
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


def legacy_path(manager: AgentManager, key: str) -> Path:
    return manager.profiles_dir / f"{key}.json"


def native_path_for_key(manager: AgentManager, key: str) -> Path:
    return manager.agents_dir / key / "agent.json"


def canonical_id(value: str) -> str:
    key = normalize_agent_id(value)
    return "code-mode" if key == "code_mode" else key


def copy_builtin(key: str) -> Agent:
    return BUILTIN_AGENTS[key].model_copy(deep=True)
