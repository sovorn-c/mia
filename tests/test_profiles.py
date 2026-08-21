"""Tests for Hermes + DSH Profile System."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_agent.harness import AgentHarness
from mia_agent.profiles.manager import ProfileManager
from mia_agent.profiles.model import AgentProfile
from mia_ai.providers.mock import MockProvider


def test_builtin_profiles_exist() -> None:
    manager = ProfileManager()
    coding = manager.get_profile("coding")
    architect = manager.get_profile("architect")
    minimal = manager.get_profile("minimal")
    code_mode = manager.get_profile("code_mode")

    assert coding.name == "coding"
    assert "read_file" in coding.tools
    assert "write_file" in coding.tools
    assert "bash" in coding.tools

    assert architect.name == "architect"
    assert architect.tools == ["read_file"]
    assert architect.permission == "read_only"

    assert minimal.name == "minimal"
    assert minimal.tools == []

    assert code_mode.execution_mode == "code"


def test_filter_tools_by_profile() -> None:
    manager = ProfileManager()
    architect = manager.get_profile("architect")

    class ReadTool:
        name = "read_file"

    class WriteTool:
        name = "write_file"

    class BashTool:
        name = "bash"

    all_tools = [ReadTool(), WriteTool(), BashTool()]
    allowed = manager.filter_tools(architect, all_tools)

    assert len(allowed) == 1
    assert allowed[0].name == "read_file"


def test_user_custom_profile_lifecycle(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    sessions_dir = tmp_path / "sessions"
    manager = ProfileManager(profiles_dir=profiles_dir, sessions_base_dir=sessions_dir)

    custom_profile = AgentProfile(
        name="custom_reviewer",
        description="Specialized code reviewer",
        system_prompt="Review pull requests carefully.",
        tools=["read_file"],
        temperature=0.1,
    )

    # Save
    saved_path = manager.save_user_profile(custom_profile)
    assert saved_path.exists()

    # Retrieve
    retrieved = manager.get_profile("custom_reviewer")
    assert retrieved.name == "custom_reviewer"
    assert retrieved.system_prompt == "Review pull requests carefully."

    # List
    all_profiles = manager.list_profiles()
    assert any(p.name == "custom_reviewer" for p in all_profiles)

    # Isolated session dir
    session_dir = manager.get_session_dir("custom_reviewer")
    assert session_dir == sessions_dir / "custom_reviewer"
    assert session_dir.exists()

    # Delete
    deleted = manager.delete_user_profile("custom_reviewer")
    assert deleted is True
    assert not saved_path.exists()


@pytest.mark.asyncio
async def test_harness_with_architect_profile() -> None:
    manager = ProfileManager()
    architect = manager.get_profile("architect")

    mock = MockProvider()
    mock.queue_text_response("Architecture review complete.")

    class ReadTool:
        name = "read_file"
        description = "Read file"
        parameters = {"type": "object", "properties": {"path": {"type": "string"}}}

    class WriteTool:
        name = "write_file"
        description = "Write file"
        parameters = {"type": "object", "properties": {"path": {"type": "string"}}}

    all_tools = [ReadTool(), WriteTool()]
    filtered_tools = manager.filter_tools(architect, all_tools)

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        system_prompt=architect.system_prompt,
        tools=filtered_tools,
    )

    events = [e async for e in harness.prompt("Review project")]
    assert len(events) > 0

    # Check that tool definition passed to provider was only read_file
    assert len(mock.recorded_calls) == 1
    tools_passed = mock.recorded_calls[0]["tools"]
    assert tools_passed is not None
    assert len(tools_passed) == 1
    assert tools_passed[0]["name"] == "read_file"
