"""Tests for built-in coding tools: read_file, write_file, edit_file, and bash."""

from __future__ import annotations

from pathlib import Path

import pytest

from mia_tools.bash import BashTool
from mia_tools.fs import EditFileTool, ReadFileTool, WriteFileTool


@pytest.mark.asyncio
async def test_read_and_write_file_tools(tmp_path: Path) -> None:
    write_tool = WriteFileTool(cwd=tmp_path)
    read_tool = ReadFileTool(cwd=tmp_path)

    # Write file
    res = await write_tool.execute(path="subdir/test.txt", content="line 1\nline 2\nline 3\n")
    assert "Successfully wrote" in res

    # Read full file
    content = await read_tool.execute(path="subdir/test.txt")
    assert content == "1: line 1\n2: line 2\n3: line 3"

    # Read with offset and limit
    slice_content = await read_tool.execute(path="subdir/test.txt", offset=2, limit=1)
    assert slice_content == "2: line 2\n... [1 more lines in file. Use offset=3 to read more.]"


@pytest.mark.asyncio
async def test_read_file_binary_and_missing(tmp_path: Path) -> None:
    read_tool = ReadFileTool(cwd=tmp_path)

    # Missing file
    with pytest.raises(FileNotFoundError):
        await read_tool.execute(path="missing.txt")

    # Binary file
    bin_file = tmp_path / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")
    res = await read_tool.execute(path="data.bin")
    assert "Cannot read binary file" in res


@pytest.mark.asyncio
async def test_edit_file_exact_match(tmp_path: Path) -> None:
    edit_tool = EditFileTool(cwd=tmp_path)
    target = tmp_path / "code.py"
    target.write_text("def hello():\n    print('old')\n")

    res = await edit_tool.execute(
        path="code.py",
        edits=[{"oldText": "print('old')", "newText": "print('new')"}],
    )

    assert "Successfully applied 1 edit(s)" in res
    assert "-    print('old')" in res
    assert "+    print('new')" in res
    assert target.read_text() == "def hello():\n    print('new')\n"


@pytest.mark.asyncio
async def test_edit_file_non_matching_fails(tmp_path: Path) -> None:
    edit_tool = EditFileTool(cwd=tmp_path)
    target = tmp_path / "code.py"
    target.write_text("def hello():\n    pass\n")

    with pytest.raises(ValueError, match="not found"):
        await edit_tool.execute(
            path="code.py",
            edits=[{"oldText": "def missing():", "newText": "def found():"}],
        )

    # File should be unchanged
    assert target.read_text() == "def hello():\n    pass\n"


@pytest.mark.asyncio
async def test_edit_file_ambiguous_match_fails(tmp_path: Path) -> None:
    edit_tool = EditFileTool(cwd=tmp_path)
    target = tmp_path / "code.py"
    target.write_text("val = 1\nval = 1\n")

    with pytest.raises(ValueError, match="matches 2 locations"):
        await edit_tool.execute(
            path="code.py",
            edits=[{"oldText": "val = 1", "newText": "val = 2"}],
        )

    assert target.read_text() == "val = 1\nval = 1\n"


@pytest.mark.asyncio
async def test_edit_file_preserves_crlf_and_bom(tmp_path: Path) -> None:
    edit_tool = EditFileTool(cwd=tmp_path)
    target = tmp_path / "crlf.txt"
    target.write_bytes("\ufefffirst line\r\nsecond line\r\n".encode("utf-8"))

    await edit_tool.execute(
        path="crlf.txt",
        edits=[{"oldText": "second line", "newText": "modified line"}],
    )

    result_bytes = target.read_bytes()
    expected = "\ufefffirst line\r\nmodified line\r\n".encode("utf-8")
    assert result_bytes == expected


@pytest.mark.asyncio
async def test_bash_tool_execution(tmp_path: Path) -> None:
    bash = BashTool(cwd=tmp_path)

    # Standard command
    out = await bash.execute("echo 'Hello Mia'")
    assert out == "Hello Mia"

    # Non-zero exit code
    out_err = await bash.execute("python3 -c 'import sys; sys.exit(42)'")
    assert "[Exit code: 42]" in out_err


@pytest.mark.asyncio
async def test_bash_tool_timeout(tmp_path: Path) -> None:
    bash = BashTool(cwd=tmp_path)

    with pytest.raises(TimeoutError, match="timed out"):
        await bash.execute("python3 -c 'import time; time.sleep(10)'", timeout=0.2)
