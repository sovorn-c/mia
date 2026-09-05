# e08s03 — Core Boundary, Notes Migration, and Compatibility

## 1. Identity

- **Story ID:** e08s03
- **Epic:** e08 — Governed Core Extension Host
- **Type:** feat
- **Risk:** P0
- **Context:** AgentRuntimeFactory, AgentRunner, ToolPipeline, access/security/audit, Notes migration, CLI, and package surface
- **BCPs:** 6
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user and Plugin author, I want the governed host to run through the same Core execution path as existing Tools so that Plugin behavior remains attributable and additive while policy, identity, Session integrity, terminal truth, Notes behavior, and Plugin-free compatibility remain protected.

## 3. Context

`AgentRuntimeFactory` currently merges bundled Plugin Tools into the built-in Tool set and constructs mandatory access, security, audit, and cost middleware (`src/mia_agent/runtime_factory.py:146-286`). `ToolPipeline` supports ordered middleware transformations, and `FinalCoreToolValidator` is the e07 boundary for final policy checks (`src/mia_middleware/pipeline.py`, `src/mia_middleware/access.py`). Notes is the existing compatibility proof with Agent-owned data (`src/mia_agent/plugin_catalog.py`, `src/mia_tools/notes.py`). e08s01 and e08s02 provide typed trust/catalog and transactional activation; this story wires them into the canonical runtime and closes the final constitutional boundary.

## 4. Problem

A Plugin host can still be unsafe if its contributions bypass the final Core validator, if transformed arguments differ from approved arguments, or if observers can suppress/forge events. Migrating Notes without explicit compatibility checks could change Tool effects, data paths, Template behavior, or Plugin-free Agents. A public API that accidentally exports runtime internals would also make the constitutional boundary unenforceable.

## 5. Goal

Integrate the host with `AgentRuntimeFactory → AgentHarness → ToolPipeline → AgentRunner` so every Plugin Tool transformation receives final Core validation and approval, every event/audit/diagnostic remains Core-attributed, Notes migrates without behavioral or storage changes, and clean package/public surfaces expose only the supported extension contract.

## 6. Non-Goals

- New Plugin discovery or activation primitives beyond e08s01/e08s02.
- Generic services/events, Core/provider/credential/Session replacement, Tool overrides, commands/UI, hot reload, background work, remote catalogs, automatic installation, or process sandboxing.
- Rewriting existing Session history or automatic migration/deletion of user data.

## 7. Stakeholders

- Users of Notes, Plugin-free Agents, CLI, REPL, and TUI.
- Plugin authors relying on declared Tool/context/observer/middleware contracts.
- Core policy, security, audit, runtime, and packaging maintainers.
- Operators reviewing attribution, diagnostics, trust, and terminal outcomes.

## 8. Dependencies

- e08s01 typed Plugin contract, trust, provenance, and static catalog.
- e08s02 transactional Run activation, immutable snapshot, owned lifecycle, and cleanup decision.
- e07 final Core Tool validation, canonical closeable Run, permanent middleware, and terminal truth.
- Existing Notes Plugin tests, Agent Template tests, runtime/factory tests, and package surface scripts.
- `specs/tech-architecture/e08-TEST_PLAN_LATEST.md` scenarios SC-e08s03-P0-01 through SC-e08s03-P1-04.
- ADR 0003; no new runtime dependency.

## 9. Assumptions

- All visible Tools, including Plugin Tools, execute through the same Core policy and middleware pipeline.
- Plugin middleware may transform only the allowed mutable Tool context; final Core validation treats transformed arguments as the operation to approve and execute.
- Plugin observers are notification-only and receive immutable sanitized values; observer failure is a diagnostic, not a terminal outcome.
- Notes keeps Plugin ID `notes`, Tool names/effects, `notes-agent` Template, configuration, Agent-owned storage, and stored format.
- Trusted Python remains unsandboxed and may act outside the supported API; Mia makes no process-isolation claim.

## 10. Constraints

- Final validation occurs after every supported Plugin Tool transformation and before executor invocation.
- Final Core validation, access, security, audit, execution limits, sanitation, attribution, Session ownership, cancellation, and terminal truth cannot be disabled, reordered, swallowed, or replaced by Plugin behavior.
- Approval describes final normalized arguments and the executor runs at most once.
- Plugin observers cannot emit, suppress, replace, or reorder Core events or terminal envelopes.
- Plugin configuration, event payloads, diagnostics, and package metadata remain secret-free.
- Plugin-free Agents receive no activation requirement and retain existing behavior.

## 11. Domain Model

- **Core execution sandwich:** attribution/audit and limits around Plugin middleware, final Core validation before execution, then Core result sanitation and completion audit.
- **Final Core validator:** last policy/security/effect/capability/schema/approval check before a Tool executor.
- **Plugin attribution:** Core-assigned Plugin ID on Tools, events, audits, and diagnostics.
- **Notes compatibility migration:** host-backed Notes implementation preserving its public and persisted contracts.
- **Plugin-free compatibility:** an Agent with no enabled Plugin follows the same built-in runtime behavior without host dependency.

## 12. Requirements

### MODIFIED: Plugin Tool execution boundary

**Before:** Bundled Plugin Tools are composed into `AgentRuntimeFactory` and pass through current middleware, while the final post-transformation Core validation and broader host attribution are only partially explicit.

**After:** Every host-backed Tool and optional middleware executes inside the permanent Core sandwich. Final identity, arguments, effect, capability, access, security, approval, size, and attribution validation occurs after transformation and before one executor call; Core owns result sanitation, audit, terminal normalization, and lifecycle diagnostics.

### ADDED: Non-forgeable Core invariants

Through the supported host API, Plugins MUST NOT access credentials, providers, mutable Agent/runtime objects, Sessions, approval callbacks, Tool registries, middleware lists, or terminal state. They MUST NOT replace identity, Session ownership, admission, permanent safeguards, event attribution, cancellation ownership, or terminal outcomes; they MUST NOT swallow Core rejection, execute a Tool more than once, or fabricate success.

### ADDED: Notes and Plugin-free migration compatibility

The host-backed Notes Plugin MUST preserve Plugin ID, Tool names and effects, Template ID and defaults, configuration validation, Agent-owned data location and format, attribution, disablement data retention, and existing CLI/API behavior. A Plugin-free Agent MUST retain existing Tool, event, Session, and frontend behavior without requiring a Plugin activation.

### ADDED: Public contract inspection

The package and public exports MUST expose the supported Plugin API/version and inspection surfaces without exposing mutable Core internals. Clean-install and wheel checks MUST verify supported modules, entry-point metadata, Notes registration, and absence of undeclared/retired extension surfaces.

## 13. Non-Functional Requirements

- **Security:** final policy cannot be bypassed; no identity, credential, approval, effect, or secret spoofing.
- **Determinism:** final arguments, approval, execution count, event order, and attribution are stable.
- **Compatibility:** Notes, Plugin-free Agent, CLI, REPL, TUI, Session, and serialized event behavior remain valid.
- **Auditability:** attempted Tools, final arguments, Plugin lifecycle failures, and terminal outcomes are attributed and sanitized.
- **Packaging:** clean offline builds contain the supported API and preserve `py.typed`/public package expectations.

## 14. Contracts

### Existing contracts preserved

- `AgentRunner → AgentRuntimeFactory → AgentHarness` is the sole prompt execution path.
- `ToolPipeline` remains an asynchronous onion/waterfall pipeline with mandatory Core middleware.
- `FinalCoreToolValidator`, access policy, security guard, audit, cost controls, event envelopes, Session append-only storage, and terminal finalization remain Core-owned.
- Notes Tool behavior, storage, Template, and CLI/API contracts remain compatible.

### New contracts

- Plugin middleware transformations are final-validated and approved immediately before exactly one execution.
- Plugin observers are immutable notification-only callbacks with attributed diagnostic failure handling.
- Public Plugin API/version and wheel surfaces are explicit and bounded.
- Plugin-free behavior does not depend on discovery, trust, or activation of any Plugin.

## 15. Reason for Depth and Zoom-Out

- **Final Core gate integration:** required because pre-transformation validation cannot prove that the executed operation is the approved operation.
- **Core-owned observer/terminal boundary:** required because a Plugin must not be able to turn an observer or cleanup failure into false Run success/failure.
- **Notes migration tests:** required because Notes is the only existing Plugin with persisted Agent-owned data and therefore catches compatibility regressions that synthetic Plugins cannot.

`ToolPipeline` purpose: execute one Tool through ordered middleware and one Core executor. Callers: `AgentHarness`, access/policy tests, middleware tests, Plugin tests, and end-to-end scenarios (`src/mia_middleware/pipeline.py:28`, `src/mia_agent/harness.py`). Contracts: asynchronous onion order, one executor path, controlled argument transforms, mandatory middleware, and failure propagation. `AgentRuntimeFactory` purpose and callers are defined in e08s02; this story adds the final host integration and verifies existing callers without moving policy into Adapters.

## 16. Implementation Steps

1. Add failing tests for transformed-argument final validation, approval/executor agreement, rejected-call non-execution, observer non-forgery, identity/Session protection, and Plugin-free behavior (ref: `specs/tech-architecture/e08-TEST_PLAN_LATEST.md`, SC-e08s03-P0-01/P0-02) → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_agent_runtime.py -k 'final or transform or approval or reject or attribution or terminal'`
2. Wire activated Plugin Tools, bounded context, observers, and optional middleware through `AgentRuntimeFactory` and `ToolPipeline` while retaining mandatory final Core validation and one executor path → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py tests/test_agent_runtime.py -k 'runtime or pipeline or middleware or context or observer or tool'`
3. Preserve Core-owned event/audit/diagnostic attribution, cancellation, terminal normalization, and Session ownership when Plugin callbacks fail, duplicate execution, or attempt to forge success → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_e2e_scenarios.py -k 'audit or diagnostic or cancellation or terminal or session or forged or duplicate' && printf 'no new security findings in affected paths\n'`
4. Migrate bundled Notes to the host-backed contract without changing its ID, Tools/effects, Template, configuration, Agent-owned storage, or stored format; verify Plugin-free and frontend compatibility → verify: `uv run --offline pytest tests/test_notes_plugin.py tests/test_plugins.py tests/test_agent_templates.py tests/test_agent_runtime.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py -k 'notes or plugin_free or compatibility or template'`
5. Expose and verify the bounded public Plugin API/version and clean wheel surface, then run the complete e08 and repository quality checks → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py tests/test_notes_plugin.py tests/test_agent_templates.py tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv build --offline && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e08s03-P0-01: Final Core validation follows Plugin transformation

```gherkin
Given a declared Plugin middleware transforms a Tool's arguments
When the Tool call reaches execution
Then Core validates the final identity, arguments, effect, capability, access, approval, security, size, and attribution
And approval describes the final normalized arguments
And the executor is called at most once
When final validation rejects the call
Then the executor is not called and the rejection cannot be swallowed
```

### Scenario SC-e08s03-P0-02: Supported Plugin API cannot forge Core truth

```gherkin
Given a Plugin attempts to access a credential, mutate an Agent or Session, suppress an event, duplicate execution, or emit success
When Core runs the Plugin through the supported host
Then the forbidden operation is rejected or unavailable
And all Tool/event/audit/diagnostic attribution remains Core-assigned
And cancellation, admission, finalization, and terminal normalization remain Core-owned
```

### Scenario SC-e08s03-P0-03: Notes migration and Plugin-free compatibility hold

```gherkin
Given an existing Notes-enabled Agent and a Plugin-free Agent
When both execute through the host-backed runtime
Then Notes retains its Plugin ID, Tool names/effects, Template, configuration, Agent-owned data path, and stored format
And the Plugin-free Agent retains existing built-in Tool, event, Session, and frontend behavior
And disabling Notes retains its configuration and data without requiring activation
```

### Scenario SC-e08s03-P1-04: Public and package surfaces are bounded

```gherkin
Given a clean offline wheel installation
When an operator inspects the Plugin API/version, catalog, entry-point metadata, and package contents
Then only the supported typed host and inspection surfaces are present
And no mutable Core internals, retired extension surface, credential-bearing metadata, or undeclared package is exposed
```

## 18. Verification Script (Step-by-Step)

1. Register a test middleware that changes a Tool argument and inspect the approval request and executor call.
2. Attempt to bypass policy, change identity, invoke twice, suppress audit, or fabricate a result; verify each operation fails closed and produces no false success.
3. Run successful, failed, cancelled, and observer-failure Runs and inspect Core-owned terminal truth and sanitized diagnostics.
4. Execute Notes before and after host migration and compare Tool names/effects, Template defaults, storage path, file format, and disablement retention.
5. Execute a Plugin-free Agent through CLI/REPL/TUI/runtime tests and confirm no Plugin activation is required.
6. Build and inspect the wheel and public API/version surface in an isolated environment.

## 19. Risks and Mitigations

- **Approval/execution mismatch:** final validation and approval occur after transformation immediately before one executor call.
- **Forgeable terminal outcome:** keep observers and lifecycle diagnostics outside terminal normalization and finalization.
- **Notes data loss:** preserve paths/format and compare migration behavior in isolated Agent homes; never rewrite user files automatically.
- **Plugin-free regression:** maintain a no-Plugin runtime test path and frontend regression suite.
- **Public authority leak:** export only immutable typed contracts and inspection values; test forbidden attributes and package contents.
- **Trusted-code overclaim:** document process authority and event-loop-blocking limits; do not claim sandboxing or forced termination.

## 20. Definition of Done and Slopcheck

- All four scenarios pass through public runtime, middleware, Notes, frontend, and packaging interfaces.
- Final Core validation cannot be bypassed or reordered through supported Plugin behavior.
- Notes and Plugin-free behavior remain compatible with no data rewrite or secret exposure.
- Public API/version and wheel surfaces are bounded and verified.
- Tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Existing Python standard library, Pydantic, pytest, and packaging tools — no new runtime dependency.
- `[OK]` Existing Core middleware and AgentRunner — reuse the established final validator and canonical execution root.
- No generic service graph, replacement Core, remote installer, event bus, or process sandbox is proposed.

### Red-Flag Check

Rejected pre-only validation, Plugin-owned approval or terminal truth, mutable Session/Agent access, duplicate execution, automatic Notes migration, Plugin-free activation requirements, public runtime internals, and same-process sandbox claims.
