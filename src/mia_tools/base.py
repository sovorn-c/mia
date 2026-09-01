"""Base tool class and metadata helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mia_ai.types import ToolDefinition


class BaseTool(ABC):
    """Abstract base class for all Mia tools."""

    name: str
    description: str
    parameters: dict[str, Any]
    effect: str = "side-effecting"

    def to_tool_definition(self) -> ToolDefinition:
        """Convert this tool into an AI-ready ToolDefinition schema."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool with the validated arguments."""
        pass

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.execute(*args, **kwargs)
