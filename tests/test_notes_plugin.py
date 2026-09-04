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
async def test_notes_tools_reject_invalid_note_input(tmp_path: Path) -> None:
    tools = NotesPlugin().build_tools(
        agent_id="alpha",
        data_dir=tmp_path / "alpha-notes",
        config={},
    )
    create = tools[0]

    with pytest.raises(ValueError, match="title"):
        await create.execute(title=" ", content="body")
    with pytest.raises(ValueError, match="too long"):
        await create.execute(title="x" * 201, content="body")
    with pytest.raises(ValueError, match="text"):
        await create.execute(title="Title", content=123)
    with pytest.raises(ValueError, match="too long"):
        await create.execute(title="Title", content="x" * 1_000_001)


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


@pytest.mark.asyncio
async def test_notes_activation_through_plugin_context_and_retention(tmp_path: Path) -> None:
    from mia_agent.plugin_catalog import NotesPlugin, notes_manifest
    from mia_agent.plugin_host import PluginContext

    manifest = notes_manifest()
    data_dir = tmp_path / "notes_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    ctx = PluginContext(
        plugin_id="notes",
        agent_id="agent_alpha",
        config={},
        data_dir=data_dir,
        manifest=manifest,
    )

    plugin = NotesPlugin()
    await plugin.activate(ctx)

    # 1. Check tools are registered with proper attribution and effects
    assert len(ctx._tools) == 3
    tool_map = {t.name: t for t in ctx._tools}
    assert "note_create" in tool_map
    assert "note_list" in tool_map
    assert "note_read" in tool_map
    for t in ctx._tools:
        assert getattr(t, "plugin_id", None) == "notes"

    # 2. Execute note_create and verify note file exists on disk
    created = await tool_map["note_create"].execute(title="Important Note", content="Retained data")
    note_id = created["note_id"]
    note_file = data_dir / f"{note_id}.json"
    assert note_file.exists()

    # 3. Simulate disablement (no plugin context or tools active) and verify data is retained
    assert note_file.exists()

    # 4. Re-activate and verify data is readable
    ctx2 = PluginContext(
        plugin_id="notes",
        agent_id="agent_alpha",
        config={},
        data_dir=data_dir,
        manifest=manifest,
    )
    await plugin.activate(ctx2)
    tool_map2 = {t.name: t for t in ctx2._tools}
    read_note = await tool_map2["note_read"].execute(note_id=note_id)
    assert read_note["title"] == "Important Note"
    assert read_note["content"] == "Retained data"
