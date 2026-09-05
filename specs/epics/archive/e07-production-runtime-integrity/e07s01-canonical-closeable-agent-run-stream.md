# e07s01 — Canonical Closeable Agent Run Stream

## 1. Identity

- **Story ID:** e07s01
- **Epic:** e07 — Production Runtime Integrity
- **Type:** feat
- **Risk:** P0
- **Context:** runtime, events, Session lifecycle, CLI, REPL, TUI, and tests
- **BCPs:** 8
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia frontend or integrator, I want one validated closeable Agent Run stream so that every supported caller receives the same attributed events and truthful terminal outcome.

## 3. Context

The current `AgentRunner.prompt()` is an async iterator that constructs identity and emits error envelopes inside a generator, but it has no immutable request model, exactly-once finalizer, terminal-state guard, or deterministic early-close contract (`src/mia_agent/agent_runner.py:58-194`). CLI, REPL, TUI, Delegation, and tests therefore depend on implementation details and can disagree about cancellation or terminal delivery. The selected design in `specs/tech-architecture/DESIGN_PLAN_LATEST.md` establishes a single `AgentRunner.run(RunRequest)` `AsyncGenerator` and requires supported callers to consume, cancel, or await `aclose()`.

## 4. Problem

Without a Core-owned lifecycle state machine, provider errors, missing terminal output, cancellation, and stream closure can produce duplicate or missing terminal events. Bare async-generator abandonment cannot guarantee asynchronous cleanup timing, and a terminal envelope yielded before a late cancellation can be incorrectly reclassified as cancelled.

## 5. Goal

Introduce the canonical immutable request and closeable ordered stream. Core must resolve identity once, normalize all handled failures, atomically finalize exactly once, distinguish interruption before versus after finalization, and keep frontend Adapters shallow.

## 6. Non-Goals

- A public lifecycle handle, callback event bus, scheduler, queue, background Run manager, or remote execution.
- Provider/model registry changes or new providers.
- Same-Session admission and effective settings (e07s02).
- New governed installed-code Plugin APIs (e08).
- A hard cleanup guarantee for event-loop-blocking trusted Python.

## 7. Stakeholders

- `AgentRunner` and runtime maintainers.
- CLI print mode, REPL, and Textual TUI maintainers.
- Delegation and deterministic test authors.
- Users relying on truthful cancellation and failure output.

## 8. Dependencies

- e06 canonical `AgentRunner → AgentRuntimeFactory → AgentHarness` path.
- `RuntimeIdentity`, `AgentEventEnvelope`, `RunErrorEvent`, and existing Agent event discriminators.
- `AgentRuntimeFactory` and `AgentHarness` existing provider/Session behavior.
- `specs/tech-architecture/e07-TEST_PLAN_LATEST.md` scenarios SC-e07s01-P0-01 through P0-04.
- Python standard library `contextlib.aclosing`; no new runtime dependency.

## 9. Assumptions

- A Run is accepted on first iteration of the returned generator, not on generator creation.
- Normal callers can own the consuming task and can use `contextlib.aclosing` for early exits.
- AgentHarness remains the source of inner Agent events; AgentRunner owns envelopes and terminal normalization.
- Research specialist/coordinator sequencing remains private to AgentRunner and uses the same lifecycle rules.
- Cancellation after Core finalization is deferred until the existing terminal envelope is returned; closure after terminal delivery is idempotent.

## 10. Constraints

- `RunRequest` is Pydantic, frozen, rejects extra fields, blank prompts, unsafe IDs, invalid thresholds, and invalid context windows.
- No credentials, provider instances, runtime factories, or filesystem paths enter request data.
- Every supported Run uses one immutable Runtime Identity and one atomic idempotent Core finalizer.
- Normal consumption emits exactly one matching terminal envelope and no event follows it.
- Pre-finalization cancellation or awaited closure finalizes `cancelled`; bare abandonment is outside the contract.
- Error text and attribution are sanitized before events, Session writes, or diagnostics.
- Frontends do not create envelopes or infer terminal outcomes.

## 11. Domain Model

- **RunRequest:** immutable validated input for one Agent Run.
- **AgentEventEnvelope:** immutable Runtime Identity plus one unchanged Agent event or Core-owned `RunErrorEvent`.
- **Run finalizer:** Core-owned atomic idempotent transition from active to one terminal outcome.
- **Terminal envelope:** the sole normal-consumption delivery for the finalized outcome.
- **Supported close contract:** consume to terminal, cancel the consuming task, or await `aclose()` via `contextlib.aclosing`.

## 12. Requirements

### MODIFIED: Canonical Run entry

**Before:** Callers invoke `AgentRunner.prompt()` with separate keyword arguments and receive an async iterator whose lifecycle and terminal semantics are implicit.

**After:** Callers invoke `AgentRunner.run(RunRequest, approval_callback=...)`, receiving a closeable `AsyncGenerator[AgentEventEnvelope, None]`; request validation, identity resolution, terminal normalization, and finalization are Core-owned.

### ADDED: Immutable request validation

`RunRequest` MUST reject unknown fields, blank prompts, invalid identity values, unsafe identifiers, invalid compaction thresholds, and invalid context windows before provider execution. Provider and credential objects MUST remain constructor dependencies, not request data.

### ADDED: Exactly-once terminal truth

Core MUST atomically finalize each Run using the supported consume/cancel/awaited-close contract exactly once. Normal consumption MUST emit one terminal envelope matching the finalized outcome, and no event may follow it.

### MODIFIED: Interruption semantics

**Before:** `CancelledError` is caught in `prompt()` and a cancellation error envelope is yielded, while generator closure and post-terminal interruption are unspecified.

**After:** Before finalization, external cancellation or awaited closure atomically finalizes `cancelled`, performs the cooperative cleanup decision owned by later lifecycle work, and returns/raises without promising an envelope. After finalization, late cancellation is deferred until the existing terminal envelope is returned; awaited closure after delivery preserves the outcome. Bare abandonment has no finalization or cleanup-timing guarantee.

### ADDED: Adapter contract

CLI, REPL, and TUI MUST render delivered envelopes, handle `CancelledError`, and use `contextlib.aclosing` for early exits. They MUST NOT classify intermediate Agent events as terminal or manufacture Run envelopes.

## 13. Non-Functional Requirements

- **Determinism:** MockProvider and isolated temporary Agent homes produce stable event ordering and terminal outcomes.
- **Safety:** cancellation and closure cannot bypass access, security, audit, or Session ownership behavior.
- **Compatibility:** inner event discriminators and existing Plugin-free serialized fields remain compatible.
- **Sanitization:** malformed IDs and exception text cannot inject paths, controls, credentials, or raw secrets.
- **Async correctness:** the stream does not block the event loop and late cancellation cannot rewrite finalized truth.

## 14. Contracts

### Existing contracts preserved

- `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only prompt path.
- `RuntimeIdentity` attribution and `AgentEventEnvelope` inner-event shape remain stable.
- Research specialist/coordinator sequencing, Delegation lineage, Session append behavior, and provider injection remain supported.
- `AgentHarness` stays headless and independent from Rich, Textual, Typer, and terminal output.

### New contracts

- `RunRequest` is the only public request model for the canonical Run Interface.
- The returned object is an `AsyncGenerator` that starts work on first iteration and supports awaited `aclose()`.
- The finalizer is atomic and idempotent; pre-finalization interruption selects `cancelled`, while post-finalization interruption preserves the existing outcome.
- Supported callers use `contextlib.aclosing`; bare abandonment is an explicit unsupported misuse.

## 15. Reason for Depth and Zoom-Out

- **RunRequest:** required to validate and freeze the cross-frontend input boundary once instead of duplicating keyword validation.
- **Atomic finalizer:** required to serialize normal completion, cancellation, closure, and late interruption into one truth-preserving transition; a second public lifecycle object is deliberately avoided.
- **Closeable stream adapter usage:** required because asynchronous-generator garbage collection cannot guarantee cleanup timing.

`AgentRunner` purpose: one headless Agent prompt entry and terminal truth. Callers: `mia_cli.main`, `mia_cli.repl`, `mia_cli.tui.app`, `DelegationService`, package exports, and runtime tests. Contracts: immutable Run input, attributed ordered envelopes, sanitized terminal errors, one final outcome, and no UI dependency (`src/mia_agent/agent_runner.py:58`, `src/mia_cli/repl.py:141`, `src/mia_cli/tui/app.py:103`).

## 16. Implementation Steps

1. Add failing public-interface tests for `RunRequest`, first-iteration acceptance, identity attribution, and sanitized validation errors (ref: `specs/tech-architecture/e07-TEST_PLAN_LATEST.md`, SC-e07s01-P0-01/P0-03) → verify: `uv run --offline pytest tests/test_agent_runtime.py -k 'run_request or validation or attribution'`
2. Implement the frozen request model and `AgentRunner.run()` generator while retaining the private research path and provider/factory injection seam (ref: `specs/tech-architecture/DESIGN_PLAN_LATEST.md`) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py -k 'run or request or research'`
3. Add an atomic idempotent finalizer and terminal-state guard for normal success, handled failure, missing terminal, duplicate terminal, and sanitized rejection/error cases (ref: ADR 0002) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py -k 'terminal or failure or missing or duplicate or contract'`
4. Implement pre-finalization cancellation/awaited-close behavior, late-cancellation deferral, post-delivery idempotent closure, and explicit unsupported bare-abandonment documentation without claiming forced cleanup (ref: ADR 0002, `DESIGN_PLAN_LATEST.md`) → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_cli_repl.py -k 'cancel or close or aclose or terminal'`
5. Migrate CLI, REPL, TUI, and delegation callers to the canonical stream without moving runtime logic into Adapters; preserve the existing Research flow and event rendering (ref: e06 clean-break contract) → verify: `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py tests/test_delegation.py`
6. Run the story regression and quality checks, recording no new security findings in affected paths → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_delegation.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e07s01-P0-01: Validated request uses one canonical stream

```gherkin
Given an eligible Agent and an injected MockProvider
When a caller creates a valid RunRequest and iterates AgentRunner.run()
Then the Run starts only on first iteration
And every envelope carries one immutable Run, Task, Agent, and Session identity
And the runtime path is AgentRunner -> AgentRuntimeFactory -> AgentHarness
```

### Scenario SC-e07s01-P0-02: Normal consumption has one terminal envelope

```gherkin
Given a provider produces a successful Agent turn
When the caller consumes the closeable stream to exhaustion
Then Core finalizes the Run exactly once
And exactly one terminal envelope matches the finalized success
And no event follows the terminal envelope
```

### Scenario SC-e07s01-P0-03: Failures are Core-owned and sanitized

```gherkin
Given an invalid request, missing Agent, provider exception, missing terminal, or duplicate terminal event
When the caller iterates the Run
Then Core emits one sanitized RunErrorEvent with bounded error taxonomy
And no raw credential, secret, control character, or unsafe path is exposed
And the Run is finalized exactly once
```

### Scenario SC-e07s01-P0-04: Interruption preserves finalization truth

```gherkin
Given a Run that has not finalized
When the consuming task is cancelled or the caller awaits stream.aclose()
Then Core finalizes cancelled and returns/raises without promising an envelope
When cancellation arrives after finalization
Then Core defers it until the existing terminal envelope is returned
When closure follows terminal delivery
Then closure is idempotent and preserves the finalized outcome
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py -k 'run or request or terminal or cancel or close'`.
2. Run `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py`.
3. Run `uv run --offline pytest tests/test_delegation.py tests/test_sessions.py`.
4. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
5. Confirm generated events and errors contain no credentials or unsanitized exception text.

## 19. Risks and Mitigations

- **Duplicate finalization:** concurrent completion and cancellation could write two outcomes. Mitigation: one atomic idempotent finalizer with explicit linearization point.
- **Generator lifecycle ambiguity:** bare abandonment may delay cleanup. Mitigation: require `aclosing` in supported Adapters and exclude bare abandonment from guarantees.
- **Research regression:** specialist and coordinator have distinct identities. Mitigation: preserve private sequencing and add both-path tests.
- **Adapter leakage:** UI code may infer outcomes. Mitigation: migrate callers to render-only envelope handling and test all three surfaces.
- **Secret exposure:** request/error values may cross event boundaries. Mitigation: strict request validation and existing sanitization tests.

## 20. Definition of Done and Slopcheck

- All four P0 scenarios pass through public AgentRunner interfaces.
- Every supported caller consumes, cancels, or awaits closure; no caller relies on bare abandonment.
- Normal, pre-finalization cancellation, and awaited-close paths have one final outcome; late interruption cannot rewrite it.
- Existing Research, Delegation, Session, and frontend regressions pass.
- Tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Python standard library — immutable models, async generator lifecycle, `contextlib.aclosing`, and cancellation.
- `[OK]` Pydantic (already installed) — strict request and event boundary validation.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic async lifecycle coverage.
- No new runtime dependency or lifecycle framework is proposed.

### Red-Flag Check

Rejected a second lifecycle handle, callback event bus, cancellation envelope after terminal delivery, finalization inferred by Adapters, provider objects in request data, and any guarantee for unsupported bare stream abandonment.
