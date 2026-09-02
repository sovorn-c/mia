"""Thin Agent-facing adapter for the core Delegation service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mia_tools.base import BaseTool


class DelegateTaskTool(BaseTool):
    """Submit one bounded Task through an injected Delegation callable."""

    name = "delegate_task"
    effect = "side-effecting"
    description = "Delegate one bounded Task to an eligible named Agent."
    parameters = {
        "type": "object",
        "properties": {
            "recipient_agent_id": {"type": "string", "description": "Eligible recipient Agent ID."},
            "prompt": {"type": "string", "description": "Bounded Task instruction."},
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds, from 0 to 300.",
                "default": 60,
            },
        },
        "required": ["recipient_agent_id", "prompt"],
    }

    def __init__(
        self,
        submit: Callable[[str, str, float], Awaitable[Any]],
    ) -> None:
        self._submit = submit

    async def execute(
        self,
        recipient_agent_id: str,
        prompt: str,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = await self._submit(recipient_agent_id, prompt, timeout)
        if hasattr(result, "model_dump"):
            return dict(result.model_dump(mode="json", exclude_none=True))
        if isinstance(result, dict):
            return result
        raise TypeError("Delegation callable returned an invalid Task result")


__all__ = ["DelegateTaskTool"]
