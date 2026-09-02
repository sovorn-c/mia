"""Contract tests for Agent-owned Notes Plugin Tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.plugins import NotesPlugin


@pytest.mark.asyncio
async def test_notes_tools_create_list_and_read_inside_agent_data_root(tmp_path: Path) -> None:
    tools = NotesPlugin().build_tools(
        agent_id="alpha",
        data_dir=tmp_path / "alpha-notes",
        config={},
    )
    by_name = {tool.name: tool for tool in tools}

    created = await by_name["note_create"].execute(title="Launch", content="Ship Notes")
    assert created["title"] == "Launch"
    assert created["content"] == "Ship Notes"
    assert len(created["note_id"]) == 32

    listed = await by_name["note_list"].execute()
    assert [note["note_id"] for note in listed] == [created["note_id"]]
    assert await by_name["note_read"].execute(note_id=created["note_id"]) == created

    with pytest.raises(ValueError, match="note ID"):
        await by_name["note_read"].execute(note_id="../outside")
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.asyncio
async def test_notes_data_roots_are_isolated_between_agents(tmp_path: Path) -> None:
    alpha = NotesPlugin().build_tools(agent_id="alpha", data_dir=tmp_path / "alpha", config={})
    beta = NotesPlugin().build_tools(agent_id="beta", data_dir=tmp_path / "beta", config={})
    created = await alpha[0].execute(title="Alpha", content="private")

    assert await alpha[1].execute() == [created]
    assert await beta[1].execute() == []
    with pytest.raises(FileNotFoundError):
        await beta[2].execute(note_id=created["note_id"])


@pytest.mark.asyncio
async def test_notes_tools_reject_a_symlinked_data_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = tmp_path / "linked-notes"
    linked_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        NotesPlugin().build_tools(agent_id="alpha", data_dir=linked_root, config={})
