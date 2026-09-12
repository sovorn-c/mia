# Impact Analysis — e14 Agent Workspace Interaction (story planning)

**Date:** 2026-09-12
**Plan revision:** e14 implementation plan (stories e14s01–e14s05)

## Target

CLI Adapter surfaces only; Core event families stay unchanged:

- `src/mia_cli/repl.py` — `MiaREPL` turn coordination, approval callback, busy gate, slash commands, restore transcript.
- `src/mia_cli/interactive_input.py` — `LivePromptSession` draft/focus, selectors, toolbar, new `Ctrl+Q`/`/queue`.
- `src/mia_cli/renderers/rich_stream.py` — `RichStreamRenderer` live transcript, Tool rows, print-mode sibling.
- `src/mia_middleware/access.py` — existing `ApprovalCallback` / `sanitize_arguments` reused, not replaced.
- `src/mia_agent/events.py` — `TurnStartEvent.user_prompt` consumed; no new event types in this epic.

`AgentRunner`, `AgentHarness`, Sessions, and Tool middleware remain compatibility constraints, not redesign targets.

## Dependents

- `src/mia_cli/main.py` constructs print rendering and `MiaREPL`.
- Interactive and print tests share `RichStreamRenderer`.
- `AgentRunner` admission remains the concurrency backstop for the follow-up queue.
- Historical e13 PTY/REPL contracts (`Enter` while busy does not queue, approval ≠ draft, plain semantic tags) must be extended, not deleted.

## Affected Stories

- e14s01 — Visible Transcript and Truthful Run Lifecycle (new projection + user blocks).
- e14s02 — Compact Expandable Tool Rows and Safe Tool Output (renderer + sanitization display).
- e14s03 — Asynchronous Approval with Distinct Focus (replaces blocking `input()`).
- e14s04 — Searchable Workspace Controls and Adaptive Footer (selectors + toolbar).
- e14s05 — Explicit Follow-up Queue and Resilient Workspace Fallbacks (Adapter-local single-slot queue).
- Archived e13 stories stay closed; their tests remain regression locks.
- e07 terminal truth and e10 accessibility remain compatibility constraints.

## Test Coverage

Existing: `tests/test_cli_repl.py`, `tests/test_pty_prompt_layout.py`, `tests/test_cli_print_mode.py`, `tests/test_agent_runtime.py`, `tests/test_agent_loop.py`, `tests/test_middleware_pipeline.py`.

Gaps closed by `specs/tech-architecture/e14-TEST_PLAN_LATEST.md`: exactly-once user transcript, derived lifecycle, expandable sanitized Tool rows, async approval loop responsiveness, searchable Agent/command selectors, footer usage/context split, single-slot follow-up queue.

## Risk: High

Shared interactive rendering, approval, and a new explicit follow-up path cross CLI, Tool, cancellation, and accessibility boundaries while Core APIs stay frozen. Mitigate with public-interface tests per story before widening the change.

## Recommended action

Implement e14s01 first (projection + transcript). Do not start a second execution system. Keep one optional queue string in the Adapter. Add no runtime dependency.

## Verification

```bash
test -f specs/tech-architecture/e14-TEST_PLAN_LATEST.md \
  && test -f specs/epics/e14-agent-workspace-interaction/e14s01-tasks.yaml \
  && grep -q 'SC-e14s05-P0-02' specs/tech-architecture/e14-TEST_PLAN_LATEST.md
```

---

# Impact Analysis — e13 Inline REPL Experience

## Target and dependents

MiaREPL (`src/mia_cli/repl.py`), LivePromptSession (`src/mia_cli/interactive_input.py`), and RichStreamRenderer (`src/mia_cli/renderers/rich_stream.py`). Cymbal depth-2 impact reported 40 callers across 20 groups (including tests). Production consumers include CLI startup and print-mode rendering in `src/mia_cli/main.py`, MiaREPL prompt/rendering composition, and LiveInteractivePrompt compatibility input.

## Affected historical capabilities

Preserve e01/e02 prompt, keyboard, selection, streaming, and inspection behavior; e07 Run terminal truth; e10 accessible essential workflows and plain output; e12 CLI-only packaging. Their archived artifacts remain unchanged. e13 owns the new requirements, documentation delta, and renewed candidate verification.

## Existing test coverage and gaps

- `tests/test_cli_repl.py`: REPL commands, shortcuts, Agent and Session operations, cancellation, rendering.
- `tests/test_pty_prompt_layout.py`: prompt layout and input behavior.
- `tests/test_cli_print_mode.py`: shared renderer and print-mode fallback.
- New coverage needed during delivery: compose-during-Run, disabled busy submission, draft preservation through approval/cancellation/focus, streaming plus editing, resize/paste, and state-specific help.

## Risk: High

Shared interactive and print surfaces plus approval/focus coordination create regression risk despite no new public Core API. Existing input bindings reset or replace drafts. Add focused regressions through public interfaces during bp-plan/build, and preserve ADR 0002 finalization and permanent Tool safeguards. No implementation or tests were run for the feature during this analysis.

---

## Preserved previous impact report

# Impact Analysis: e12 CLI-Only Frontend Cleanup

## Target

Remove the full-screen Textual frontend and make the inline CLI/REPL Mia's only supported interactive terminal surface.

## Dependents

- `src/mia_cli/main.py:tui_command` — removed public command and import boundary.
- `src/mia_cli/tui/` — removed presentation adapter and widgets.
- `tests/test_tui_app.py` — removed frontend contract tests.
- `scripts/check-wheel-surface.py` and `scripts/check-artifact-integrity.py` — no longer require `mia_cli/tui/` in artifacts.
- Release/package tests — synthetic artifact fixtures no longer include the removed package.
- `docs/user-guide.md` and current product/planning specifications — updated to describe CLI/REPL-only support.

## Unchanged Core Dependents

`AgentRunner`, `AgentRuntimeFactory`, `AgentHarness`, Providers, Sessions, Tools, Plugins, middleware, and security controls remain unchanged. The removed frontend was a shallow adapter and did not own execution truth.

## Affected Stories

- e12s01 — Remove Full-Screen Textual Frontend.
- e12s02 — Reconcile CLI/REPL-Only Product Surface.

## Test Coverage

- `tests/test_cli_repl.py` and `tests/test_cli_print_mode.py` cover the retained interactive and print entry points.
- `tests/test_release_artifacts.py`, `tests/test_release_process.py`, and `tests/test_surface_checks.py` cover the updated package and artifact boundaries.
- `tests/test_documentation.py` covers supported CLI command references.

## Risk: Low

The change removes one presentation adapter and its dependency; the canonical headless Agent runtime and supported CLI/REPL path remain in place.

## Historical Record

Archived e06/e10 specifications and verification evidence continue to record that Textual was supported at that time. They are not rewritten.

## Recommended action

The two e12 stories are complete, the full offline quality gate passed, and the completed capsule is archived.

---

# Impact Assessment — Mia interactive Agent workspace

**Date:** 2026-09-08
**Feature:** Extend the inline REPL with a truthful Agent workspace, compact Tool presentation, async approval, and explicit follow-up queue.

## Target

Cross-cutting behavior across the existing CLI Adapter and runtime event boundary:

- `src/mia_cli/repl.py` — `MiaREPL` turn coordination, commands, approval, model/session actions.
- `src/mia_cli/interactive_input.py` — `LivePromptSession` input, draft, focus, and busy-state behavior.
- `src/mia_cli/renderers/rich_stream.py` — `RichStreamRenderer` streaming and status output.
- `src/mia_agent/agent_runner.py` — canonical Run admission, cancellation, and terminal outcome delivery.
- `src/mia_agent/harness.py` — Agent turn, Step, Tool, and Session event production.
- `src/mia_agent/events.py` and `src/mia_agent/runtime_events.py` — typed UI-consumable lifecycle contract.

## Dependents

- `src/mia_cli/main.py` constructs both the print renderer and `MiaREPL`.
- `MiaREPL` is used by interactive CLI tests and owns the current prompt/rendering integration.
- `LivePromptSession` is used by `MiaREPL` and direct PTY/input tests.
- `RichStreamRenderer` is used by both interactive REPL and non-interactive print mode.
- `AgentRunner` is used by the CLI, diagnostics, plugin, delegation, and runtime test surfaces.
- `AgentHarness` is constructed by `AgentRuntimeFactory` and direct Agent-loop/e2e tests.
- `AgentEventEnvelope` is consumed by `AgentRunner`, the REPL, print mode, and runtime tests.

## Affected stories and scope

- Historical e13 stories remain completed and must not be reopened or rewritten.
- e13’s prior exclusion of automatic queues is superseded only for this approved feature delta.
- e07 runtime-integrity contracts remain a compatibility constraint: Core still owns final Run truth and exactly-once finalization.
- e10 accessibility contracts remain a compatibility constraint: no color, animation, or full-screen UI may be required.
- The feature should be placed in a new unused epic rather than mutating archived e13 artifacts.

## Existing test coverage

- `tests/test_cli_repl.py`: REPL commands, status transitions, cancellation, selectors, approval focus, and print/interactive renderer behavior.
- `tests/test_pty_prompt_layout.py`: prompt layout, completion, pipe input, and approval focus restoration.
- `tests/test_cli_print_mode.py`: shared stream renderer and plain-mode behavior.
- `tests/test_agent_runtime.py`: Runner envelopes, cancellation, admission, and runtime failures.
- `tests/test_agent_loop.py`: Harness turn, Tool, and provider event behavior.
- `tests/test_middleware_pipeline.py`: mandatory Tool middleware and policy behavior.
- `tests/test_sessions.py` and `tests/test_e2e_scenarios.py`: append-only Session and branching behavior.

## Coverage gaps

- No public-interface regression contract for an explicit follow-up queue.
- No user-message transcript contract for a live interactive turn.
- No keyed persistent Tool card contract covering pending, partial, final, error, and cancelled states.
- No async approval round-trip test proving the event loop remains responsive.
- No shared UI reducer contract separating lifetime usage from current context usage.
- No cross-terminal guarantee that `Ctrl+Q` is delivered; `/queue` must remain the portable fallback.
- Existing prompt-toolkit async-validator and duplicate-wheel warnings remain unrelated verification concerns.

## Risk: High

The feature changes shared interactive rendering and input ownership while depending on the public Run/event contract; it also changes the approved e13 queue exclusion and crosses CLI, event, cancellation, Tool, approval, and accessibility boundaries.

## Recommended action

Proceed with an incremental new epic only after the scope and release placement are accepted. Start with a UI projection/reducer and single-owner prompt-toolkit output path; preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, Rich print mode, Tool middleware, append-only Sessions, and Core-owned cancellation truth. Add new Core events only where existing events cannot express a required UI state. Do not implement true in-flight steering, a full-screen frontend, or a second execution system.

## Verification

```bash
test -f specs/IMPACT_LATEST.md && grep -q '^## Risk: High' specs/IMPACT_LATEST.md
```
