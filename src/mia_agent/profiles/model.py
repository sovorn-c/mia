"""AgentProfile definition controlling persona, models, tools, and execution modes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    """Declarative specification for an agent profile / preset."""

    name: str
    description: str = ""
    system_prompt: str = "You are Mia, an expert AI software engineer."
    model: str | None = None
    temperature: float = 0.7
    max_steps_per_turn: int = 25
    tools: list[str] | None = None  # None = all allowed, [] = no tools
    execution_mode: Literal["native", "code"] = "native"
    permission: Literal["standard", "read_only", "no_tools", "full_access"] = "standard"
    compaction_threshold_ratio: float | None = None
    context_window_tokens: int | None = None
    middlewares: list[str] = Field(
        default_factory=lambda: ["security_guard", "audit_log", "cost_budget"]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
