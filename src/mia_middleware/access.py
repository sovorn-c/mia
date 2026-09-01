"""Frontend-independent Agent access and approval enforcement."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from mia_middleware.pipeline import ToolCallContext

AccessLevel = Literal["read-only", "approval-required", "full-access"]
ToolEffect = Literal["non-mutating", "side-effecting"]
ApprovalCallback = Callable[["ApprovalRequest"], bool | Awaitable[bool]]

TOOL_EFFECTS: dict[str, ToolEffect] = {
    "read_file": "non-mutating",
    "write_file": "side-effecting",
    "edit_file": "side-effecting",
    "bash": "side-effecting",
}

_LEGACY_ACCESS: dict[str, AccessLevel] = {
    "standard": "approval-required",
    "read_only": "read-only",
    "full_access": "full-access",
    "no_tools": "approval-required",
}
_SECRET_KEY_PARTS = ("api_key", "apikey", "token", "secret", "authorization", "password")


class PolicyRejectedError(PermissionError):
    """Raised when access policy prevents a Tool invocation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Access policy rejected Tool invocation: {reason}")


class ApprovalRequest(BaseModel):
    """Sanitized, attributable request for one side-effecting Tool call."""

    agent_id: str = ""
    run_id: str = ""
    task_id: str = ""
    session_id: str = ""
    tool_name: str
    effect: ToolEffect
    arguments: dict[str, Any] = Field(default_factory=dict)


def normalize_access_level(value: str) -> AccessLevel:
    """Normalize the three target levels and deterministic legacy labels."""
    normalized = _LEGACY_ACCESS.get(value.strip().lower(), value.strip().lower())
    if normalized not in {"read-only", "approval-required", "full-access"}:
        raise ValueError("Unknown access policy. Use read-only, approval-required, or full-access.")
    return normalized  # type: ignore[return-value]


def tool_effect(tool_name: str, metadata: Mapping[str, Any] | None = None) -> ToolEffect:
    """Return declared Tool effect, defaulting unknown Tools to side-effecting."""
    declared = (metadata or {}).get("effect")
    if declared in {"non-mutating", "side-effecting"}:
        return cast(ToolEffect, declared)
    return TOOL_EFFECTS.get(tool_name, "side-effecting")


class AccessPolicyMiddleware:
    """Enforce capabilities, read-only mode, approvals, and full-access opt-in."""

    def __init__(
        self,
        *,
        access_policy: str = "approval-required",
        capabilities: Sequence[str] | None = None,
        approval_callback: ApprovalCallback | None = None,
        full_access_confirmed: bool = False,
        tool_effects: Mapping[str, ToolEffect] | None = None,
        agent_id: str = "",
        run_id: str = "",
        task_id: str = "",
        session_id: str = "",
    ) -> None:
        self.access_policy = normalize_access_level(access_policy)
        self.capabilities = None if capabilities is None else frozenset(capabilities)
        self.approval_callback = approval_callback
        self.full_access_confirmed = full_access_confirmed
        self.tool_effects = dict(tool_effects or {})
        self.agent_id = agent_id
        self.run_id = run_id
        self.task_id = task_id
        self.session_id = session_id
        self.approvals: list[ApprovalRequest] = []

    async def __call__(
        self,
        ctx: ToolCallContext,
        next_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        if self.capabilities is not None and ctx.tool_name not in self.capabilities:
            raise PolicyRejectedError(
                f"Tool '{ctx.tool_name}' is outside the Agent capability scope"
            )

        effect = self.tool_effects.get(ctx.tool_name) or tool_effect(ctx.tool_name, ctx.metadata)
        if self.access_policy == "read-only" and effect == "side-effecting":
            raise PolicyRejectedError(
                f"Tool '{ctx.tool_name}' is side-effecting under read-only access"
            )
        if self.access_policy == "full-access":
            if not self.full_access_confirmed:
                raise PolicyRejectedError("full-access requires explicit user confirmation")
            return await next_fn()
        if effect == "non-mutating":
            return await next_fn()

        if self.approval_callback is None:
            raise PolicyRejectedError(
                f"approval is required before side-effecting Tool '{ctx.tool_name}'"
            )
        request = ApprovalRequest(
            agent_id=self.agent_id or str(ctx.metadata.get("agent_id", "")),
            run_id=self.run_id or str(ctx.metadata.get("run_id", "")),
            task_id=self.task_id or str(ctx.metadata.get("task_id", "")),
            session_id=self.session_id or ctx.session_id,
            tool_name=ctx.tool_name,
            effect=effect,
            arguments=_sanitize(ctx.arguments),
        )
        self.approvals.append(request)
        decision = self.approval_callback(request)
        if inspect.isawaitable(decision):
            decision = await decision
        if not decision:
            raise PolicyRejectedError(f"approval denied for Tool '{ctx.tool_name}'")
        return await next_fn()


def _sanitize(value: Any, key: str = "") -> Any:
    """Redact credential-shaped keys and values in approval arguments."""
    key_text = key.lower().replace("-", "_")
    if any(part in key_text for part in _SECRET_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _sanitize(nested, str(k)) for k, nested in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key) for item in value]
    if isinstance(value, str) and (
        value.lower().startswith("bearer ") or value.startswith(("sk-", "ghp_", "xoxb-"))
    ):
        return "[REDACTED]"
    return value


__all__ = [
    "AccessLevel",
    "AccessPolicyMiddleware",
    "ApprovalCallback",
    "ApprovalRequest",
    "PolicyRejectedError",
    "TOOL_EFFECTS",
    "ToolEffect",
    "normalize_access_level",
    "tool_effect",
]
