"""Validated contracts for bounded Agent-to-Agent Delegation."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

TaskOutcome = Literal["succeeded", "failed", "rejected", "cancelled", "timed-out"]
MAX_TASK_PROMPT_LENGTH = 20_000
MAX_DELEGATION_TIMEOUT = 300.0


class TaskRequest(BaseModel):
    """Validated bounded input to one direct Delegation call."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex}")
    caller_agent_id: str = Field(validation_alias=AliasChoices("caller_agent_id", "caller_id"))
    recipient_agent_id: str = Field(
        validation_alias=AliasChoices("recipient_agent_id", "recipient_id")
    )
    prompt: str = Field(
        validation_alias=AliasChoices("prompt", "task_prompt", "text"),
        min_length=1,
        max_length=MAX_TASK_PROMPT_LENGTH,
    )
    parent_run_id: str = "root"
    parent_session_id: str = "root"
    timeout: float = 60.0
    depth: int = 0

    @field_validator("task_id", "parent_run_id", "parent_session_id")
    @classmethod
    def require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task identity fields must not be blank")
        return value

    @field_validator("caller_agent_id", "recipient_agent_id")
    @classmethod
    def normalize_agent_identity(cls, value: str) -> str:
        from mia_agent.agents.model import normalize_agent_id

        return normalize_agent_id(value)

    @field_validator("prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task prompt must not be blank")
        return value

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 0 < value <= MAX_DELEGATION_TIMEOUT:
            raise ValueError(
                f"Task timeout must be greater than 0 and at most {MAX_DELEGATION_TIMEOUT:g}s"
            )
        return value

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, value: int) -> int:
        if value not in {0, 1}:
            raise ValueError("Delegation depth must be 0 or 1")
        return value

    @model_validator(mode="after")
    def reject_self_target(self) -> TaskRequest:
        if self.caller_agent_id.strip().lower() == self.recipient_agent_id.strip().lower():
            raise ValueError("An Agent cannot delegate a Task to itself")
        return self


class TaskResult(BaseModel):
    """Serializable, attributable terminal result for one Task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    caller_agent_id: str
    recipient_agent_id: str
    parent_run_id: str = "root"
    parent_session_id: str = "root"
    child_run_id: str = ""
    child_session_id: str = ""
    outcome: TaskOutcome
    response: str | None = None
    error: str | None = None

    @field_validator(
        "task_id",
        "caller_agent_id",
        "recipient_agent_id",
        "parent_run_id",
        "parent_session_id",
    )
    @classmethod
    def require_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task result identity fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> TaskResult:
        if self.outcome == "succeeded":
            if not self.response or not self.response.strip():
                raise ValueError("Succeeded Task results require response content")
            if self.error is not None:
                raise ValueError("Succeeded Task results cannot carry an error")
        elif not self.error or not self.error.strip():
            raise ValueError(f"{self.outcome} Task results require terminal error context")
        return self
