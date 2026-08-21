"""Domain models and typed events for multi-agent Herd orchestration."""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mia_agent.events import AgentEvent


class AgentState(StrEnum):
    """Lifecycle state of a managed agent in the herd."""

    IDLE = "idle"  # Waiting for instruction or next turn
    WORKING = "working"  # Actively streaming LLM or executing tool
    BLOCKED = "blocked"  # Awaiting human confirmation / security approval
    DONE = "done"  # Completed current task / turn
    ERROR = "error"  # Encountered an unrecoverable failure


class ManagedAgent(BaseModel):
    """Metadata and runtime state for an individual agent in the herd."""

    id: str  # Unique slug, e.g. "lead", "coder", "tester"
    name: str  # Human-readable title, e.g. "Lead Architect", "Senior Coder"
    profile: str = "coding"  # Profile name ("coding", "architect", etc.)
    model: str | None = None  # Model identifier or override
    state: AgentState = AgentState.IDLE
    current_step: int = 0
    max_steps: int = 25
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    session_id: str = Field(default_factory=lambda: f"session_{uuid.uuid4().hex[:8]}")
    unread_messages: int = 0
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Herd Event Stream Types ---


class BaseHerdEvent(BaseModel):
    """Base model for all herd orchestration events."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = Field(default_factory=time.time)
    type: str


class AgentSpawnedEvent(BaseHerdEvent):
    """Emitted when a new agent is registered into the herd."""

    type: Literal["agent_spawned"] = "agent_spawned"
    agent: ManagedAgent


class AgentStateChangedEvent(BaseHerdEvent):
    """Emitted when an agent's operational state transitions."""

    type: Literal["agent_state_changed"] = "agent_state_changed"
    agent_id: str
    previous_state: AgentState
    new_state: AgentState
    reason: str = ""


class AgentEventEnvelope(BaseHerdEvent):
    """Wraps a standard AgentEvent with the originating agent's ID."""

    type: Literal["agent_event_envelope"] = "agent_event_envelope"
    agent_id: str
    event: AgentEvent


class InterAgentMessageEvent(BaseHerdEvent):
    """Emitted when one agent sends a message or delegation task to another."""

    type: Literal["inter_agent_message"] = "inter_agent_message"
    sender_id: str
    recipient_id: str
    content: str
    task_id: str | None = None


HerdEvent = Annotated[
    AgentSpawnedEvent | AgentStateChangedEvent | AgentEventEnvelope | InterAgentMessageEvent,
    Field(discriminator="type"),
]
