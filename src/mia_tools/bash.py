"""Asynchronous shell command execution tool."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any

from mia_tools.base import BaseTool

DEFAULT_MAX_BYTES = 50 * 1024
DEFAULT_MAX_LINES = 2000


class BashTool(BaseTool):
    """Tool to execute shell commands asynchronously with process isolation."""

    name = "bash"
    description = (
        "Execute a shell command asynchronously in the project directory. "
        "Captures combined stdout and stderr."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command line to execute."},
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds before terminating process (default: 60.0).",
                "default": 60.0,
            },
        },
        "required": ["command"],
    }

    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd()

    async def execute(self, command: str, timeout: float = 60.0, **kwargs: Any) -> str:
        if not command or not command.strip():
            raise ValueError("Command cannot be empty.")

        kwargs_proc: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "cwd": str(self.cwd),
        }

        if sys.platform != "win32":
            kwargs_proc["start_new_session"] = True

        proc = await asyncio.create_subprocess_shell(command, **kwargs_proc)

        try:
            stdout_data, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            # Terminate entire process group
            if sys.platform != "win32" and proc.pid:
                import contextlib

                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout} seconds: '{command}'") from None

        output = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
        exit_code = proc.returncode

        lines = output.splitlines()
        truncated = False
        if len(lines) > DEFAULT_MAX_LINES:
            lines = lines[-DEFAULT_MAX_LINES:]
            truncated = True

        result_text = "\n".join(lines)
        if len(result_text.encode("utf-8")) > DEFAULT_MAX_BYTES:
            result_text = result_text.encode("utf-8")[-DEFAULT_MAX_BYTES:].decode(
                "utf-8", errors="ignore"
            )
            truncated = True

        prefix = f"[Exit code: {exit_code}]\n" if exit_code != 0 else ""
        suffix = "\n[Output truncated due to size limits]" if truncated else ""

        return f"{prefix}{result_text}{suffix}".strip()
