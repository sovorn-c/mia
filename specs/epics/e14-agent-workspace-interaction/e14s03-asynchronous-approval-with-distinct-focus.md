# e14s03 — Asynchronous Approval with Distinct Focus

## 1. Identity

- **Epic:** e14 — Agent Workspace Interaction
- **Story:** e14s03
- **Type:** feat
- **Risk:** P0
- **BCPs:** 4
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want Tool approval to own a distinct asynchronous focus so that I can approve or deny without stalling the loop, consuming my draft, or accidentally authorizing a Tool.

## 3. Scope

Replace the blocking `input()` approval path with an inline asynchronous approval context that restores the exact draft. Keep the existing `ApprovalRequest` callback contract (`bool | Awaitable[bool]`) and fail-closed policy. This is a vertical slice through `MiaREPL`, `LivePromptSession`, Tool rows from e14s02, and middleware approval.

## 4. Requirements

#### MODIFIED: Blocking stdin approval
**Before:** `_request_tool_approval` saved the draft, exited the prompt-toolkit app when running, then used synchronous `input("Approve? [y/N] ")`, restoring the draft in `finally`. The callback is typed as possibly awaitable, but the UI implementation blocked the loop.
**After:** Approval is an asynchronous inline focus context. Ordinary draft keystrokes cannot authorize a Tool. The event loop remains responsive. Approve, deny, and cancel restore the exact draft. Missing, empty, or errored approval remains fail-closed (`false`).

#### ADDED: Approval phase on the workspace projection
While approval is outstanding, the derived lifecycle and Tool row show an approval state. That phase is Adapter-local from the existing callback, not a new Core event family.

## 5. Implementation Steps

1. Add failing tests that approval is awaitable, the loop stays responsive, draft keystrokes cannot authorize, and approve/deny/cancel restore the exact draft fail-closed → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
2. Replace blocking `input()` with an async prompt-toolkit approval context that cannot consume the draft buffer → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
3. Project the approval phase onto the Tool row and lifecycle status; keep deny/error fail-closed; no new security findings in affected paths → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q && echo "no new security findings in affected paths"`
4. Verify specification consistency and focused lint for REPL and input adapters → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_pty_prompt_layout.py`

## 6. Design Context

`ApprovalCallback` already allows `Awaitable[bool]`. Keep authorization inside that callback and the existing access middleware. Do not route approval through the draft buffer or an unvalidated string. Do not add a Core approval event. prompt-toolkit remains the single interactive input owner.

## 7. Existing Modules and Purpose

`MiaREPL._request_tool_approval` is the current sync UI callback. `LivePromptSession` owns draft get/restore and busy focus. `AccessPolicy` / middleware invoke the callback before side-effecting Tools. `sanitize_arguments` already redacts approval payloads.

## 8. Callers and Contracts

Callers: `AgentRuntimeFactory` supplies the callback into the Tool pipeline; `MiaREPL` is the interactive implementation; print mode has no interactive approval. Preserve fail-closed denial, mandatory middleware, and ADR 0002 stream consumption during approval. Do not block envelope consumption with sync stdin.

## 9. State and Data

Approval focus is ephemeral UI state. Draft text remains local and must be restored byte-for-byte after the callback returns. Approval decisions are not Session messages.

## 10. Security and Safety

Approval is a high trust boundary. Only the approval context can return `true`. Default is deny. Do not log approval payloads or drafts. Show only sanitized request summaries. Callback exceptions are deny, not approve.

## 11. Performance and Resource Limits

The callback must yield to the event loop. Do not nest a second prompt-toolkit application that starves stream consumption. Bound any approval timeout to existing Tool/middleware timeouts; do not add implicit retries.

## 12. Compatibility

e13 tests that approval is distinct from draft and restores the draft remain required. Print mode is unchanged. No new runtime dependency (`prompt-toolkit` [OK]).

## 13. Observability and Diagnostics

Record that approval was requested/granted/denied only through existing secret-free diagnostic channels. Do not write draft text or unsanitized arguments into logs.

## 14. Dependencies

Depends on e14s01 lifecycle projection and e14s02 Tool rows so the pending-approval row has a place to land.

## 15. Risks and Mitigations

Exiting the prompt-toolkit app to call `input()` is the current stall. Cover approve, deny, cancel, callback exception, and draft-keystroke-is-not-yes before adding the queue.

## 16. Definition of Ready

Existing callback typing and draft restore contracts are identified; Tool rows exist in the plan; every task has a runnable verify command; no new Core event family is proposed.

## 17. Acceptance Criteria

### Scenario SC-e14s03-P0-01: Asynchronous approval remains responsive

- **Given** a side-effecting Tool that requires approval
- **When** the approval callback runs
- **Then** it is awaitable, does not call blocking `input()`, and the event loop can still progress cancellation or stream finalization.

### Scenario SC-e14s03-P0-02: Distinct focus cannot authorize from the draft

- **Given** a non-empty draft and an outstanding approval
- **When** the user types ordinary draft characters, including `y`
- **Then** the Tool is not authorized and those characters remain in the draft.

### Scenario SC-e14s03-P0-03: Restore after approve, deny, or cancel

- **Given** a saved draft and an approval prompt
- **When** the user approves, denies, or cancels approval
- **Then** the exact draft is restored, deny/cancel is fail-closed, and only an explicit approval action can return `true`.

### Scenario SC-e14s03-P1-01: Approval errors are fail-closed

- **Given** the approval callback raises or returns an empty/invalid answer
- **When** middleware receives the result
- **Then** the Tool is not authorized and the draft is still restored.

## 18. Verification Script

1. Run focused REPL and PTY approval tests.
2. Confirm a MockProvider approval-required Tool can be denied without losing a draft.
3. Confirm `y` typed in the draft does not approve.
4. Confirm no blocking `input()` remains on the interactive path.

## 19. Out of Scope

Follow-up queue, searchable Agent picker, overlay focus stacks, and new Core approval events.

## 20. Definition of Done

Focused tests pass; approval is async, fail-closed, draft-safe, and distinct; Tool rows show approval state; no new Core events or dependencies were added.
