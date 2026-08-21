"""Built-in inter-agent coordination tools for Herd orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mia_tools.base import BaseTool

if TYPE_CHECKING:
    from mia_agent.herd.manager import HerdManager


class InvokeSubagentTool(BaseTool):
    """Allows an orchestrator agent to spawn or delegate tasks to a subagent."""

    name: str = "invoke_subagent"
    description: str = (
        "Delegate a specific coding, testing, or architectural task to a specialized subagent "
        "(e.g. 'coder', 'tester', 'reviewer') and wait for their result."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "ID of the target agent, e.g. 'coder', 'tester', 'architect'.",
            },
            "prompt": {
                "type": "string",
                "description": "The exact instruction, context, and requirements for the subagent.",
            },
            "profile": {
                "type": "string",
                "description": "Optional profile to spawn if the agent does not exist (default: 'coding').",
            },
        },
        "required": ["agent_id", "prompt"],
    }

    def __init__(self, herd_manager: HerdManager) -> None:
        super().__init__()
        self.herd_manager = herd_manager

    async def execute(self, **kwargs: Any) -> str:
        agent_id = str(kwargs.get("agent_id", "")).strip().lstrip("@")
        prompt = str(kwargs.get("prompt", ""))
        profile = kwargs.get("profile")

        if not agent_id:
            return "Error: agent_id is required."
        if not prompt:
            return "Error: prompt cannot be empty."

        return await self.herd_manager.delegate_task(
            target_id=agent_id,
            prompt=prompt,
            profile=profile,
        )


class SendMessageTool(BaseTool):
    """Allows an agent to send an asynchronous message or status update to another agent."""

    name: str = "send_message"
    description: str = "Send a status message, review feedback, or notification to another agent."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "recipient_id": {
                "type": "string",
                "description": "ID of the recipient agent (e.g. 'lead', 'coder').",
            },
            "message": {
                "type": "string",
                "description": "The message body to deliver.",
            },
        },
        "required": ["recipient_id", "message"],
    }

    def __init__(self, herd_manager: HerdManager, sender_id: str = "unknown") -> None:
        super().__init__()
        self.herd_manager = herd_manager
        self.sender_id = sender_id

    async def execute(self, **kwargs: Any) -> str:
        recipient_id = str(kwargs.get("recipient_id", "")).strip().lstrip("@")
        message = str(kwargs.get("message", ""))

        if not recipient_id:
            return "Error: recipient_id is required."

        await self.herd_manager.send_direct_message(
            sender_id=self.sender_id,
            recipient_id=recipient_id,
            content=message,
        )
        return f"Message successfully delivered to @{recipient_id}."
