# e13s01 — Truthful Inline Run and Stream Presentation

## 1. Identity

- **Epic:** e13 — Inline REPL Visual and Interaction Experience
- **Story:** e13s01
- **Type:** feat
- **Risk:** P1
- **BCPs:** 4
- **Status:** planned
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, I want the inline REPL to show truthful Run, Agent, model, Session, response, and Tool state so that streamed work remains readable and understandable in terminal scrollback.

## 3. Scope

Build the first vertical slice through the existing REPL renderer: compact context/status, readable streamed response and Tool activity, and terminal-state presentation.

## 4. Requirements

- **ADDED:** The inline REPL presents actual Agent, model, Session, Run, response, Tool, and terminal outcome state in scrollback without inventing metrics or classifying intermediate events as final outcomes.
- **ADDED:** Interactive and plain/print rendering retain their existing adapter boundary.

## 5. Implementation Steps

1. Add focused tests for truthful idle/running/approval/completed/cancelled/error presentation and attributed stream/Tool grouping → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`
2. Implement the compact inline status and stream presentation through the existing REPL adapter without changing Core event semantics → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`
3. Verify existing specification, lint, and focused CLI contracts after the presentation change → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_cli_print_mode.py`

## 6. Design Context

Reuse `RichStreamRenderer` and `MiaREPL` as adapters. Prefer compact text/status bands over decorative panels that consume scrollback. Keep the existing AgentRunner stream and render delivered envelopes.

## 7. Existing Modules and Purpose

`MiaREPL.execute_turn` owns turn presentation; `RichStreamRenderer` is shared by interactive and print mode; `AgentEventEnvelope`/terminal events are the source of outcome truth.

## 8. Callers and Contracts

The primary callers are the inline `MiaREPL` loop and its `LivePromptSession` input adapter; print mode shares rendering where stated below. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, Core terminal truth, mandatory Tool middleware, append-only Sessions, and the CLI adapter boundary. Do not introduce a second execution root, queue, or frontend framework.

## 9. State and Data

No new persisted data. Status is derived from the current Run and selected Agent/model/Session context.

## 10. Security and Safety

Never print credentials or sensitive Tool arguments. Preserve Core attribution, approval, sanitation, and terminal truth.

## 11. Performance and Resource Limits

Avoid per-event expensive redraws or unbounded retained output. Keep streaming incremental and compatible with current terminal widths.

## 12. Compatibility

Print mode, Rich recording tests, and existing inline output remain supported; no Textual return.

## 13. Observability and Diagnostics

Group useful state changes for local diagnosis without changing secret-free operational records.

## 14. Dependencies

Depends on e07 terminal contract, e10 plain-output requirements, and e12 CLI-only surface; all are complete historical predecessors.

## 15. Risks and Mitigations

Incorrect grouping can duplicate or hide output; cover normal, error, and cancellation paths before moving to story 2.

## 16. Definition of Ready

The existing e13 blueprint and test plan are approved; affected module contracts are understood; every task below has a runnable verification command; and no new runtime dependency is proposed. Exact key/layout details must remain within the approved design boundary.

## 17. Acceptance Criteria

### Scenario SC-e13s01-P1-01: Truthful context and Run state

- **Given** the REPL is idle, running, awaiting approval, completed, cancelled, or failed
- **When** the corresponding state is rendered
- **Then** the label and values describe the actual state without relying on color alone or claiming a non-measured metric.

### Scenario SC-e13s01-P1-02: Readable streaming and Tool activity

- **Given** a Run emits response deltas and Tool events
- **When** the inline renderer consumes them
- **Then** response text remains readable, Tool activity is distinguishable, and no final result is duplicated.

### Scenario SC-e13s01-P1-03: Terminal truth in presentation

- **Given** a Run completes, fails, or is cancelled through the supported contract
- **When** the adapter renders the outcome
- **Then** it does not announce success from an intermediate event or contradict the Core terminal outcome.

## 18. Verification Script

1. Run the story's focused tests and inspect the named state transitions.
2. Exercise the normal interactive path with a deterministic MockProvider.
3. Exercise the failure, cancellation, approval, resize, or plain-output cases named above.
4. Confirm no duplicate terminal result, accidental Tool approval, dropped draft, or unsupported full-screen surface.

## 19. Out of Scope

Next-draft editing, selector redesign, and broad responsive/a11y hardening are separate stories.

## 20. Definition of Done

Focused tests pass; interactive and print rendering remain compatible; story evidence records truthful state and no duplicate terminal output.
