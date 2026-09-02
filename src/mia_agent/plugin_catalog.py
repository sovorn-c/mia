"""Bundled Plugin implementations and their public manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mia_agent.plugin_models import AgentTemplate, PluginManifest, PluginToolSpec
from mia_tools.base import BaseTool


class NotesPlugin:
    """Bundled Notes contribution used by the initial Plugin vertical slice."""

    plugin_id = "notes"

    @property
    def manifest(self) -> PluginManifest:
        return notes_manifest()

    def build_tools(
        self,
        *,
        agent_id: str,
        data_dir: Path,
        config: dict[str, Any],
    ) -> list[BaseTool]:
        """Build Notes Tools against the one data root selected by Mia Core."""
        del agent_id, config
        from mia_tools.notes import NoteCreateTool, NoteListTool, NoteReadTool

        return [
            NoteCreateTool(data_dir),
            NoteListTool(data_dir),
            NoteReadTool(data_dir),
        ]


def notes_manifest() -> PluginManifest:
    """Return the bundled Notes manifest and its safe Agent Template."""
    return PluginManifest(
        plugin_id="notes",
        version="1.0.0",
        display_name="Notes",
        description="Private Agent-owned local notes.",
        templates=[
            AgentTemplate(
                template_id="notes-agent",
                version="1.0.0",
                display_name="Notes Agent",
                description="A focused Agent for private local notes.",
                instructions="You are a careful Agent for creating and retrieving private notes.",
                tools=[],
                required_plugins=["notes"],
                plugin_config={"notes": {"notebook_name": "Personal"}},
            )
        ],
        tool_specs=[
            PluginToolSpec(
                name="note_create",
                description="Create a private note for this Agent.",
                effect="side-effecting",
            ),
            PluginToolSpec(
                name="note_list",
                description="List private notes owned by this Agent.",
                effect="non-mutating",
            ),
            PluginToolSpec(
                name="note_read",
                description="Read one private note owned by this Agent.",
                effect="non-mutating",
            ),
        ],
    )


__all__ = ["NotesPlugin", "notes_manifest"]
