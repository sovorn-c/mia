# e14s05 — Explicit Follow-up Queue and Resilient Workspace Fallbacks

## 1. Identity

- **Epic:** e14 — Agent Workspace Interaction
- **Story:** e14s05
- **Type:** feat
- **Risk:** P0
- **BCPs:** 4
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want to queue exactly one follow-up prompt while a Run is active so that it starts after successful settlement, returns to my draft after cancel or failure, and remains usable when Ctrl+Q is stolen by the terminal.

## 3. Scope

Add a single-slot follow-up queue owned by the CLI Adapter: `Ctrl+Q` and `/queue` move the current draft into that slot while busy. Auto-run only after a successful Core terminal outcome. Cancellation or failure restores queued text to the draft. Harden plain/narrow/reduced-motion fallbacks and help for the finished workspace. This is not a scheduler, concurrent Run manager, or in-flight steering control.

## 4. Requirements

#### MODIFIED: Compose-during-run without queueing
**Before:** Enter while busy saved the draft and returned without queueing. e13 explicitly forbade an automatic or explicit execution queue. Completion never auto-submitted the draft.
**After:** Enter while busy still does not submit or queue. An explicit follow-up action (`Ctrl+Q` or `/queue`) moves the current draft into one queue slot. After successful settlement the queued prompt starts as the next `AgentRunner` Run. After cancellation or failure the queued text is restored to the draft and does not auto-run. Completion still does not auto-submit an ordinary unqueued draft.

#### ADDED: Portable `/queue` fallback
`Ctrl+Q` is best-effort because terminal flow control may consume it. `/queue` is always available, documented, and equivalent. Mia does not change terminal flow control to force `Ctrl+Q` delivery.

#### ADDED: Occupied-slot rejection
If the slot is already occupied, a second enqueue is rejected with an actionable message. The existing queued text is not silently replaced. The user may cancel the Run to restore queued text, then queue again.

#### ADDED: Accessible workspace fallbacks
Queue occupancy, message roles, and lifecycle labels remain understandable in plain, `NO_COLOR`, narrow, and reduced-motion modes.

## 5. Implementation Steps

1. Add failing tests for `Ctrl+Q` and `/queue` enqueue, success-only auto-run, cancel/failure restore, occupied-slot reject, no concurrent Runs, and Enter-while-busy still not queueing → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py tests/test_agent_runtime.py -q`
2. Implement the single-slot follow-up queue in `MiaREPL`/`LivePromptSession` using existing `AgentRunner` admission after successful settlement → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py tests/test_agent_runtime.py -q`
3. Document `/queue` and `Ctrl+Q` in help; keep `/queue` available when `Ctrl+Q` is absent; restore queued text after cancel/failure; no new security findings in affected paths → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q && echo "no new security findings in affected paths"`
4. Harden plain/narrow/reduced-motion fallbacks for queue status and semantic roles, then run spec consistency and focused lint → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py -q && uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py`

## 6. Design Context

The queue is Adapter-local. It is not Session history until the follow-up Run is admitted. It never steers an in-flight provider step. Same-Session concurrent admission remains fail-fast in Core; the UI must not start a second Run while one is active. Reason for Depth: none beyond the existing REPL state machine — a single optional string slot, not a queue-manager abstraction.

## 7. Existing Modules and Purpose

`LivePromptSession` blocks Enter while `is_busy` and currently has no `c-q` binding. `MiaREPL.execute_turn` owns one-at-a-time turns. `AgentRunner` fails fast on an active same-Session Run. `COMMAND_HINTS` / `print_command_menu` own help.

## 8. Callers and Contracts

Callers: interactive `MiaREPL` loop only. Print mode has no queue. Preserve ADR 0002 consume/cancel/close, append-only Sessions, and one foreground Run per Agent-owned Session. Do not construct a second execution root.

## 9. State and Data

The queued prompt is ephemeral local UI state (one optional string plus occupancy). It becomes a Session user message only when the follow-up Run is admitted. It must not be written to diagnostics.

## 10. Security and Safety

Queued text is user-controlled input, not a Tool approval channel. Queue auto-run still goes through `AgentRunner` and mandatory middleware. Do not treat queue occupancy as authorization. Do not log queued text.

## 11. Performance and Resource Limits

One slot only. No background workers, retries, or timers that start Runs. Auto-run happens on the successful terminal path of the current turn.

## 12. Compatibility

e13 Enter-while-busy tests must remain green: Enter still does not queue. `/stop`, Ctrl+C cancel, EOF/exit, and draft clearing stay distinct from queue restore. No new runtime dependency.

## 13. Observability and Diagnostics

Footer/help may show that a follow-up is queued without printing the queued text in logs. Core diagnostics still record only admitted Runs.

## 14. Dependencies

Depends on e14s01 settlement truth, e14s03 so queue actions cannot collide with approval focus, and e14s04 so `/queue` is discoverable.

## 15. Risks and Mitigations

Auto-running after failure would surprise users and skip recovery. Occupied-slot replace would drop text. Cover success, fail, cancel, occupied reject, and Ctrl+Q-missing fallback before calling the epic done.

## 16. Definition of Ready

Queue cardinality and restore rules are recorded in the epic; every task has a runnable verify command; steering and multi-item queue UI remain excluded.

## 17. Acceptance Criteria

### Scenario SC-e14s05-P0-01: Explicit enqueue while busy

- **Given** an active Run and a non-empty draft
- **When** the user presses Ctrl+Q or runs `/queue`
- **Then** the draft moves into the single follow-up slot, the editor is cleared or shows empty draft, and Enter still does not queue.

### Scenario SC-e14s05-P0-02: Auto-run only after success

- **Given** a queued follow-up and a Run that completes successfully through Core
- **When** the terminal envelope is success
- **Then** the queued prompt starts as the next admitted Run and does not overlap the previous Run.

### Scenario SC-e14s05-P0-03: Restore after cancel or failure

- **Given** a queued follow-up and a Run that is cancelled or fails
- **When** Core finalizes that unsuccessful outcome
- **Then** the queued text is restored to the draft and no follow-up Run starts.

### Scenario SC-e14s05-P0-04: Occupied slot and no concurrency

- **Given** an occupied follow-up slot
- **When** the user queues again or the UI would start two Runs
- **Then** the second enqueue is rejected without replacing the slot, and `AgentRunner` still refuses concurrent same-Session Runs.

### Scenario SC-e14s05-P1-01: `/queue` without Ctrl+Q

- **Given** a terminal that does not deliver Ctrl+Q
- **When** the user runs `/queue`
- **Then** enqueue behaves the same as the keybinding and help documents the fallback.

### Scenario SC-e14s05-P1-02: Accessible fallbacks

- **Given** plain, `NO_COLOR`, narrow, or reduced-motion output
- **When** queue occupancy and semantic roles render
- **Then** meaning remains available without color or animation.

### Scenario SC-e14s05-P1-03: Help distinguishes the three input modes

- **Given** idle, running, approval, and queued states
- **When** `/help` is shown
- **Then** it distinguishes compose-during-run, approval focus, and the explicit follow-up queue.

## 18. Verification Script

1. Run focused queue, help, print-mode, and PTY tests.
2. Queue a follow-up during a MockProvider success path and confirm it auto-runs once.
3. Queue a follow-up and cancel; confirm restore and no second Run.
4. Confirm Enter while busy still does not queue and a second `/queue` is rejected.

## 19. Out of Scope

In-flight steering, multi-item display/edit/dequeue, background scheduling, concurrent Runs, changing terminal XON/XOFF, and live Tool cards.

## 20. Definition of Done

Focused tests pass; single-slot queue matches success/cancel/fail rules; `/queue` is the portable fallback; Enter does not queue; accessible fallbacks hold; no new Core events or dependencies were added.
