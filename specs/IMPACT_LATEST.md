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
