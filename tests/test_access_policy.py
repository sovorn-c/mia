"""Contract tests for fail-closed Agent access policy enforcement."""

from __future__ import annotations

import pytest

from mia_middleware.access import (
    AccessPolicyMiddleware,
    ApprovalRequest,
    PolicyRejectedError,
)
from mia_middleware.pipeline import ToolCallContext, ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware, SecurityViolationError


@pytest.mark.asyncio
async def test_approval_required_reads_automatically_and_asks_for_side_effects() -> None:
    approvals: list[ApprovalRequest] = []
    executed: list[str] = []

    def approve(request: object) -> bool:
        approvals.append(request)
        return True

    policy = AccessPolicyMiddleware(
        access_policy="approval-required",
        capabilities={"read_file", "write_file", "bash"},
        approval_callback=approve,
        agent_id="mia",
        run_id="run-1",
        task_id="root",
        session_id="session-1",
    )
    pipeline = ToolPipeline([policy])

    read = ToolCallContext(tool_name="read_file", arguments={"path": "README.md"})
    assert await pipeline.execute(read, lambda: executed.append("read") or "contents") == "contents"
    assert approvals == []

    write = ToolCallContext(
        tool_name="write_file",
        arguments={"path": "notes.txt", "content": "hello"},
    )
    assert await pipeline.execute(write, lambda: executed.append("write") or "written") == "written"
    assert len(approvals) == 1
    assert executed == ["read", "write"]
    assert approvals[0].tool_name == "write_file"
    assert approvals[0].agent_id == "mia"


@pytest.mark.asyncio
async def test_missing_or_denied_approval_never_reaches_executor() -> None:
    for callback in (None, lambda _request: False):
        executed = False
        policy = AccessPolicyMiddleware(
            access_policy="approval-required",
            capabilities={"bash"},
            approval_callback=callback,
        )
        with pytest.raises(PolicyRejectedError):
            await ToolPipeline([policy]).execute(
                ToolCallContext(tool_name="bash", arguments={"command": "echo hi"}),
                lambda: "must not run",
            )
        assert executed is False


@pytest.mark.asyncio
async def test_read_only_and_unknown_tools_are_rejected_before_execution() -> None:
    policy = AccessPolicyMiddleware(access_policy="read-only", capabilities=None)
    for tool_name in ("write_file", "unknown_tool"):
        with pytest.raises(PolicyRejectedError):
            await ToolPipeline([policy]).execute(
                ToolCallContext(tool_name=tool_name, arguments={}),
                lambda: pytest.fail("policy must reject before execution"),
            )


@pytest.mark.asyncio
async def test_security_guard_remains_mandatory_after_approval() -> None:
    policy = AccessPolicyMiddleware(
        access_policy="full-access",
        capabilities={"bash"},
        full_access_confirmed=True,
        approval_callback=lambda _request: pytest.fail("full access should not ask"),
    )
    with pytest.raises(SecurityViolationError):
        await ToolPipeline([policy, SecurityGuardMiddleware()]).execute(
            ToolCallContext(tool_name="bash", arguments={"command": "rm -rf /"}),
            lambda: "must not run",
        )
