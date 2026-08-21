"""Multi-Agent Herd Orchestration package."""

from mia_agent.herd.manager import HerdManager
from mia_agent.herd.models import (
    AgentEventEnvelope,
    AgentSpawnedEvent,
    AgentState,
    AgentStateChangedEvent,
    HerdEvent,
    InterAgentMessageEvent,
    ManagedAgent,
)
from mia_agent.herd.tools import InvokeSubagentTool, SendMessageTool

__all__ = [
    "AgentEventEnvelope",
    "AgentSpawnedEvent",
    "AgentState",
    "AgentStateChangedEvent",
    "HerdEvent",
    "HerdManager",
    "InterAgentMessageEvent",
    "InvokeSubagentTool",
    "ManagedAgent",
    "SendMessageTool",
]
