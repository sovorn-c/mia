"""Filesystem coding tools: read_file, write_file, and edit_file."""

from __future__ import annotations

import asyncio
import difflib
from pathlib import Path
from typing import Any

from mia_tools.base import BaseTool

DEFAULT_MAX_BYTES = 50 * 1024
DEFAULT_MAX_LINES = 2000
UTF8_BOM = "\ufeff"

_file_locks: dict[Path, asyncio.Lock] = {}


def _get_lock(path: Path) -> asyncio.Lock:
    resolved = path.resolve()
    if resolved not in _file_locks:
        _file_locks[resolved] = asyncio.Lock()
    return _file_locks[resolved]


def is_binary_file(path: Path) -> bool:
    """Check if a file appears to be binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return False


def detect_line_ending(content: str) -> str:
    """Detect whether content uses CRLF or LF line endings."""
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def normalize_to_lf(content: str) -> str:
    """Normalize CRLF or CR to LF."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(content: str, line_ending: str) -> str:
    """Restore target line endings."""
    if line_ending == "\r\n":
        return content.replace("\n", "\r\n")
    return content


def generate_unified_diff(file_path: str, old_content: str, new_content: str) -> str:
    """Generate a unified diff string between old and new text."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


class ReadFileTool(BaseTool):
    """Tool to inspect file contents with line numbers and pagination."""

    name = "read_file"
    description = "Read file contents with line numbers. Supports offset and limit for large files."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative or absolute file path to read."},
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-indexed). Default is 1.",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. Default is 2000.",
                "default": 2000,
            },
        },
        "required": ["path"],
    }

    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    async def execute(
        self, path: str, offset: int = 1, limit: int = DEFAULT_MAX_LINES, **kwargs: Any
    ) -> str:
        target = (self.cwd / path).resolve() if not Path(path).is_absolute() else Path(path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if target.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: {path}")
        if is_binary_file(target):
            return f"Error: Cannot read binary file {path} as text."

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"Failed to read file {path}: {exc}") from exc

        if content.startswith(UTF8_BOM):
            content = content[len(UTF8_BOM) :]

        lines = content.splitlines()
        total_lines = len(lines)

        start_idx = max(0, offset - 1)
        if start_idx >= total_lines and total_lines > 0:
            return f"Offset {offset} is beyond end of file ({total_lines} lines total)."

        end_idx = min(start_idx + limit, total_lines)
        slice_lines = lines[start_idx:end_idx]

        # Format with line numbers: '1: line content'
        numbered_lines = [f"{start_idx + i + 1}: {line}" for i, line in enumerate(slice_lines)]
        output = "\n".join(numbered_lines)

        if len(output.encode("utf-8")) > DEFAULT_MAX_BYTES:
            output = output.encode("utf-8")[:DEFAULT_MAX_BYTES].decode("utf-8", errors="ignore")
            output += f"\n... [Truncated output at 50KB. Total lines: {total_lines}]"
        elif end_idx < total_lines:
            output += f"\n... [{total_lines - end_idx} more lines in file. Use offset={end_idx + 1} to read more.]"

        return output


class WriteFileTool(BaseTool):
    """Tool to create or overwrite a file atomically."""

    name = "write_file"
    description = (
        "Write content to a file. Automatically creates parent directories if they do not exist."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target file path."},
            "content": {"type": "string", "description": "Text content to write."},
        },
        "required": ["path", "content"],
    }

    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        target = (self.cwd / path).resolve() if not Path(path).is_absolute() else Path(path)

        lock = _get_lock(target)
        async with lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return f"Successfully wrote {len(content)} characters to {path}."


class EditFileTool(BaseTool):
    """Tool to perform exact, unique text replacements on a file."""

    name = "edit_file"
    description = (
        "Make precise changes to a file by replacing oldText with newText. "
        "Each oldText block must appear exactly once in the target file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit."},
            "edits": {
                "type": "array",
                "description": "List of replacement blocks containing oldText and newText.",
                "items": {
                    "type": "object",
                    "properties": {
                        "oldText": {
                            "type": "string",
                            "description": "Exact text to find and replace.",
                        },
                        "newText": {"type": "string", "description": "New text to substitute."},
                    },
                    "required": ["oldText", "newText"],
                },
            },
            "oldText": {"type": "string", "description": "Legacy single edit oldText fallback."},
            "newText": {"type": "string", "description": "Legacy single edit newText fallback."},
        },
        "required": ["path"],
    }

    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    async def execute(
        self,
        path: str,
        edits: list[dict[str, str]] | None = None,
        oldText: str | None = None,
        newText: str | None = None,
        **kwargs: Any,
    ) -> str:
        target = (self.cwd / path).resolve() if not Path(path).is_absolute() else Path(path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if target.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Normalize edits parameter
        edit_list: list[dict[str, str]] = []
        if edits:
            edit_list.extend(edits)
        elif oldText is not None and newText is not None:
            edit_list.append({"oldText": oldText, "newText": newText})
        else:
            raise ValueError("Must provide either 'edits' list or 'oldText' and 'newText'.")

        lock = _get_lock(target)
        async with lock:
            with open(target, encoding="utf-8", newline="") as f:
                raw = f.read()
            has_bom = raw.startswith(UTF8_BOM)
            content = raw[len(UTF8_BOM) :] if has_bom else raw

            line_ending = detect_line_ending(content)
            norm_content = normalize_to_lf(content)
            working_content = norm_content

            for i, edit in enumerate(edit_list):
                old_t = normalize_to_lf(edit.get("oldText", ""))
                new_t = normalize_to_lf(edit.get("newText", ""))

                if not old_t:
                    raise ValueError(f"Edit #{i + 1}: oldText cannot be empty.")

                occurrences = working_content.count(old_t)
                if occurrences == 0:
                    raise ValueError(
                        f"Edit #{i + 1} failed: oldText not found in {path}. Make sure whitespace and indentation match exactly."
                    )
                if occurrences > 1:
                    raise ValueError(
                        f"Edit #{i + 1} failed: oldText matches {occurrences} locations in {path}. Provide more surrounding context to make the match unique."
                    )

                working_content = working_content.replace(old_t, new_t, 1)

            final_content = restore_line_endings(working_content, line_ending)
            if has_bom:
                final_content = UTF8_BOM + final_content

            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(final_content)

        diff = generate_unified_diff(path, norm_content, working_content)
        return f"Successfully applied {len(edit_list)} edit(s) to {path}.\n\nDiff:\n{diff}"
