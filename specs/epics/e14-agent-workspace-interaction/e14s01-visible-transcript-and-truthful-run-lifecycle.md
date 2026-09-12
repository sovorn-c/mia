# e14s01 — Visible Transcript and Truthful Run Lifecycle

## 1. Identity

- **Epic:** e14 — Agent Workspace Interaction
- **Story:** e14s01
- **Type:** feat
- **Risk:** P0
- **BCPs:** 5
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, I want each admitted prompt and Agent response to appear exactly once with a truthful Run phase so that I can see what I submitted and whether the Run is thinking, responding, succeeded, failed, or cancelled.

## 3. Scope

Deliver the tracer workspace slice: a CLI-local projection over existing `AgentEventEnvelope` values, exactly-once live user/Agent transcript blocks, and derived lifecycle status. This is the vertical path through `MiaREPL` → renderer → existing Core events. Compact Tool rows, async approval, searchable pickers, and the follow-up queue are later stories.

## 4. Requirements

#### ADDED: Exactly-once live user transcript block
Each admitted user prompt is visible exactly once in the interactive transcript, rendered from `TurnStartEvent.user_prompt`. Local submit must not echo a second copy. A Run that never admits must not leave a user block.

#### ADDED: Derived truthful Run lifecycle
The workspace distinguishes thinking, responding, success, failure, and cancellation from existing events (`AssistantChunkEvent`, `TurnCompleteEvent`, `AgentErrorEvent`, `RunErrorEvent`). Intermediate chunks never announce a terminal outcome.

#### MODIFIED: Coarse idle/running presentation
**Before:** `MiaREPL._run_state` was only `idle` or `running`; the footer echoed that string while the renderer used local spinner labels (`Thinking`, `Running {tool}`) that were not shared status truth.
**After:** Transcript, status, and footer consume one CLI-local projection derived from Core envelopes. Tool and approval phases may appear as `running` until e14s02/e14s03 specialize them; they must not be reported as success.

## 5. Implementation Steps

1. Add failing tests for exactly-once admitted user blocks, restore non-duplication, and truthful thinking/responding/success/failure/cancellation → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q -k "transcript or lifecycle or turn_start or cancelled or error"`
2. Implement a CLI-local workspace projection and render user/Agent blocks plus derived phase without new Core event families or a second execution path → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`
3. Keep print/plain mode compatible and prove intermediate events cannot display success or cancellation → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_agent_runtime.py -q`
4. Verify specification consistency and focused lint after the presentation change → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_cli_print_mode.py`

## 6. Design Context

Reuse `RichStreamRenderer` and `MiaREPL` as adapters. Introduce one CLI-local projection so transcript and footer cannot disagree. Reason for Depth: one derived view of Core envelopes prevents conflicting lifecycle facts across surfaces. Do not put the projection in `mia_agent`. Do not run Rich Live beside the prompt-toolkit editor. Render the user block from admitted `TurnStartEvent.user_prompt` only.

## 7. Existing Modules and Purpose

`MiaREPL.execute_turn` owns turn presentation and currently starts the renderer without printing the submitted prompt. `RichStreamRenderer` maps envelopes to scrollback and treats `TurnStartEvent` as a thinking spinner reset. `AgentHarness` already emits `TurnStartEvent.user_prompt`. `AgentRunner` owns admission and terminal truth.

## 8. Callers and Contracts

Callers: `mia_cli/main.py` constructs `MiaREPL` and print-mode rendering; tests drive `MiaREPL`, `RichStreamRenderer`, and `AgentRunner`. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, ADR 0002 exactly-once finalization, mandatory Tool middleware, append-only Sessions, and the CLI adapter boundary. Do not introduce a second execution root, queue, or frontend framework in this story.

## 9. State and Data

No new persisted data. Projection state is ephemeral per turn. Drafts remain local UI state from e13. Session restore already prints historical user lines; live rendering must not duplicate the same admitted prompt.

## 10. Security and Safety

Never print credentials. User prompts may contain sensitive text; treat them as user-controlled output, sanitize control characters, and do not copy them into diagnostics. Preserve Core attribution and terminal truth.

## 11. Performance and Resource Limits

Avoid per-chunk expensive full redraws. Keep streaming incremental and compatible with current terminal widths. Do not retain unbounded transcript copies beyond the current turn's display needs.

## 12. Compatibility

Print mode, Rich recording tests, and existing inline output remain supported. e13 compose-during-run and busy Enter blocking remain. No Textual return. No new runtime dependency (`prompt-toolkit` [OK], `Rich` [OK]).

## 13. Observability and Diagnostics

Derived UI phase is not a diagnostic record. Core envelopes and secret-free operational logs remain the source of truth.

## 14. Dependencies

Depends on completed e13 presentation, e07 terminal contract, e10 plain-output requirements, and e12 CLI-only surface. No sibling e14 story.

## 15. Risks and Mitigations

Duplicate user blocks (submit echo + `TurnStartEvent` + Session restore) are the primary failure. Cover admit, fail-to-admit, restore, success, error, and cancel before expanding Tool rows.

## 16. Definition of Ready

The e14 blueprint, impact report, and test plan are approved for planning; module purpose/callers/contracts are identified; every task has a runnable verify command; no new Core event family or runtime dependency is proposed.

## 17. Acceptance Criteria

### Scenario SC-e14s01-P0-01: Admitted user prompt appears exactly once

- **Given** an interactive turn that Core admits
- **When** `TurnStartEvent` is rendered
- **Then** the submitted prompt appears exactly once in the live transcript and is not echoed again from the local submit buffer.

### Scenario SC-e14s01-P0-02: Derived lifecycle matches Core envelopes

- **Given** thinking chunks, response chunks, successful completion, failure, or cancellation
- **When** the workspace projection consumes the envelopes
- **Then** the displayed phase is thinking, responding, success, failure, or cancellation respectively, and is shared by transcript status and footer.

### Scenario SC-e14s01-P0-03: Intermediate events are not terminal

- **Given** a Run that is still streaming
- **When** assistant or thought chunks arrive
- **Then** the UI does not announce success or cancellation, and the later Core terminal envelope wins.

### Scenario SC-e14s01-P1-01: Restore does not duplicate the live user block

- **Given** a Session restore that already prints historical user messages
- **When** a new live turn is admitted
- **Then** the new prompt is shown once for that turn and historical restore lines are not replayed as live duplicates.

### Scenario SC-e14s01-P1-02: Print/plain mode stays compatible

- **Given** `--plain`, `NO_COLOR`, or non-tty print mode
- **When** a MockProvider turn completes, fails, or is cancelled
- **Then** output remains usable without interactive chrome, and existing semantic success/error/cancelled labels still match Core truth.

## 18. Verification Script

1. Run the story's focused tests and inspect transcript plus lifecycle assertions.
2. Exercise a deterministic MockProvider interactive turn and confirm the user prompt appears once.
3. Exercise failure and cancellation and confirm the UI matches the Core terminal envelope.
4. Exercise print/plain mode and confirm no interactive-only requirement leaked.

## 19. Out of Scope

Compact expandable Tool rows, async approval replacement, searchable Agent picker, follow-up queue, and live Tool cards.

## 20. Definition of Done

Focused tests pass; user blocks are exactly-once; derived phase matches Core; print mode remains compatible; no new Core event family or runtime dependency was added.
