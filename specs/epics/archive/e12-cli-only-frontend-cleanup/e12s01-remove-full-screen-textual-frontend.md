# e12s01 — Remove Full-Screen Textual Frontend

## 1. Identity

- **Epic:** e12 — CLI-Only Frontend Cleanup
- **Type:** removal
- **Risk:** P1
- **BCPs:** 3
- **Status:** done
- **Requirement delta:** REMOVED

## 2. User Story

As a Mia maintainer, I want the unused full-screen Textual frontend removed so that Mia has one clear interactive terminal entry point and less frontend maintenance surface.

## 3. Scope

Remove the `mia tui` command, the `src/mia_cli/tui/` package, its Textual dependency, and tests/checks that exist only to require or exercise that frontend. Preserve the inline `mia` CLI/REPL and the canonical Agent runtime.

## 4. Requirements

- `mia tui` is absent from the public CLI surface.
- No production source imports Textual or `mia_cli.tui`.
- The inline CLI/REPL continues to launch and execute through `AgentRunner`.
- Package and artifact checks no longer require `mia_cli/tui/`.
- No Core, Provider, Session, Tool, Plugin, middleware, or security behavior changes.

## 5. Implementation Steps

1. Delete the full-screen Textual package and remove the `tui` Typer command and dependency → verify: `test ! -d src/mia_cli/tui && ! grep -q 'textual>=' pyproject.toml && ! grep -q 'def tui_command' src/mia_cli/main.py`
2. Remove Textual-specific tests and update package/artifact fixtures and checks → verify: `uv run --offline pytest tests/test_release_artifacts.py tests/test_release_process.py tests/test_surface_checks.py`
3. Verify the inline CLI/REPL remains available through the normal entry point → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py`

## Acceptance Criteria

### Scenario SC-e12s01-P1-01: Full-screen frontend is absent

- Given an installed source tree, when a user inspects `mia --help`, then no `tui` command is advertised.
- The source tree and built wheel contain no `mia_cli/tui/` package.

### Scenario SC-e12s01-P1-02: Inline CLI/REPL remains supported

- Given the repository, when the CLI/REPL tests run, then prompting, streaming, approvals, and session controls continue to use the existing runtime path.
- Removing Textual does not introduce a second execution path or alter Agent Core behavior.

### Scenario SC-e12s01-P1-03: Release surface is coherent

- Given a built artifact, when package and artifact checks run, then they validate the remaining CLI/REPL surface without requiring Textual files.

## Verification Script

1. Confirm `src/mia_cli/tui/` is absent and `textual` is not a project dependency.
2. Run `uv run --offline mia --help` and confirm no `tui` command is listed.
3. Run the focused CLI and release-surface tests.
4. Build a wheel and confirm it contains no `mia_cli/tui/` members.
