# e09s01 — Attributed Local Diagnostics and Bounded Retention

## 1. Identity

- **Story ID:** e09s01
- **Epic:** e09 — Local Operations and Recovery
- **Type:** feat
- **Risk:** P0
- **Context:** Local diagnostics, Tool audit, Run outcomes, Plugin lifecycle, CLI inspection, and retention
- **BCPs:** 5
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As an operator, I want bounded, attributable, secret-free local diagnostics so that I can understand what a Run, Tool, or Plugin did without reading credentials or relying on a remote service.

## 3. Context

`AuditLogMiddleware` currently keeps `AuditLogRecord` values only in an in-memory list (`src/mia_middleware/telemetry.py:22-35,65-105`). Core already emits attributed `RunErrorEvent` and `PluginDiagnosticEvent` values, but those events are delivered through the Run stream and are not a durable operator-facing record (`src/mia_agent/runtime_events.py:17-48`, `src/mia_agent/agent_runner.py:125-153`). e09 must make these existing signals inspectable locally without creating a second event bus or changing terminal truth.

## 4. Problem

After a process exits, an operator cannot inspect attempted Tool actions or Plugin cleanup failures. A naive logger could persist sensitive Tool arguments, raw Plugin exceptions, mutable runtime objects, or unbounded records; a telemetry write failure could also incorrectly change the outcome of a successful Tool or Run.

## 5. Goal

Add a small Core-owned local diagnostic record and store, wire existing Tool and Run/Plugin lifecycle signals into it, enforce recursive redaction and bounded retention, and expose deterministic read-only CLI inspection with truthful failure reporting.

## 6. Non-Goals

- Remote telemetry, dashboards, exporters, tracing backends, or hosted monitoring.
- A generic event bus or replacement for `AgentEventEnvelope`.
- Persisting credentials, provider objects, mutable Sessions, full Tool results, or unrestricted exception text.
- Changing Tool authorization, Plugin activation, Run finalization, or terminal-envelope semantics.

## 7. Stakeholders

- Operators diagnosing local Agent Runs and Plugin lifecycles.
- Core maintainers of `AuditLogMiddleware`, `AgentRunner`, `PluginHost`, and local persistence.
- Security reviewers protecting credentials and sensitive Tool arguments.
- CLI users inspecting a bounded diagnostic history.

## 8. Dependencies

- e07 terminal Run and permanent safeguard contracts.
- e08 attributed `AuditLogRecord`, `PluginDiagnosticEvent`, Plugin cleanup/quarantine, and immutable event envelopes.
- `JsonlSessionStore` append-only persistence patterns and `sanitize_arguments` (`src/mia_agent/session/jsonl.py`, `src/mia_middleware/access.py`).
- Test scenarios SC-e09s01-P0-01 through SC-e09s01-P1-04 in `specs/tech-architecture/e09-TEST_PLAN_LATEST.md`.
- No new runtime dependency; use the standard library and installed Pydantic.

## 9. Assumptions

- Diagnostic records are local operational evidence, not a complete transcript or audit-compliance system.
- Record ordering is insertion order with a stable timestamp/sequence representation; retention removes only the oldest diagnostic records according to an explicit bound.
- Diagnostic persistence failure is reported to the operator and counted as a diagnostic-health failure, but does not turn a completed Tool side effect or truthful Run outcome into a false failure.
- The default diagnostic location is inside the configured Mia data root and is separate from credential storage.

## 10. Constraints

- Every persisted record is attributable to the available Run, Task, Agent, Session, Tool, and Plugin identifiers.
- Recursive sanitization is applied before persistence, rendering, and error reporting; raw arguments and exception text never cross the diagnostic boundary.
- Store writes are append-only and use file ownership/permissions compatible with existing local persistence.
- Retention is bounded by count and/or bytes using deterministic oldest-first behavior; a failed trim is explicit and does not delete valid Session or Plugin data.
- CLI output is stable, plain-text readable, and supports narrow filters without exposing secrets or arbitrary paths.
- Diagnostics remain outside the canonical Agent execution path's authority model: they observe and report; they cannot authorize, suppress, reorder, or rewrite execution.

## 11. Domain Model

- **Diagnostic Record:** immutable/validated local evidence for one Tool attempt, Run outcome, or Plugin lifecycle transition.
- **Diagnostic Store:** Core-owned append-only local record store with retention and explicit health errors.
- **Diagnostic Source:** bounded category such as `tool`, `run`, or `plugin`.
- **Diagnostic Health:** whether the store accepted, rejected, or could not retain a record; it is distinct from domain-work outcome.
- **Diagnostic Filter:** deterministic source, Agent, Session, Run, Plugin, and time/count selection for inspection.

## 12. Requirements

### ADDED: Attributed local operational records

Core MUST persist bounded records for attempted Tool actions, terminal Run outcomes, and Plugin activation/observer/disposal/timeout/quarantine failures. Each record MUST retain only sanitized, bounded fields and Core-derived attribution. Diagnostic records MUST NOT become an alternate outcome or event stream.

### ADDED: Secret-free diagnostic boundary

Before a record is persisted or displayed, Core MUST recursively redact credential-shaped values, authorization material, sensitive Tool arguments, unsafe paths, and raw exception content using the existing sanitation contract or a stricter compatible form. Diagnostic persistence and CLI inspection MUST never display credential values.

### ADDED: Explicit retention and failure behavior

The Diagnostic Store MUST enforce a documented deterministic retention bound. Append, read, malformed-record, permission, and retention failures MUST return actionable sanitized errors or health information. A diagnostic failure MUST NOT change a successful Tool side effect, a finalized Run outcome, or append-only Session history.

### ADDED: Read-only operator inspection

The supported CLI MUST expose deterministic local diagnostic inspection with bounded output and filters for source and identity. It MUST return a non-zero status for invalid filters or unreadable diagnostic state and a zero status for an empty valid store.

## 13. Non-Functional Requirements

- **Security:** no credentials, sensitive Tool arguments, provider objects, or unsanitized exceptions in records, files, or CLI output.
- **Attribution:** every record identifies its source and the available Core identity fields.
- **Durability:** accepted records survive process exit and remain append-only.
- **Boundedness:** retention limits are enforced without unbounded memory or disk growth.
- **Truthfulness:** diagnostic health is separate from Tool/Run success and failure.
- **Compatibility:** existing middleware callbacks, Run envelopes, Plugin diagnostics, and Plugin-free Agents remain supported.

## 14. Contracts

### Existing contracts preserved

- `AuditLogMiddleware` continues to record Tool attempts and invoke its optional callback.
- `AgentRunner` continues to own Run finalization, cleanup ordering, admission release, and terminal envelopes.
- `PluginDiagnosticEvent` remains sanitized and attributed in the Run stream.
- Sessions remain append-only and diagnostic writes never rewrite them.

### New contracts

- `DiagnosticRecord` and `DiagnosticStore` provide a validated local persistence boundary.
- A Core-owned diagnostic sink receives sanitized Tool, Run, and Plugin lifecycle records without receiving credentials or mutable runtime internals.
- `mia diagnostics` (or the repository's canonical equivalent) lists bounded records in stable order and fails clearly on malformed state or invalid selectors.
- Diagnostic-store failures are observable to operators while the underlying domain operation retains truthful outcome semantics.

## 15. Reason for Depth and Zoom-Out

- **DiagnosticRecord/DiagnosticStore abstraction:** required because persistence, redaction, retention, and health semantics must be shared by Tool, Run, and Plugin sources without duplicating security rules.
- **Core diagnostic sink:** required because `AuditLogMiddleware` and `AgentRunner` have different lifecycle owners; a narrow sink avoids a generic event bus.
- **CLI inspection surface:** required because durable records have no operator value if they cannot be read without opening implementation files.

`src/mia_middleware/telemetry.py` purpose: enforce Tool budgets and produce structured Tool audit records. Callers: `AgentRuntimeFactory` constructs it and `AgentHarness`/`ToolPipeline` invoke it for visible Tool actions; tests cover middleware and Plugin composition. Contracts: sanitized arguments, attribution from `ToolCallContext`, callback compatibility, and no false Tool success/failure. `src/mia_agent/agent_runner.py` purpose: own Run lifecycle truth and Plugin cleanup. Callers: CLI, REPL, TUI, Delegation, and tests use `run`/`prompt`; contracts include exactly-once finalization, cleanup ordering, admission release, and sanitized envelopes. This story adds observation/persistence only and does not move lifecycle authority.

## 16. Implementation Steps

1. Add failing public-interface tests for Tool, Run, and Plugin diagnostic records, recursive redaction, attribution, stable ordering, and persistence-health separation → verify: `uv run --offline pytest tests/test_diagnostics.py tests/test_agent_runtime.py tests/test_plugin_host.py -k 'diagnostic or audit or attribut or secret or outcome'`
2. Implement validated `DiagnosticRecord`, append-only `DiagnosticStore`, recursive sanitation, bounded retention, and explicit store-health errors under the configured local data root → verify: `uv run --offline pytest tests/test_diagnostics.py -k 'record or append or redact or retention or persistence or failure'`
3. Wire sanitized Tool audit callbacks and existing Run/Plugin lifecycle diagnostics to the Core-owned store without changing terminal outcome or cleanup ordering → verify: `uv run --offline pytest tests/test_diagnostics.py tests/test_agent_runtime.py tests/test_plugin_host.py -k 'tool or run or plugin or cleanup or quarantine or outcome'`
4. Add deterministic read-only CLI diagnostic inspection with source and identity filters, bounded output, and truthful exit codes → verify: `uv run --offline pytest tests/test_diagnostics_cli.py -k 'diagnostic or filter or empty or invalid or secret'`
5. Run the full e09s01 verification, public-surface, quality, and security checks with no new security findings in affected paths → verify: `uv run --offline pytest tests/test_diagnostics.py tests/test_diagnostics_cli.py tests/test_agent_runtime.py tests/test_plugin_host.py tests/test_middleware_pipeline.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e09s01-P0-01: Tool attempts are attributed and sanitized

```gherkin
Given a Tool attempt with Run, Agent, Session, Plugin, and sensitive argument metadata
When the Tool succeeds, is rejected, or fails
Then one bounded diagnostic record is persisted with available Core attribution
And credential-shaped values, authorization material, raw sensitive arguments, and unsafe exception text are absent
```

### Scenario SC-e09s01-P0-02: Run and Plugin lifecycle diagnostics preserve truth

```gherkin
Given a Run with a successful domain outcome and a Plugin observer, disposal, timeout, or quarantine failure
When Core finalizes and cleans up the Run
Then the diagnostic record identifies the Plugin lifecycle failure and Run identity
And the successful domain outcome, terminal envelope, Session history, and admission semantics remain unchanged
```

### Scenario SC-e09s01-P0-03: Retention and persistence health are explicit

```gherkin
Given a diagnostic store at its retention boundary or a store that cannot be written or trimmed
When Core records a diagnostic
Then retention is deterministic and oldest-first where possible
And the operator can see sanitized diagnostic health
And no valid Session or Plugin data is deleted or rewritten
And the underlying Tool or Run outcome is not relabeled
```

### Scenario SC-e09s01-P1-04: Operators can inspect bounded diagnostics

```gherkin
Given zero or more valid local diagnostic records
When an operator invokes the diagnostic inspection command with valid or invalid filters
Then valid filters return stable bounded plain output and an empty store succeeds
And invalid filters or unreadable state return a non-zero actionable error
And output contains no credential values or raw exception data
```

## 18. Verification Script (Step-by-Step)

1. Create an isolated Agent home and diagnostic store with synthetic Run, Tool, Plugin, and Session identities.
2. Execute successful, rejected, and failed Tool attempts containing API-key-shaped and authorization-shaped sentinel values.
3. Trigger a Plugin observer/disposer failure and a short cleanup timeout, then inspect the persisted records.
4. Assert record fields are attributed, bounded, sanitized, and ordered; compare Tool/Run outcomes and Session entries with the pre-diagnostic state.
5. Fill the store past its retention bound and simulate a write/trim failure; confirm health is explicit and valid domain data remains unchanged.
6. Run the CLI inspection command with valid, empty, and invalid filters and inspect its exit codes and plain output.

## 19. Risks and Mitigations

- **Secret leakage:** centralize recursive sanitation before both store and CLI boundaries; assert sentinel absence in bytes and rendered output.
- **False outcomes:** keep diagnostic writes after or beside existing domain decisions and test store failure independently from Tool/Run truth.
- **Unbounded growth:** enforce count/byte limits in the store and test oldest-first retention.
- **Second event system:** accept only narrow record writes from existing owners; do not expose a publish/subscribe API.
- **Corrupt diagnostic state:** fail closed for malformed records and preserve the file for e09s03 recovery verification.

## 20. Definition of Done and Slopcheck

- All four scenarios pass through public middleware, runtime, Plugin, store, and CLI boundaries.
- Diagnostics are durable, bounded, attributed, secret-free, and separate from domain outcome truth.
- Existing Run, Plugin, Tool, Session, and Plugin-free contracts remain compatible.
- Every task remains `failing` until its verify command passes during implementation.

### Slopcheck

- `[OK]` Python standard library — local file persistence, filtering, and bounded retention.
- `[OK]` Pydantic (already installed) — validated diagnostic records.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic boundary tests.
- No new runtime dependency, remote telemetry SDK, generic event bus, or hosted service is proposed.

### Red-Flag Check

Rejected credential-bearing logs, full Tool-result capture, remote exporters, unbounded retention, diagnostic authority over outcomes, and a replacement event bus.
