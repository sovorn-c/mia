"""Contract tests for fail-closed Agent access policy enforcement."""

from __future__ import annotations

import pytest

from mia_middleware.access import (
    AccessPolicyMiddleware,
    ApprovalRequest,
    PolicyRejectedError,
    compose_effective_access,
    normalize_access_level,
    tool_effect,
)
from mia_middleware.pipeline import ToolCallContext, ToolPipeline
from mia_middleware.telemetry import AuditLogMiddleware
from mia_middleware.security import SecurityGuardMiddleware, SecurityViolationError
from mia_tools.bash import BashTool
from mia_tools.fs import ReadFileTool, WriteFileTool


def test_access_levels_map_legacy_values_and_unknown_tools_fail_closed() -> None:
    assert normalize_access_level("read_only") == "read-only"
    assert normalize_access_level("standard") == "approval-required"
    assert normalize_access_level("full_access") == "full-access"
    assert normalize_access_level("no_tools") == "approval-required"
    assert tool_effect("read_file") == "non-mutating"
    assert tool_effect("unknown_plugin_tool") == "side-effecting"
    assert ReadFileTool.effect == "non-mutating"
    assert WriteFileTool.effect == "side-effecting"
    assert BashTool.effect == "side-effecting"
    with pytest.raises(ValueError, match="Unknown access policy"):
        normalize_access_level("auto")


def test_effective_access_is_restrictive_and_intersects_capabilities() -> None:
    effective = compose_effective_access(
        "full-access",
        "approval-required",
        {"read_file", "write_file"},
        {"read_file", "bash"},
    )
    assert effective.access_level == "approval-required"
    assert effective.capabilities == {"read_file"}

    no_tools = compose_effective_access("approval-required", "full-access", set(), None)
    assert no_tools.access_level == "approval-required"
    assert no_tools.capabilities == set()


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
async def test_unknown_tools_are_side_effecting_and_approval_is_sanitized() -> None:
    requests: list[ApprovalRequest] = []

    def approve(request: ApprovalRequest) -> bool:
        requests.append(request)
        return True

    policy = AccessPolicyMiddleware(
        access_policy="approval-required",
        approval_callback=approve,
        agent_id="mia",
    )
    await ToolPipeline([policy]).execute(
        ToolCallContext(
            tool_name="plugin_tool",
            arguments={"authorization": "Bearer secret", "value": "sk-secret"},
        ),
        lambda: "ok",
    )
    assert requests[0].effect == "side-effecting"
    assert requests[0].arguments == {
        "authorization": "[REDACTED]",
        "value": "[REDACTED]",
    }


@pytest.mark.asyncio
async def test_audit_records_are_attributed_and_redacted() -> None:
    audit = AuditLogMiddleware()
    ctx = ToolCallContext(
        session_id="session-1",
        tool_name="write_file",
        arguments={"content": "safe", "api_key": "sk-never-log"},
        metadata={"agent_id": "mia", "run_id": "run-1", "task_id": "task-1"},
    )
    await ToolPipeline([audit]).execute(ctx, lambda: "ok")

    record = audit.logs[0]
    assert record.agent_id == "mia"
    assert record.run_id == "run-1"
    assert record.task_id == "task-1"
    assert record.arguments["api_key"] == "[REDACTED]"
    assert "sk-never-log" not in str(record.model_dump())


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
