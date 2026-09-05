# e12s02 — Reconcile CLI/REPL-Only Product Surface

## 1. Identity

- **Epic:** e12 — CLI-Only Frontend Cleanup
- **Type:** documentation and specification
- **Risk:** P1
- **BCPs:** 2
- **Status:** done
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user or frontend developer, I want the supported product surface documented as the CLI/REPL plus UI-independent Core contracts so that product, architecture, package, and security guidance agree on which interface to use and where to build other frontends.

## 3. Scope

Update current user-facing and planning documents, release/package checks, and verification evidence to stop promising the removed full-screen Textual frontend. Keep archived e06/e10 artifacts unchanged as historical records of what v0.6 previously delivered and verified.

## 4. Requirements

- Current product, architecture, security, quality, and planning guidance names the inline CLI/REPL as Mia's supported interactive terminal surface.
- Current packaging and quality documentation does not require Textual.
- The Core boundary remains UI-independent and available to future frontend adapters.
- Historical archived evidence is not rewritten.
- YAML and specification consistency checks pass.

## 5. Implementation Steps

1. Update current README/user guidance and CLI package descriptions to remove `mia tui` instructions → verify: `! grep -R -nE 'mia tui|full-screen.*Textual|Textual frontend' README.md docs src/mia_cli --exclude-dir=tui`
2. Update current product, architecture, planning, security, release, and status records with the e12 removal decision → verify: `uv run --offline python -c "import pathlib,yaml; [yaml.safe_load(p.read_text()) for p in pathlib.Path('specs').rglob('*.yaml') if 'archive' not in p.parts]"`
3. Record e12 verification and confirm current documents contain no unsupported frontend promise → verify: `uv run --offline python scripts/check-spec-consistency.py && ! grep -R -nE --exclude-dir=__pycache__ 'retained (shallow )?TUI|Textual remains declared|MiaApp|tests/test_tui_app.py|src/mia_cli/tui' specs/tech-architecture README.md docs src tests scripts pyproject.toml uv.lock`

## Acceptance Criteria

### Scenario SC-e12s02-P1-01: Users see one supported interactive entry point

- Given the current user guide, when a user looks for interactive operation, then it documents `uv run mia` and does not instruct users to run `mia tui`.

### Scenario SC-e12s02-P1-02: Future frontend authors see the Core boundary

- Given the current product and architecture guidance, then the CLI/REPL is described as an adapter over the UI-independent Agent Core rather than the only possible frontend.

### Scenario SC-e12s02-P1-03: Specification history remains honest

- Given archived e06/e10 specifications and verification records, then they remain available as historical evidence and are not rewritten to pretend Textual was never supported.

### Scenario SC-e12s02-P1-04: Current specifications are consistent

- Given the repository, when YAML and specification consistency checks run, then the e12 capsule, release plan, and execution status agree on story IDs, statuses, paths, and BCPs.

## Verification Script

1. Follow the current README and user guide interactive instructions.
2. Confirm they point to the inline CLI/REPL only.
3. Confirm the Core boundary still describes UI-independent Agent execution.
4. Confirm archived historical evidence remains present.
5. Run the specification and documentation checks.
