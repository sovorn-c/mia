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
