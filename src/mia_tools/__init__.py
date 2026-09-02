"""Mia Tools - Built-in coding tools."""

from mia_tools.base import BaseTool
from mia_tools.bash import BashTool
from mia_tools.delegate import DelegateTaskTool
from mia_tools.fs import (
    EditFileTool,
    ReadFileTool,
    WriteFileTool,
    detect_line_ending,
    generate_unified_diff,
    normalize_to_lf,
    restore_line_endings,
)
from mia_tools.notes import Note, NoteCreateTool, NoteListTool, NoteReadTool

__all__ = [
    "BaseTool",
    "DelegateTaskTool",
    "BashTool",
    "EditFileTool",
    "ReadFileTool",
    "WriteFileTool",
    "Note",
    "NoteCreateTool",
    "NoteListTool",
    "NoteReadTool",
    "detect_line_ending",
    "generate_unified_diff",
    "normalize_to_lf",
    "restore_line_endings",
]
