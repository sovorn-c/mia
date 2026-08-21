"""Security middleware preventing execution of destructive commands and access to sensitive paths."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from mia_middleware.pipeline import ToolCallContext


class SecurityViolationError(PermissionError):
    """Raised when a tool execution violates security guardrails."""


# Patterns matching dangerous shell commands
DEFAULT_BLOCKED_COMMAND_PATTERNS = [
    r"rm\s+-(?:r|f|rf|fr)\s+(?:/|~|\$HOME|\.\./\.\./)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
    r"mkfs\.[a-z0-9]+",
    r"dd\s+if=.*of=/dev/(?:sda|sdb|nvme|disk)",
    r"chmod\s+-(?:R|r)\s+777\s+/",
    r">\s*/dev/(?:sda|sdb|nvme|kmem|mem)",
]

# Sensitive file paths that should never be accessed
DEFAULT_BLOCKED_PATHS = [
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/master.passwd",
    "/dev/mem",
    "/dev/kmem",
]


class SecurityGuardMiddleware:
    """Middleware enforcing filesystem and command safety policies."""

    def __init__(
        self,
        blocked_command_patterns: list[str] | None = None,
        blocked_paths: list[str] | None = None,
        raise_on_violation: bool = True,
    ) -> None:
        self.blocked_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in (blocked_command_patterns or DEFAULT_BLOCKED_COMMAND_PATTERNS)
        ]
        self.blocked_paths = set(blocked_paths or DEFAULT_BLOCKED_PATHS)
        self.raise_on_violation = raise_on_violation

    async def __call__(
        self,
        ctx: ToolCallContext,
        next_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        # 1. Shell command safety
        if ctx.tool_name == "bash":
            command = str(ctx.arguments.get("command", ""))
            for pattern in self.blocked_patterns:
                if pattern.search(command):
                    msg = f"Security Violation: Command '{command}' was blocked by safety policy."
                    if self.raise_on_violation:
                        raise SecurityViolationError(msg)
                    return f"Error: {msg}"

        # 2. Filesystem path safety
        if ctx.tool_name in {"read_file", "write_file", "edit_file"}:
            path = str(ctx.arguments.get("path", "")).strip()
            if path in self.blocked_paths:
                msg = f"Security Violation: Access to restricted path '{path}' was blocked."
                if self.raise_on_violation:
                    raise SecurityViolationError(msg)
                return f"Error: {msg}"

        return await next_fn()
