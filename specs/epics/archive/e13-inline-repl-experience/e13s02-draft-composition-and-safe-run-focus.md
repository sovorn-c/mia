# e13s02 — Draft Composition and Safe Run Focus

## 1. Identity

- **Epic:** e13 — Inline REPL Visual and Interaction Experience
- **Story:** e13s02
- **Type:** feat
- **Risk:** P0
- **BCPs:** 4
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, I want to compose my next prompt while a Run is active without submitting it, losing it, or accidentally approving a Tool.

## 3. Scope

Add the bounded draft editor and focus state machine across idle, running, approval, cancellation, and completion. Editing is allowed during a Run; submission is explicit and disabled while busy; no queue or concurrent Run exists.

## 4. Requirements

- **ADDED:** A user may edit a local draft during a Run, but Enter cannot submit it until the current Run finishes.
- **ADDED:** Completion never auto-submits the draft, and cancellation, approval, and focus transitions preserve it.
- **ADDED:** Approval input is distinct from draft input and cannot authorize a Tool through ordinary draft keystrokes.

## 5. Implementation Steps

1. Add deterministic input tests for editing a next draft while a Run streams, blocked busy submission, and draft retention after cancellation → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
2. Implement explicit draft, busy, approval, and cancellation focus coordination in `LivePromptSession`/`MiaREPL`; never enqueue or concurrently submit a draft → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
3. Verify exactly-once terminal handling and no approval or draft loss across the supported consume/cancel/close paths → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`

## 6. Design Context

Use explicit local UI focus/state rather than a scheduler or Core API. Keep the draft outside Session history until explicit submission. Account for current Escape/Ctrl+C buffer-reset behavior.

## 7. Existing Modules and Purpose

`LivePromptSession` owns prompt buffers and key bindings; `MiaREPL.execute_turn` owns Run lifecycle; `AgentRunner` remains the sole execution entry point.

## 8. Callers and Contracts

The primary callers are the inline `MiaREPL` loop and its `LivePromptSession` input adapter; print mode shares rendering where stated below. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, Core terminal truth, mandatory Tool middleware, append-only Sessions, and the CLI adapter boundary. Do not introduce a second execution root, queue, or frontend framework.

## 9. State and Data

The draft is ephemeral local input. It must not become a Session message, RunRequest, or queue item before explicit submission.

## 10. Security and Safety

Approval is a trust boundary: only the approval context can confirm a Tool. Do not log draft or approval secrets. Preserve access policy and middleware.

## 11. Performance and Resource Limits

Do not add background execution or concurrent Runs. Focus transitions must be bounded and must not block stream consumption or cleanup.

## 12. Compatibility

Preserve Ctrl+C, Esc, EOF, multiline paste, history, cancellation, and exactly-once consume/cancel/close semantics.

## 13. Observability and Diagnostics

Draft text must not enter diagnostic or Session records. Cancellation and approval outcomes remain attributed to the existing Run and Core records.

## 14. Dependencies

Depends on e07 terminal truth and e13s01 presentation; e13s01 must establish state rendering first.

## 15. Risks and Mitigations

Buffer resets and approval keystrokes can silently drop or authorize text; add deterministic PTY/input regressions before integration.

## 16. Definition of Ready

The e13 blueprint and test scenarios are approved, the input and Run contracts are identified, every task has a runnable verification command, and no queue or concurrency behavior is implied.

## 17. Acceptance Criteria

### Scenario SC-e13s02-P0-01: Compose without queueing

- **Given** a Run is active and the user types a next prompt
- **When** the user edits the draft and presses Enter
- **Then** the draft is not submitted, no automatic queue is created, and the active Run remains the only Run.

### Scenario SC-e13s02-P0-02: Preserve draft on cancellation

- **Given** a Run is active with a non-empty draft
- **When** the user cancels the Run
- **Then** the draft remains available after cancellation and the outcome follows Core cancellation truth.

### Scenario SC-e13s02-P0-03: Separate approval focus

- **Given** a Tool requires approval while a draft exists
- **When** the user enters approval input or declines
- **Then** approval is explicit, draft content is not interpreted as authorization, and the draft is restored afterward.

## 18. Verification Script

1. Start a deterministic streamed Run and type a second prompt before completion.
2. Press Enter and confirm no second Run starts and the draft remains.
3. Cancel the active Run and confirm the draft remains editable.
4. Trigger Tool approval with a draft present; confirm approval and draft input are distinct.
5. Run focused REPL and PTY tests.

## 19. Out of Scope

Automatic prompt queues, concurrent execution, persistent draft history, and new Core runtime interfaces.

## 20. Definition of Done

Focused input/REPL tests prove all three P0 scenarios; no draft loss or accidental approval occurs; and no concurrency is introduced.
