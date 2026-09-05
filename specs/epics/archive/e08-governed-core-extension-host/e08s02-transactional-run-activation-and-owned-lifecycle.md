# e08s02 — Transactional Run Activation and Owned Plugin Lifecycle

## 1. Identity

- **Story ID:** e08s02
- **Epic:** e08 — Governed Core Extension Host
- **Type:** feat
- **Risk:** P0
- **Context:** PluginHost, AgentRuntimeFactory, Run-scoped contributions, dependency planning, rollback, disposal, and quarantine
- **BCPs:** 8
- **Status:** passing
- **Requirement delta:** ADDED

## 2. User Story

As a Mia Core maintainer, I want enabled Plugins to activate transactionally into one immutable Run snapshot so that declared extensions are deterministic, reversible, and unable to leave partial capabilities or unowned cleanup behind.

## 3. Context

The current `PluginManager.resolve_tools()` builds bundled Notes Tools and `AgentRuntimeFactory.build()` collects Tool disposers, but there is no general activation plan, dependency graph, registration context, staged publication, rollback, or owned effect lifecycle (`src/mia_agent/plugins.py:238-287`, `src/mia_agent/runtime_factory.py:146-286`). ADR 0003 selects a narrow `PluginContext` with `register`, `observe`, and `effect`, dependency-ready activation, immutable Run-scoped contributions, and Core-owned cleanup.

## 4. Problem

Activating enabled Plugins one at a time can expose sibling contributions before the complete set is validated. A failed callback or disposer can leak effects, produce nondeterministic order, or leave an active Plugin usable after cleanup timeout. A mutable shared registration surface could also let one Run affect another Run or bypass Core ownership.

## 5. Goal

Implement the narrow typed runtime host behind `AgentRuntimeFactory`: plan the complete enabled set without callbacks, validate exact dependencies and declarations, activate deterministically, publish staged contributions atomically, roll back partial work in reverse order, freeze one Run-scoped activation, and give `AgentRunner` an idempotent cooperative disposal/quarantine decision.

## 6. Non-Goals

- New Plugin Tool policy validation after middleware transformation, Notes compatibility migration, or package/public surface release gates; those belong to e08s03.
- Generic services/dependency injection, child Plugin mounting, arbitrary event buses, Core/provider replacement, commands/UI, hot reload, background work, remote catalogs, automatic installation, or OS/process sandbox guarantees.
- Stopping arbitrary event-loop-blocking same-process Python; only cooperative cleanup decisions are bounded.

## 7. Stakeholders

- `AgentRuntimeFactory` and `AgentRunner` maintainers.
- Trusted Plugin authors implementing async activation/disposal.
- Operators relying on deterministic Run behavior and truthful cleanup diagnostics.
- Security and reliability maintainers protecting Core-owned identity, Sessions, and outcomes.

## 8. Dependencies

- e08s01 strict Plugin models, trust, provenance, and static catalog.
- e07 canonical closeable Run, Session admission, terminal truth, and cleanup linearization.
- Existing `AgentRuntimeFactory`, `PluginManager`, `AgentRuntime`, `AgentRunner`, `PluginDiagnosticEvent`, and `ToolPipeline`.
- `specs/tech-architecture/e08-TEST_PLAN_LATEST.md` scenarios SC-e08s02-P0-01 through SC-e08s02-P0-04.
- ADR 0003 and the selected Option A registration-context design.

## 9. Assumptions

- Planning validates the complete enabled Plugin set and runs no activation callback.
- Exact dependencies must be installed, compatible, trusted, and explicitly enabled; Core never enables dependencies implicitly.
- Independent Plugins are ordered by normalized Plugin ID after dependency ordering.
- Plugin callbacks and disposers are asynchronous and cancellation-cooperative; event-loop-blocking code can prevent Core from regaining control.
- A successful activation is immutable for one Run; Agent/Plugin changes apply only to later Runs.
- Plugin data survives disablement, failed activation, disposal, and quarantine.

## 10. Constraints

- `PluginContext` exposes only Plugin ID, Agent ID, secret-free config, Core-selected data directory, `register`, `observe`, and `effect`.
- Contributions are limited to declared Tools, bounded additive context contributors, notification-only Run observers, and optional Tool middleware.
- Registrations remain staged until all enabled Plugins activate and declaration/collision validation succeeds.
- Failure rolls back every acquired effect in reverse order and exposes no partial runtime contribution.
- Disposal is idempotent, attributed, reverse ordered, cooperative, and reaches `DISPOSED` or `ABANDONED` before terminal delivery when Core regains control.
- `ABANDONED` quarantines the Plugin until process restart and diagnoses the condition; Mia makes no hard guarantee against code that blocks the event loop.

## 11. Domain Model

- **Plugin Host:** Core-owned planner and activator behind `AgentRuntimeFactory`.
- **Plugin Context:** narrow per-activation author API with three operations: register, observe, effect.
- **Activation Plan:** complete validated enabled Plugin set and deterministic dependency order.
- **Plugin Activation:** immutable Run-scoped published contributions and owned disposers.
- **Owned Effect:** synchronous or asynchronous reversible resource whose disposer belongs to one activation.
- **Cleanup Decision:** Core result `DISPOSED` or `ABANDONED`, with diagnostics and quarantine when appropriate.

## 12. Requirements

### ADDED: Complete-set deterministic activation

Core MUST plan and validate the complete enabled Plugin set before callback execution, including installation, API compatibility, trust, provenance, enablement, configuration, exact dependencies, declarations, IDs, collisions, and quarantine state. Activation order MUST be dependency-first with normalized Plugin ID as a stable tie-breaker.

### ADDED: Narrow typed registration context

Trusted-code Plugins MAY use only `register`, `observe`, and `effect`. `register` accepts declared Tools, bounded additive context contributors, notification-only Run observers, or optional Tool middleware. `observe` accepts only approved immutable sanitized Run phases and cannot replace, suppress, or emit events. `effect` records a Core-owned disposer. The context MUST NOT expose credentials, providers, mutable Agents/runtimes, Sessions, approval callbacks, registries, or middleware lists.

### ADDED: Transactional staging and rollback

Runtime contributions MUST remain staged until the complete enabled set activates and validates. Any planning, declaration, collision, callback, or activation failure MUST publish nothing and MUST request reverse-order disposal for every acquired effect, including the failing Plugin. A successful activation MUST be immutable and isolated to one Run.

### ADDED: Owned cooperative lifecycle

AgentRunner MUST own idempotent reverse-order disposal for each activation. While callbacks yield control, Core applies its cleanup deadline and reaches a completion-or-timeout decision before terminal delivery. Timeout or disposal failure creates an attributed sanitized diagnostic; timeout marks the Plugin `ABANDONED`, quarantines it until process restart, and does not rewrite completed domain-work truth.

## 13. Non-Functional Requirements

- **Determinism:** dependency order, registration publication, collision errors, rollback, and disposal order are stable.
- **Security:** Plugin context cannot access credentials, identity owners, Sessions, approval, permanent safeguards, or terminal outcomes.
- **Atomicity:** no partial Plugin contribution is visible after any activation failure.
- **Resilience:** cleanup failure is diagnosed and isolated without corrupting Sessions or changing a completed Run outcome.
- **Async correctness:** cooperative callbacks are cancellable and bounded when they yield; blocking same-process code is documented honestly.

## 14. Contracts

### Existing contracts preserved

- `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only prompt path.
- Existing Agent-owned Session admission, immutable runtime settings, ToolPipeline ordering, Notes data paths, and Plugin-free behavior remain intact.
- Existing `AgentRuntime.disposers` and `PluginDiagnosticEvent` semantics remain compatible while becoming activation-owned.

### New contracts

- One complete activation plan is the only source of visible runtime Plugin contributions for a Run.
- Plugin context operations are narrow, typed, declaration-checked, and attributed to one activation.
- Activation publication is atomic; failed activation exposes no sibling contribution.
- Cleanup is Core-owned, reverse ordered, idempotent, deadline-aware, and quarantine-aware.

## 15. Reason for Depth and Zoom-Out

- **PluginHost:** required to centralize complete-set planning, dependency order, staging, rollback, and lifecycle ownership; a generic service container would add unapproved authority and compatibility burden.
- **PluginContext:** required to give authors an ergonomic extension seam while hiding mutable Core internals and preserving constitutional invariants.
- **Activation snapshot:** required because Agent/Plugin configuration changes must not mutate an active Run or make two Runs share disposers.

`AgentRuntimeFactory` purpose: compose one Agent's provider, Tools, middleware, Session, effective settings, and runtime lifecycle while preserving Core safeguards. Callers: `AgentRunner`, `DelegationService`, CLI/TUI adapters, runtime tests, and factory tests. Contracts: one execution root, mandatory middleware, immutable runtime identity, Agent-owned Session paths, and collected cleanup disposers (`src/mia_agent/runtime_factory.py:50`, `src/mia_agent/delegation.py`). This story inserts the governed host into that existing composition seam; final post-transformation policy validation remains e08s03.

## 16. Implementation Steps

1. Add failing public-interface tests for complete-set planning, exact dependency validation, deterministic order, staged publication, immutable snapshots, rollback, and Plugin-free compatibility (ref: `specs/tech-architecture/e08-TEST_PLAN_LATEST.md`, SC-e08s02-P0-01/P0-03) → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_agent_runtime.py -k 'plan or dependency or order or staged or snapshot'`
2. Implement the narrow typed `PluginContext`, contribution union, owned effect scope, notification-only observers, and declaration/collision validation without exposing mutable Core objects → verify: `uv run --offline pytest tests/test_plugin_host.py -k 'context or register or observe or effect or declaration or collision'`
3. Add complete-set dependency planning, deterministic activation, staged publication, and reverse-order rollback behind `AgentRuntimeFactory` → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py tests/test_agent_runtime.py -k 'activation or dependency or deterministic or rollback or staged'`
4. Connect immutable Run activation disposal to AgentRunner cleanup, including idempotent cooperative completion/timeout decisions, attributed diagnostics, and process-restart quarantine semantics → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_agent_runtime.py -k 'dispose or cleanup or timeout or quarantine or diagnostic' && printf 'no new security findings in affected paths\n'`
5. Run the complete host, runtime, Session, cancellation, and Plugin regression suite with formatting, lint, and strict typing → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_sessions.py tests/test_delegation.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`

## 17. Acceptance Criteria

### Scenario SC-e08s02-P0-01: Complete Plugin set activates deterministically

```gherkin
Given an Agent with multiple trusted enabled Plugins and exact installed dependencies
When Core plans and activates one Run
Then all dependencies are validated before callbacks
And Plugins activate in dependency order with stable ID tie-breaking
And no callback runs during planning
And the published contribution set is complete and attributed
```

### Scenario SC-e08s02-P0-02: Activation is atomic and reversible

```gherkin
Given a Plugin activation acquires an effect and a later Plugin fails validation or activation
When Core processes the failure
Then no staged Tool, context, observer, or middleware contribution becomes visible
And all acquired effects are disposed in reverse order
And the failure is sanitized and attributed
```

### Scenario SC-e08s02-P0-03: Each Run receives an immutable activation snapshot

```gherkin
Given an enabled Agent starts two eligible Runs or changes Plugin configuration after one Run starts
When each Run constructs its runtime
Then each Run has its own immutable contribution and effect snapshot
And later Agent/Plugin changes affect only later Runs
And a Plugin cannot access mutable Agent, Session, provider, or runtime internals
```

### Scenario SC-e08s02-P0-04: Cleanup reaches an honest Core decision

```gherkin
Given a Run finishes or is cancelled with cooperative Plugin observers or disposers
When Core performs cleanup
Then disposal is reverse ordered and idempotent before terminal delivery when callbacks yield
When disposal fails or exceeds the cooperative deadline
Then Core emits an attributed sanitized diagnostic
And timeout quarantines the Plugin until process restart
And completed domain-work truth remains unchanged
And Mia makes no claim to stop event-loop-blocking same-process code
```

## 18. Verification Script (Step-by-Step)

1. Define two synthetic trusted Plugins with a dependency and record callback/effect order.
2. Plan the complete enabled set and assert no callback executes during planning.
3. Activate a Run and verify deterministic dependency order, staged publication, attribution, and immutable contribution objects.
4. Inject a later activation failure and verify reverse-order rollback with no published sibling contributions.
5. Complete and cancel Runs with successful, failing, and cooperative-timeout disposers; verify diagnostics, quarantine, idempotence, and preserved terminal truth.
6. Run Plugin-free and existing Notes/runtime regression checks.

## 19. Risks and Mitigations

- **Partial publication:** stage all registrations and publish only after complete validation.
- **Dependency cycle or hidden enablement:** require exact installed/trusted/enabled dependencies and reject cycles/missing dependencies.
- **Context authority leak:** expose immutable values and narrow methods only; add forbidden-object tests.
- **Cleanup deadlock:** apply cooperative deadlines and quarantine after Core regains control; document event-loop-blocking limits.
- **Cross-Run mutation:** create a per-Run activation snapshot and owned effect scope; test configuration changes after activation.
- **Rollback omission:** register every acquired disposer immediately and test failure at each activation position.

## 20. Definition of Done and Slopcheck

- All four P0 scenarios pass through the public host/runtime interfaces.
- Activation is complete-set, deterministic, staged, immutable, reversible, and Core-attributed.
- Cleanup is reverse ordered, idempotent, cooperative, diagnostically honest, and quarantine-aware.
- No generic service graph, second execution root, or sandbox claim is introduced.
- Tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Python standard library — async cancellation, deterministic ordering, entry-point metadata, and immutable mappings.
- `[OK]` Pydantic (already installed) — typed contribution, context, activation, and diagnostic boundaries.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic activation and lifecycle tests.
- No new runtime dependency, generic service container, or process manager is proposed.

### Red-Flag Check

Rejected partial publication, implicit dependency enablement, mutable runtime exposure, Plugin-owned terminal truth, unbounded cleanup promises, event-loop-blocking termination claims, generic services/events, and a second execution root.
