# e07s03 — Final Core Tool Validation and Plugin Boundary

## 1. Identity

- **Story ID:** e07s03
- **Epic:** e07 — Production Runtime Integrity
- **Type:** hardening
- **Risk:** P0
- **Context:** Plugin Tools, ToolPipeline, access/security/audit middleware, runtime events, and tests
- **BCPs:** 6
- **Status:** passing
- **Requirement delta:** ADDED

## 2. User Story

As a Mia operator, I want Core to validate the final Tool call and terminal outcome after optional Plugin behavior so that extensions cannot bypass policy, forge attribution, or turn a rejected operation into success.

## 3. Context

The existing `AgentRuntimeFactory` resolves bundled Plugin Tools, merges their names into Agent capabilities, rejects duplicate Tool names, and builds a `ToolPipeline` around the harness (`src/mia_agent/runtime_factory.py:64-128`). `ToolPipeline` is an onion runner in which middleware may inspect or transform `ToolCallContext.arguments` before the core executor (`src/mia_middleware/pipeline.py:28-57`). Current policy and security tests establish individual controls, but the production blueprint requires a final Core validation boundary after any optional transformation and terminal truth outside Plugin behavior. The full governed installed-code host remains e08.

## 4. Problem

If a Plugin middleware transforms arguments after approval or if Plugin Tool declarations are trusted without a complete effect/collision check, the executed operation can differ from the reviewed operation. If Plugin-side errors or events can classify terminal state, a failed or rejected Run can be reported as success and attribution can be lost.

## 5. Goal

Harden the existing Plugin-compatible runtime seam: stage and validate all current Plugin Tool contributions deterministically, revalidate final Tool identity/arguments/effect/access/security before execution, keep attribution and audit mandatory, and ensure terminal normalization and cleanup decisions remain Core-owned.

## 6. Non-Goals

- The general e08 governed Core extension host, arbitrary installed-code callbacks, service graphs, or new Plugin contribution types.
- Provider/model replacement, Tool overrides, command/UI contributions, hot reload, remote catalogs, or package installation.
- OS/process sandboxing or forced termination of trusted Python.
- Redesign of ToolPipeline's general middleware API beyond the required final validation boundary.

## 7. Stakeholders

- Core security, policy, middleware, and runtime maintainers.
- Bundled Notes Plugin and future bounded Plugin authors.
- Operators relying on approval/audit evidence.
- CLI, REPL, TUI, and diagnostic consumers.

## 8. Dependencies

- e07s01 canonical Run finalization and terminal envelope contract.
- e07s02 effective settings, mandatory safeguards, and Session admission.
- Existing `PluginManager`, `PluginManifest`, `AgentRuntimeFactory`, `ToolPipeline`, `ToolCallContext`, and Tool effect map.
- e04/e05 Plugin attribution, fail-closed, and data-isolation contracts.
- `specs/tech-architecture/e07-TEST_PLAN_LATEST.md` scenarios SC-e07s03-P0-01 through P1-04.
- e08's later governed extension host must consume this boundary rather than replace it.

## 9. Assumptions

- Current bundled Plugin Tools remain the compatibility proof; e08 introduces the broader trusted-code host.
- Any optional middleware transformation is treated as untrusted input and is followed by Core validation.
- Tool identity, effect, Agent/Run/Session identity, approval state, and attribution are Core-owned.
- Plugin lifecycle failures are diagnostics and cleanup decisions; they do not rewrite completed domain-work truth.
- Cooperative asynchronous cleanup can be deadline-bounded when callbacks yield control; event-loop-blocking trusted code is outside a hard in-process guarantee.

## 10. Constraints

- Complete Plugin Tool sets are resolved before provider execution and become immutable for one Run.
- Duplicate or undeclared Tool names/effects reject the complete activation before any Tool executes.
- Approval evaluates final normalized arguments and effective policy, not pre-transformation arguments.
- Final Core validation cannot be skipped, reordered, swallowed, or replaced through supported Plugin behavior.
- Tool events and audit records retain Agent, Run, Task, Session, Tool, and optional Plugin attribution.
- Plugin errors are sanitized and cannot fabricate successful Tool or terminal results.

## 11. Domain Model

- **Plugin contribution set:** complete validated current Plugin Tool list and declarations for one Agent.
- **Staged registration:** contributions held unavailable until complete validation succeeds.
- **Final Core gate:** last validation of Tool identity, arguments, effect, capability, approval, security, size, and attribution before executor invocation.
- **Plugin lifecycle diagnostic:** attributed sanitized observer/cleanup failure that does not change domain-work truth.
- **Terminal truth:** Core-owned finalized Run outcome and matching envelope, outside Plugin hooks.

## 12. Requirements

### ADDED: Complete deterministic Plugin Tool boundary

Core MUST validate installation state, compatibility, Agent enablement, declared Tool names/effects, duplicate collisions, and attribution for the complete current Plugin Tool set before exposing any Plugin Tool to a provider or harness. Failure MUST reject the complete set without partial execution.

### ADDED: Final Core Tool validation

After any optional Plugin middleware or Tool argument transformation, Core MUST revalidate Tool identity, final arguments, declared effect, Agent capability, access policy, approval, security constraints, output bounds, and attribution immediately before the Tool executor. Approval MUST describe the final normalized arguments.

### ADDED: Non-forgeable Tool and terminal truth

Plugin behavior MUST NOT change Tool identity, Agent/Run/Session identity, effect classification, call Core more than once, swallow a Core rejection, fabricate a successful Tool result without execution, suppress mandatory audit, or classify Run terminal state. Terminal normalization and finalization remain outside Plugin hooks.

### ADDED: Core-owned lifecycle decision

For any supported optional Plugin observer/disposer seam, Core MUST request reverse-order cooperative cleanup and reach a completion-or-timeout decision before terminal delivery when callbacks yield control. A timeout is diagnosed and quarantines the offending Plugin until process restart; event-loop-blocking trusted code can delay this decision and is recovered by process restart, not forced in-process termination.

### MODIFIED: Plugin attribution and compatibility

**Before:** Existing Plugin Tools carry the current optional attribution fields and are composed alongside built-ins, but the final post-transformation validation and terminal boundary are implicit.

**After:** Plugin Tool calls, results, diagnostics, and audits are attributed through a Core-owned final validation boundary; Plugin-free Agents preserve existing event discriminators, Tool policy, and frontend behavior.

## 13. Non-Functional Requirements

- **Security:** no middleware bypass, approval confusion, effect downgrade, identity spoofing, secret leak, or forged success.
- **Determinism:** contribution ordering, collision errors, middleware order, and final validation are stable.
- **Auditability:** attempted calls, final arguments, Plugin attribution, results, and lifecycle failures remain attributable and sanitized.
- **Compatibility:** Notes and Plugin-free runtimes preserve existing behavior and serialized event discriminators.
- **Resilience:** cooperative cleanup failures do not corrupt Session history or rewrite completed domain-work outcomes.

## 14. Contracts

### Existing contracts preserved

- `PluginManager.resolve_tools()` and Notes Tool names/effects/data isolation remain compatible.
- `ToolPipeline` retains onion ordering and asynchronous execution.
- Access policy, SecurityGuard, AuditLog, CostBudget, redaction, and AgentHarness contracts remain active.
- AgentRunner's final envelope and finalizer remain the only terminal truth source.

### New contracts

- Plugin contribution validation is complete-set and staged before execution.
- The final Core gate sees the same arguments approved and executed.
- Plugin hooks are observational/additive only at this boundary and cannot forge Tool or Run outcomes.
- Cleanup health is separately diagnosed and cannot rewrite domain-work truth.

## 15. Reason for Depth and Zoom-Out

- **Final Core gate:** required because middleware can transform arguments; validation before middleware is insufficient to prove the executed operation was permitted.
- **Complete-set staging:** required because partial Plugin activation creates nondeterministic Tool visibility and effect maps; a new generic activation planner is deferred to e08.
- **Attribution-preserving diagnostics:** required to make Plugin failures actionable without exposing secrets or allowing Plugin control of terminal truth.

`ToolPipeline` purpose: execute one Tool through ordered middleware and the Core executor. Callers: AgentHarness, access/policy tests, middleware tests, and end-to-end scenarios (`src/mia_agent/harness.py:31`, `src/mia_middleware/pipeline.py:28`). Contracts: async onion order, one core executor path, mutable-in-pipeline context for controlled transforms, and propagation of Core rejection/failure. This story adds the final Core guard around that existing seam; it does not turn ToolPipeline into a Plugin runtime.

## 16. Implementation Steps

1. Add failing tests for complete Plugin Tool staging, deterministic ordering, duplicate/undeclared contribution rejection, attribution, and Plugin-free compatibility (ref: `specs/tech-architecture/e07-TEST_PLAN_LATEST.md`, SC-e07s03-P0-01/P1-04) → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agent_runtime.py -k 'activation or duplicate or undeclared or attribution or plugin_free'`
2. Make current Plugin Tool resolution and effect-map construction complete-set, deterministic, and immutable before provider/harness execution (ref: `src/mia_agent/plugins.py`, `src/mia_agent/runtime_factory.py`) → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agent_runtime.py -k 'plugin or effect or duplicate or activation'`
3. Add the final Core Tool validation boundary after middleware argument transformation, ensuring approval uses final arguments and rejected calls cannot reach the executor → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_plugins.py -k 'transform or rewrite or final or approval or effect or security'`
4. Keep Tool events, audits, diagnostics, and terminal normalization outside Plugin control; add failure/forgery/duplicate-execution regressions and cooperative cleanup decision evidence without claiming forced in-process termination (ref: ADR 0003) → verify: `uv run --offline pytest tests/test_agent_loop.py tests/test_plugins.py tests/test_e2e_scenarios.py -k 'audit or attribution or terminal or failure or cleanup or plugin' && printf 'no new security findings in affected paths\n'`
5. Run all e07 runtime, policy, Plugin, frontend, delegation, and Session regressions plus strict quality checks → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_plugins.py tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py tests/test_delegation.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e07s03-P0-01: Plugin contributions are complete and fail closed

```gherkin
Given an Agent with current bundled Plugin Tools and a complete declared contribution set
When Core builds a runtime
Then contributions are validated, attributed, deterministically ordered, and staged before execution
When a duplicate, undeclared, incompatible, or invalid Tool/effect is present
Then the complete Plugin set is rejected before provider or Tool execution
And no sibling contribution remains partially active
```

### Scenario SC-e07s03-P0-02: Final validation follows transformation

```gherkin
Given Plugin middleware transforms Tool arguments
When the Tool call reaches the executor
Then Core validates the final Tool identity, arguments, effect, capability, approval, security, and attribution
And approval describes the final arguments
When final validation rejects the call
Then the executor is not called and the rejection cannot be swallowed
```

### Scenario SC-e07s03-P0-03: Plugin cannot forge terminal truth

```gherkin
Given a Plugin Tool, observer, or disposer fails, duplicates execution, or attempts to emit a success
When Core processes the Run
Then the failure is sanitized and attributed
And mandatory audit and terminal normalization remain Core-owned
And completed domain-work truth is not rewritten by Plugin lifecycle health
And cooperative cleanup reaches a completion-or-timeout decision
```

### Scenario SC-e07s03-P1-04: Plugin-free compatibility remains intact

```gherkin
Given a Plugin-free Agent invokes a built-in Tool
When Core executes and renders the Run
Then existing Tool policy, event discriminators, attribution defaults, CLI, REPL, TUI, and Session behavior remain valid
And no Plugin runtime requirement is introduced
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_plugins.py tests/test_agent_runtime.py -k 'plugin or activation or duplicate or attribution'`.
2. Run `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'transform or rewrite or final or approval or security'`.
3. Run `uv run --offline pytest tests/test_agent_loop.py tests/test_e2e_scenarios.py -k 'audit or terminal or failure or cleanup'`.
4. Run `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py`.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Confirm diagnostic and event payloads contain no Plugin configuration secrets, credentials, or unsanitized exceptions.

## 19. Risks and Mitigations

- **Approval mismatch:** transformed arguments differ from reviewed arguments. Mitigation: final Core validation and approval immediately before execution.
- **Partial Plugin activation:** one invalid contribution leaves sibling Tools visible. Mitigation: complete-set staging and fail-closed rejection.
- **Forged success:** Plugin swallows rejection or emits a success without execution. Mitigation: terminal and Tool result normalization outside Plugin hooks.
- **Duplicate execution:** middleware calls the executor more than once. Mitigation: one Core-owned execution guard and regression test.
- **Cleanup overclaim:** same-process trusted code blocks the event loop. Mitigation: conditional cooperative deadline language and process-restart recovery requirement.
- **Compatibility break:** added attribution or validation changes Plugin-free payloads. Mitigation: additive defaults and full frontend regression suite.

## 20. Definition of Done and Slopcheck

- All four scenarios pass through public runtime, Tool, Plugin, and frontend interfaces.
- Every Plugin Tool call is complete-set validated, attributed, and finally Core-checked after transformation.
- Core policy, security, audit, and terminal truth cannot be bypassed or forged by supported Plugin behavior.
- Cleanup decisions are honest about cooperative yielding and process authority.
- Notes and Plugin-free behavior remain compatible.
- Tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Python standard library — deterministic collections, async cancellation, and bounded validation.
- `[OK]` Pydantic (already installed) — Tool context, event, effect, and configuration boundaries.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic middleware and lifecycle tests.
- No new package, generic event bus, service graph, loader, or sandbox is proposed.

### Red-Flag Check

Rejected trusting transformed arguments, partial Plugin activation, Plugin-owned terminal events, Plugin-controlled middleware order, a second extension host in e07, forced same-process cleanup claims, and any Plugin-free compatibility break.
