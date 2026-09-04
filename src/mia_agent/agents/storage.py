"""Persistence helpers for native Agent definitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any

from .model import Agent

if TYPE_CHECKING:
    from .manager import AgentManager


def load_native(path: Path) -> Agent:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Agent.model_validate(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Failed to load Agent definition '{path}': {exc}") from exc


def write_agent(manager: AgentManager, agent: Agent) -> Path:
    target = manager.agent_path(agent.agent_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = agent.model_dump(mode="json", exclude_none=True)
    atomic_write_json(target, payload)
    return target


def coerce_agent(
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


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    with NamedTemporaryFile(
        "w", dir=path.parent, prefix=".agent-", suffix=".tmp", encoding="utf-8", delete=False
    ) as temp:
        json.dump(payload, temp, indent=2)
        temp.write("\n")
        temp.flush()
        os.fsync(temp.fileno())
        temporary_path = Path(temp.name)
    temporary_path.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", dir=path.parent, prefix=".default-", suffix=".tmp", encoding="utf-8", delete=False
    ) as temp:
        temp.write(value)
        temp.flush()
        os.fsync(temp.fileno())
        temporary_path = Path(temp.name)
    temporary_path.replace(path)
