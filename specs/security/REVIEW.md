# Security Review — Agent Core Clean Break

> Historical e06 review record. The TUI references below describe the implementation at that time and are not current product requirements.

- **Scope:** Agent, runtime, Session, access, Plugin, Delegation, CLI, REPL, TUI, and package surfaces
- **Review round:** 2
- **Verdict:** PASS — prior findings are fixed and verified.

## Resolved findings

1. Session IDs now pass through AgentManager-owned path validation before JSONL storage.
2. Agent and Session paths reject symlink components and resolved paths outside the configured Agent root.
3. AgentRunner contains lookup and runtime construction failures, preserves cancellation propagation, and sanitizes error identity and credential-shaped text.
4. CLI returns non-zero for Run and Agent errors; the TUI routes approval requests through its modal callback.
5. Public and wheel gates cover package metadata, retired filenames, source symbols, entry points, and retained TUI packaging.
6. Runtime/display version values align with the 0.6.0 release target.

## Verification

- `./scripts/check-public-surface.sh` — passed.
- `uv run --offline ruff check .` — passed.
- `uv run --offline mypy src` — passed.
- `uv run --offline pytest` — 165 passed.
- `./scripts/check-coverage.sh` — 91% scoped, 97% business boundary.
- `uv build --offline` and wheel-surface inspection — passed.
- Isolated CLI/TUI UAT — passed.

No new unsafe shell interpolation, deserialization, SQL/HTTP sink, authentication endpoint, dependency, or secret-bearing log was found in the changed paths.

## e12 follow-up — CLI-Only Frontend Cleanup (2026-09-05)

- **Scope:** CLI/REPL, package metadata, wheel/artifact surface, documentation, and deleted frontend boundaries.
- **Verdict:** PASS — no new security finding was introduced.
- **Review:** The removed `mia tui` command and Textual dependency do not add an execution path. Artifact checks reject unexpected package members, and the supported CLI/REPL continues through the existing Agent runtime and security middleware.
- **Verification:** `bash scripts/check-release-gate.sh`, `uv build --offline`, wheel-surface checks, and the full test suite passed. No credentials or secret-bearing values were added.

## e13 follow-up — Inline REPL Visual and Interaction Experience (2026-09-08)

- **Scope:** Inline REPL layout, streaming and Tool activity presentation, draft composition during runs, command/selector focus, and accessible terminal fallbacks.
- **Verdict:** PASS — no security vulnerabilities or policy regressions identified.
- **Review:** The canonical Agent execution path (`AgentRunner` → `AgentRuntimeFactory` → `AgentHarness` → Providers/Tools/Middleware/Session) is strictly preserved. Prompt drafting during active runs is strictly decoupled from Tool approval inputs and cannot bypass approval gates or trigger unauthorized tool calls. No new execution paths, network sinks, deserialization points, or runtime dependencies were introduced.
- **Verification:** `bash scripts/check-release-gate.sh` (374 passed, strict mypy, 88% overall / 96% business boundary coverage, clean public surface), `uv build --offline`, wheel surface and artifact integrity verification, clean-install smoke test, and dry-run candidate verification passed cleanly.

## e14 follow-up — Agent Workspace Interaction (2026-09-12)

- **Scope:** Workspace transcript/lifecycle projection, Tool-row display and expansion, async approval focus, searchable controls/footer, follow-up queue, and changed CLI/REPL tests.
- **Verdict:** PASS — no high-confidence security finding identified.
- **Review:** The review covered the exact branch contents plus the final correction diff. The canonical `AgentRunner` → `AgentRuntimeFactory` → `AgentHarness` path, Tool middleware, fail-closed approval, bounded/sanitized display, and single-slot success-only queue remain intact. `/tool` expansion/collapse is reachable through the interactive command path; terminal C0/Cc controls are sanitized.
- **Verification:** Review pass 3 ran every story verification command, full `pytest` (404 passed), Ruff format/check, mypy, offline build, coverage, public/wheel/clean-install checks, specification consistency, and `git diff --check`. `specs/security/epics/e14/THREAT_MODEL.md` contains the affected-path threat model. Browser OAuth remains outside this CLI review and is not claimed verified.

## e14 follow-up — Agent Workspace Interaction (2026-09-12)

- **Scope:** Workspace transcript/lifecycle projection, Tool-row display and expansion, async approval focus, searchable controls/footer, follow-up queue, and changed CLI/REPL tests.
- **Verdict:** PASS — no high-confidence security finding identified.
- **Review:** The review covered the exact branch contents plus the final correction diff. The canonical `AgentRunner` → `AgentRuntimeFactory` → `AgentHarness` path, Tool middleware, fail-closed approval, bounded/sanitized display, and single-slot success-only queue remain intact. `/tool` expansion/collapse is reachable through the interactive command path; terminal C0/Cc controls are sanitized.
- **Verification:** Review pass 3 ran every story verification command, full `pytest` (404 passed), Ruff format/check, mypy, offline build, coverage, public/wheel/clean-install checks, specification consistency, and `git diff --check`. `specs/security/epics/e14/THREAT_MODEL.md` contains the affected-path threat model. Browser OAuth remains outside this CLI review and is not claimed verified.

