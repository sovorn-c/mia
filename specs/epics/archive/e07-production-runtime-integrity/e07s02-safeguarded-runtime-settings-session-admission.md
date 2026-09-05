# e07s02 — Safeguarded Runtime Settings and Session Admission

## 1. Identity

- **Story ID:** e07s02
- **Epic:** e07 — Production Runtime Integrity
- **Type:** hardening
- **Risk:** P0
- **Context:** Agent configuration, provider resolution, middleware, Session persistence, delegation, and tests
- **BCPs:** 7
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As an Agent owner, I want effective settings and Session ownership resolved by Core so that configured limits and access policy cannot be silently ignored or concurrently corrupt one Agent-owned history.

## 3. Context

`AgentRuntimeFactory.build()` currently resolves Agent and global settings, constructs providers, filters Tools, wires configured middleware, and opens a Session store (`src/mia_agent/runtime_factory.py:44-172`). The factory accepts overrides and the Agent model carries policy, tools, context, compaction, and execution limits. There is no explicit admission guard preventing two foreground Runs from owning one `(agent_id, session_id)` simultaneously. Existing access, security, audit, and cost middleware are individually tested but their permanent Core ownership must be made non-optional in the canonical path.

## 4. Problem

A request or Agent setting can be ignored when precedence is implicit, invalid effective settings can reach provider construction, and concurrent Runs can append nondeterministically to one Session. Allowing Agent middleware lists or capability overrides to remove Core safeguards creates a path around approval, audit, security, or execution limits.

## 5. Goal

Make runtime configuration deterministic and fail closed: validate effective provider/model/context/compaction/execution settings, admit at most one Run per Agent-owned Session, preserve distinct-Session concurrency, and always apply permanent safeguards without escalating access.

## 6. Non-Goals

- Scheduler, queue, background Run manager, or cross-process distributed lock.
- New providers, provider registry, or model discovery.
- A public lifecycle handle or second runtime root.
- Remote Session storage or automatic repair of corrupt user files.
- Governed installed-code Plugin activation (e08), except preserving existing Plugin-free and bundled Plugin behavior.

## 7. Stakeholders

- Agent owners and operators of interactive Runs.
- Runtime, provider, middleware, and Session maintainers.
- Delegation callers sharing the canonical factory.
- CLI, REPL, TUI, and deterministic test authors.

## 8. Dependencies

- e07s01 canonical `RunRequest` and finalizer.
- `Agent`, `AgentManager`, `ConfigManager`, `AgentRuntimeFactory`, `AgentHarness`, and Session storage.
- Access, security, audit, cost, and execution-limit middleware contracts.
- e04 access/credential/Session invariants and e06 clean-break runtime path.
- `specs/tech-architecture/e07-TEST_PLAN_LATEST.md` scenarios SC-e07s02-P0-01 through P1-04.

## 9. Assumptions

- Precedence is request override, then persisted Agent setting, then global config, then safe built-in default where the setting is allowed to be overridden.
- A request may narrow capabilities or limits but cannot broaden Agent policy or remove a permanent safeguard.
- Same-Session admission is process-local and released on every terminal, cancellation, closure, and handled construction failure.
- Different Agent-owned Sessions may run concurrently.
- Provider credentials remain resolved from `ConfigManager` and never enter Agent, Session, event, or diagnostic data.

## 10. Constraints

- All effective settings are validated before provider execution or Session mutation beyond sanitized identity metadata.
- Access policy remains `read-only`, `approval-required`, or explicitly confirmed `full-access`.
- Delegation can restrict but never increase caller capability or bypass admission.
- Core always owns security, audit, supported execution limits, output sanitation, and terminal truth middleware.
- Admission failure is a finalized `session_busy` Run error and never a success or partial provider turn.
- Session history remains append-only; no lock path rewrites or deletes entries.

## 11. Domain Model

- **Effective settings:** validated provider model, context window, compaction threshold, max steps, access policy, and capability set for one Run.
- **Session admission:** process-local ownership token keyed by `(agent_id, session_id)`.
- **Permanent safeguards:** Core-owned access, security, audit, cost, execution-limit, sanitation, and terminal controls.
- **Capability intersection:** the effective Tool set after Agent policy, request narrowing, and Delegation restriction.

## 12. Requirements

### MODIFIED: Effective settings precedence

**Before:** `AgentRuntimeFactory.build()` uses a mixture of request overrides, Agent values, and global configuration, while access/capability overrides can be supplied independently and validation is distributed across constructors (`src/mia_agent/runtime_factory.py:44-172`).

**After:** Core computes and validates one effective settings snapshot with documented precedence before provider execution. Invalid or unsafe values fail with sanitized errors; request/delegation overrides may narrow capability or limits but cannot broaden policy or remove safeguards.

### ADDED: One active Run per Agent-owned Session

Core MUST admit at most one supported Run for each `(agent_id, session_id)` in the process. A conflicting Run MUST fail fast with a finalized `session_busy` error and MUST NOT execute provider/Tool code or append indeterminate Session history. Admission MUST release on all terminal, cancellation, closure, and construction-failure paths.

### MODIFIED: Permanent safeguard composition

**Before:** `AgentRuntimeFactory._build_pipeline()` builds middleware from the Agent's configured names and the available Tool list (`src/mia_agent/runtime_factory.py:199-225`).

**After:** Core constructs mandatory access, security, audit, and supported execution-limit controls in fixed order around the Agent/Plugin Tool set. Agent and request configuration may narrow capability or add supported behavior but cannot remove, replace, or reorder permanent safeguards.

### ADDED: Secret-free effective-setting failures

Provider resolution, invalid configuration, unsupported overrides, Session admission, and policy failures MUST use bounded sanitized error codes/messages. Credentials, authorization headers, sensitive Tool arguments, and filesystem secrets MUST not appear in events, Session entries, diagnostics, or logs.

### MODIFIED: Delegation boundary

**Before:** Delegated runtime construction uses the factory but relies on caller-provided depth/access handling at individual call sites.

**After:** Delegated Runs use the same effective-setting and Session-admission boundary, with capability intersection and bounded depth enforced by Core before child provider/Tool execution.

## 13. Non-Functional Requirements

- **Security:** no policy escalation, credential exposure, middleware bypass, or Session path injection.
- **Determinism:** settings precedence and admission outcomes are stable under concurrent asyncio scheduling.
- **Durability:** admission failures do not mutate valid Session history; existing entries remain append-only.
- **Compatibility:** Plugin-free Tool behavior and existing Agent settings remain valid unless invalid under the documented constraints.
- **Concurrency:** distinct Sessions remain independently runnable without a global serialization bottleneck.

## 14. Contracts

### Existing contracts preserved

- `AgentRuntimeFactory` remains the only runtime composition seam for direct and delegated Runs.
- ConfigManager credential resolution and provider injection remain compatible.
- Access policy, approval callback, full-access confirmation, Tool filtering, and Delegation bounds remain enforced.
- Session path confinement, append-only JSONL entries, and identity metadata remain intact.

### New contracts

- One effective settings snapshot is used by provider, harness, Tool pipeline, compactor, and Session admission for a Run.
- `(agent_id, session_id)` has at most one active supported Run in a process.
- Mandatory Core safeguards are not configurable away; configured middleware only contributes approved optional behavior.
- `session_busy` is a terminal Core error, never a provider or Tool result.

## 15. Reason for Depth and Zoom-Out

- **Effective settings snapshot:** required to prevent precedence drift between provider, harness, middleware, and compactor; no general configuration framework is needed.
- **Admission ownership token:** required to guard append-only Session integrity across all frontends while keeping the current process-local product scope; a distributed lock is out of scope.
- **Fixed Core safeguard composition:** required because Agent configuration is untrusted policy input and cannot own the constitutional controls.

`AgentRuntimeFactory` purpose: compose one Agent-scoped provider, Tool set, middleware pipeline, Session store, and harness. Callers: AgentRunner, DelegationService, CLI construction, and runtime tests (`src/mia_agent/runtime_factory.py:29`, `src/mia_agent/delegation.py:18`). Contracts: provider credential separation, Agent Tool filtering, access policy, middleware ordering, Session append-only paths, Plugin compatibility, and one canonical runtime root.

## 16. Implementation Steps

1. Add failing tests for settings precedence, invalid effective values, capability narrowing, and secret-free configuration errors (ref: `specs/tech-architecture/e07-TEST_PLAN_LATEST.md`, SC-e07s02-P0-01) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agents.py tests/test_credentials.py -k 'settings or override or model or context or compaction or invalid'`
2. Implement one validated effective-settings resolution path in AgentRuntimeFactory and pass the snapshot consistently to provider, harness, compactor, and policy construction (ref: `specs/tech-architecture/tech-stack.md`) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agents.py tests/test_credentials.py -k 'settings or precedence or provider or context or compaction'`
3. Add process-local Session admission keyed by Agent and Session identity, with fail-fast `session_busy` normalization and release on success, failure, cancellation, closure, and construction errors (ref: ADR 0002) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_sessions.py -k 'session_busy or admission or concurrent or release or append'`
4. Make Core access, security, audit, cost, and execution-limit safeguards mandatory and fixed-order while preserving Agent policy narrowing, approval, redaction, and Plugin-free behavior (ref: `src/mia_agent/runtime_factory.py`, `src/mia_middleware/`) → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py -k 'policy or approval or security or audit or budget or limit'`
5. Route Delegation through the same admission and effective-setting boundary, proving capability intersection, depth limits, distinct-Session concurrency, and secret-free failures (ref: e04/e06 contracts) → verify: `uv run --offline pytest tests/test_delegation.py tests/test_agent_runtime.py tests/test_sessions.py -k 'delegat or depth or access or session or failure'`
6. Run the complete story regression, strict quality checks, and affected-path security evidence → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agents.py tests/test_credentials.py tests/test_sessions.py tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py tests/test_delegation.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e07s02-P0-01: Effective settings are deterministic

```gherkin
Given global, Agent, and request settings with a valid narrowing override
When Core constructs a Run
Then one validated effective settings snapshot is used by provider, harness, compactor, and policy
And the documented precedence is applied
When an override is invalid or broadens authority
Then Core rejects it before provider execution with a sanitized error
```

### Scenario SC-e07s02-P0-02: Same-Session admission is exclusive

```gherkin
Given an active Run for Agent alpha and Session S
When a second Run targets alpha and S
Then it fails fast with session_busy
And it does not execute provider or Tool code
And it does not append indeterminate Session history
When the first Run reaches success, failure, cancellation, closure, or construction failure
Then admission is released exactly once
```

### Scenario SC-e07s02-P0-03: Permanent safeguards cannot be removed

```gherkin
Given an Agent configuration that narrows tools or requests full access through the supported consent path
When Core builds and executes a Run
Then access, security, audit, cost, execution-limit, sanitation, and terminal controls remain active in fixed order
And narrowing never becomes escalation
And approval evaluates final permitted Tool arguments
```

### Scenario SC-e07s02-P1-04: Delegation preserves boundaries

```gherkin
Given a caller Agent delegates a bounded Task
When Core constructs the child Run
Then child capability is the intersection of caller and target policy
And depth, identity, Session, and terminal truth remain attributable
And a child cannot execute concurrently against a Session already admitted by another Run
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_agent_runtime.py tests/test_agents.py tests/test_credentials.py -k 'settings or override or provider or context or compaction'`.
2. Run `uv run --offline pytest tests/test_agent_runtime.py tests/test_sessions.py -k 'admission or session_busy or concurrent or release'`.
3. Run `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py`.
4. Run `uv run --offline pytest tests/test_delegation.py`.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Inspect serialized errors and Session entries for absence of credentials and sensitive arguments.

## 19. Risks and Mitigations

- **Admission leak:** an exception path could hold the Session token forever. Mitigation: one Runner-owned finalizer releases in `finally` and test every terminal path.
- **Deadlock or over-serialization:** a global lock could block distinct Sessions. Mitigation: key ownership by `(agent_id, session_id)` and test concurrent distinct Sessions.
- **Policy escalation:** request overrides could broaden tools or access. Mitigation: explicit intersection/narrowing checks before effective snapshot creation.
- **Safeguard removal:** configurable middleware names could omit security/audit. Mitigation: Core inserts mandatory controls and tests hostile configuration.
- **Credential leak:** provider errors may include keys or URLs. Mitigation: existing sanitization at error boundaries plus regression assertions.

## 20. Definition of Done and Slopcheck

- All four scenarios pass deterministically through public runtime/delegation interfaces.
- Effective settings have one documented precedence and no invalid override reaches provider execution.
- Same-Session conflicts fail fast and all exits release admission.
- Permanent controls cannot be disabled or reordered through supported Agent/request APIs.
- Delegation and Plugin-free compatibility regressions pass.
- Tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Python standard library — process-local admission, immutable snapshots, and async coordination.
- `[OK]` Pydantic (already installed) — effective settings and boundary validation.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic concurrency and policy tests.
- No lock service, configuration framework, provider registry, or runtime dependency is proposed.

### Red-Flag Check

Rejected a global Session lock, distributed scheduler, policy override that escalates access, Agent-controlled security middleware, credentials in settings models, and automatic repair of Session data.
