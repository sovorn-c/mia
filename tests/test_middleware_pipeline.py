"""Tests for the Onion Middleware Pipeline and built-in guardrails."""

from __future__ import annotations

import pytest

from mia_agent.harness import AgentHarness
from mia_ai.providers.mock import MockProvider
from mia_middleware.pipeline import ToolCallContext, ToolPipeline
from mia_middleware.security import SecurityGuardMiddleware, SecurityViolationError
from mia_middleware.telemetry import (
    AuditLogMiddleware,
    BudgetExceededError,
    CostBudgetMiddleware,
)


@pytest.mark.asyncio
async def test_tool_pipeline_onion_execution_order() -> None:
    order: list[str] = []

    async def middleware_1(ctx: ToolCallContext, next_fn):
        order.append("m1_pre")
        res = await next_fn()
        order.append("m1_post")
        return res

    async def middleware_2(ctx: ToolCallContext, next_fn):
        order.append("m2_pre")
        res = await next_fn()
        order.append("m2_post")
        return res

    async def core():
        order.append("core")
        return "result"

    pipeline = ToolPipeline([middleware_1, middleware_2])
    ctx = ToolCallContext(tool_name="test_tool", arguments={})

    result = await pipeline.execute(ctx, core)

    assert result == "result"
    assert order == ["m1_pre", "m2_pre", "core", "m2_post", "m1_post"]


@pytest.mark.asyncio
async def test_tool_pipeline_argument_mutation() -> None:
    async def rewrite_path(ctx: ToolCallContext, next_fn):
        if "path" in ctx.arguments:
            ctx.arguments["path"] = f"/sandbox/{ctx.arguments['path']}"
        return await next_fn()

    pipeline = ToolPipeline([rewrite_path])
    ctx = ToolCallContext(tool_name="read_file", arguments={"path": "test.txt"})

    captured_args = {}

    async def core():
        captured_args.update(ctx.arguments)
        return "content"

    await pipeline.execute(ctx, core)
    assert captured_args["path"] == "/sandbox/test.txt"


@pytest.mark.asyncio
async def test_security_guard_middleware_blocks_dangerous_commands() -> None:
    guard = SecurityGuardMiddleware(raise_on_violation=True)
    pipeline = ToolPipeline([guard])

    dangerous_commands = [
        "rm -rf /",
        "rm -rf ~",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda",
        "chmod -R 777 /",
    ]

    for cmd in dangerous_commands:
        ctx = ToolCallContext(tool_name="bash", arguments={"command": cmd})
        with pytest.raises(SecurityViolationError):
            await pipeline.execute(ctx, lambda: "never reached")

    # Safe command should pass
    safe_ctx = ToolCallContext(tool_name="bash", arguments={"command": "ls -la src/"})
    res = await pipeline.execute(safe_ctx, lambda: "file1 file2")
    assert res == "file1 file2"


@pytest.mark.asyncio
async def test_security_guard_middleware_blocks_sensitive_paths() -> None:
    guard = SecurityGuardMiddleware(raise_on_violation=True)
    pipeline = ToolPipeline([guard])

    restricted_ctx = ToolCallContext(tool_name="read_file", arguments={"path": "/etc/shadow"})
    with pytest.raises(SecurityViolationError):
        await pipeline.execute(restricted_ctx, lambda: "secret")


@pytest.mark.asyncio
async def test_cost_budget_middleware_enforces_limits() -> None:
    budget = CostBudgetMiddleware(max_tool_calls_per_turn=2)
    pipeline = ToolPipeline([budget])

    ctx = ToolCallContext(tool_name="ping", arguments={})

    # Call 1: OK
    await pipeline.execute(ctx, lambda: "ok 1")
    # Call 2: OK
    await pipeline.execute(ctx, lambda: "ok 2")
    # Call 3: Exceeds limit
    with pytest.raises(BudgetExceededError):
        await pipeline.execute(ctx, lambda: "ok 3")


@pytest.mark.asyncio
async def test_audit_log_middleware_records_traces() -> None:
    audit = AuditLogMiddleware()
    pipeline = ToolPipeline([audit])

    ctx = ToolCallContext(
        session_id="sess_123",
        step_index=2,
        call_id="call_99",
        tool_name="read_file",
        arguments={"path": "config.yaml"},
    )

    async def core():
        return "yaml content"

    res = await pipeline.execute(ctx, core)
    assert res == "yaml content"

    assert len(audit.logs) == 1
    log = audit.logs[0]
    assert log.session_id == "sess_123"
    assert log.step_index == 2
    assert log.tool_name == "read_file"
    assert log.arguments == {"path": "config.yaml"}
    assert log.is_error is False
    assert log.duration_ms >= 0


@pytest.mark.asyncio
async def test_agent_harness_with_pipeline_integration() -> None:
    mock = MockProvider()
    mock.queue_tool_call_response(
        tool_name="bash",
        arguments={"command": "rm -rf /"},
        call_id="call_danger",
    )
    mock.queue_text_response("Blocked dangerous command.")

    guard = SecurityGuardMiddleware(raise_on_violation=True)
    pipeline = ToolPipeline([guard])

    harness = AgentHarness(
        provider=mock,
        model="mock-model",
        pipeline=pipeline,
        tool_executor=lambda name, args: "executed",
    )

    events = [e async for e in harness.prompt("Please delete root")]

    tool_result = next(e for e in events if e.type == "tool_result")
    assert tool_result.is_error is True
    assert "Security Violation" in str(tool_result.output)


@pytest.mark.asyncio
async def test_tool_pipeline_rejects_duplicate_execution_attempts() -> None:
    async def duplicate_calling_middleware(ctx: ToolCallContext, next_fn):
        await next_fn()
        return await next_fn()

    executed = 0

    async def core():
        nonlocal executed
        executed += 1
        return "ok"

    pipeline = ToolPipeline([duplicate_calling_middleware])
    ctx = ToolCallContext(tool_name="test_tool", arguments={})
    with pytest.raises(RuntimeError, match="cannot be invoked more than once"):
        await pipeline.execute(ctx, core)
    assert executed == 1


@pytest.mark.asyncio
async def test_tool_pipeline_rejects_tool_identity_rewrite() -> None:
    async def rewrite_tool_name(ctx: ToolCallContext, next_fn):
        ctx.tool_name = "malicious_tool"
        return await next_fn()

    pipeline = ToolPipeline([rewrite_tool_name])
    ctx = ToolCallContext(tool_name="safe_tool", arguments={})
    with pytest.raises(ValueError, match="Tool identity cannot be modified"):
        await pipeline.execute(ctx, lambda: "core")


@pytest.mark.asyncio
async def test_tool_pipeline_rejects_attribution_rewrite() -> None:
    async def rewrite_attribution(ctx: ToolCallContext, next_fn):
        ctx.plugin_id = "spoofed_plugin"
        return await next_fn()

    pipeline = ToolPipeline([rewrite_attribution])
    ctx = ToolCallContext(tool_name="tool", plugin_id="orig_plugin", arguments={})
    with pytest.raises(ValueError, match="Tool attribution cannot be modified"):
        await pipeline.execute(ctx, lambda: "core")


@pytest.mark.asyncio
async def test_tool_pipeline_rejection_cannot_be_swallowed() -> None:
    async def swallowing_middleware(ctx: ToolCallContext, next_fn):
        try:
            return await next_fn()
        except Exception:
            return "swallowed_fake_success"

    async def failing_core():
        raise PermissionError("Core access rejected")

    pipeline = ToolPipeline([swallowing_middleware])
    ctx = ToolCallContext(tool_name="tool", arguments={})
    with pytest.raises(PermissionError, match="Core access rejected"):
        await pipeline.execute(ctx, failing_core)


@pytest.mark.asyncio
async def test_tool_pipeline_rejects_bypassed_execution() -> None:
    async def bypassing_middleware(ctx: ToolCallContext, next_fn):
        return "fabricated_result_without_calling_next"

    pipeline = ToolPipeline([bypassing_middleware])
    ctx = ToolCallContext(tool_name="tool", arguments={})
    with pytest.raises(RuntimeError, match="bypassed"):
        await pipeline.execute(ctx, lambda: "core")
