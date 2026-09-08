# e13s04 — Accessible and Resilient Inline Terminal Experience

## 1. Identity

- **Epic:** e13 — Inline REPL Visual and Interaction Experience
- **Story:** e13s04
- **Type:** feat
- **Risk:** P1
- **BCPs:** 2
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user operating in different terminals, I want the improved REPL to remain usable at narrow widths, in plain output, with reduced motion, and during multiline paste so that the redesign does not reduce accessibility or portability.

## 3. Scope

Harden the approved design across terminal constraints and update current user guidance. Finish with renewed v0.6 quality and artifact verification.

## 4. Requirements

- **ADDED:** Essential states remain understandable without color or animation alone and respect reduced-motion/plain-output constraints.
- **ADDED:** Narrow terminals, resizing, multiline paste, and print mode retain essential operation.
- **ADDED:** Current documentation describes the new inline interaction contract without reintroducing Textual promises.

## 5. Implementation Steps

1. Add coverage for narrow terminals, multiline paste, plain output, reduced motion, and documentation/help consistency → verify: `uv run --offline pytest tests/test_pty_prompt_layout.py tests/test_cli_print_mode.py -q`
2. Harden layout fallbacks, non-color status cues, motion preferences, and current documentation without reintroducing a full-screen frontend → verify: `uv run --offline pytest tests/test_pty_prompt_layout.py tests/test_cli_print_mode.py -q`
3. Run the complete offline quality and package gates required for the renewed v0.6 candidate → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && uv build --offline`

## 6. Design Context

Prefer existing Rich/prompt-toolkit capabilities and current plain-mode pathways. Keep visual ambition restrained by scrollback, width, and accessibility constraints.

## 7. Existing Modules and Purpose

`LivePromptSession`, `RichStreamRenderer`, `MiaREPL`, CLI print mode, current README/docs, and package checks are affected; Agent Core remains untouched.

## 8. Callers and Contracts

The primary callers are the inline `MiaREPL` loop and its `LivePromptSession` input adapter; print mode shares rendering where stated below. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, Core terminal truth, mandatory Tool middleware, append-only Sessions, and the CLI adapter boundary. Do not introduce a second execution root, queue, or frontend framework.

## 9. State and Data

No new durable state. Reduced-motion and plain-mode choices are presentation policy only.

## 10. Security and Safety

No color-only or animation-only meaning; do not expose secrets in status, help, or error output.

## 11. Performance and Resource Limits

Layout must degrade gracefully without alternate-screen rendering or unbounded buffering.

## 12. Compatibility

Preserve Python 3.12+, current dependencies, print mode, PTY behavior, and clean installation.

## 13. Observability and Diagnostics

Candidate evidence must distinguish prior v0.6 verification from fresh post-e13 evidence.

## 14. Dependencies

Depends on e13s01–e13s03 and the approved e13 design/test plan.

## 15. Risks and Mitigations

Late accessibility fixes can regress interaction; run focused tests before the full gate and inspect narrow/plain cases.

## 16. Definition of Ready

The prior three stories define the interaction contract, accessibility expectations are explicit, current documentation is identified, and the full gate commands are known.

## 17. Acceptance Criteria

### Scenario SC-e13s04-P1-01: Accessible terminal fallback

- **Given** the terminal is narrow, plain, non-interactive, or motion-reduced
- **When** the user performs an essential workflow
- **Then** content remains readable, status meaning remains available without color or animation, and no full-screen frontend is required.

### Scenario SC-e13s04-P1-02: Resilient editing

- **Given** the user pastes multiline text or resizes during a prompt or stream
- **When** the REPL continues
- **Then** text is not silently truncated or dropped and the draft/stream contract remains intact.

### Scenario SC-e13s04-P1-03: Candidate readiness

- **Given** all e13 stories are implemented
- **When** the release quality and packaging gates run
- **Then** the checks cover the added surface and publication remains separately authorized.

## 18. Verification Script

1. Exercise essential operation in a narrow terminal and plain output.
2. Exercise multiline paste and resize during prompt and streaming.
3. Confirm status remains understandable without color or motion.
4. Run the full offline quality and package gate.
5. Confirm current documentation and release artifacts describe the inline-only surface.

## 19. Out of Scope

Localization, alternate frontends, new dependencies, and redesign of Agent Core or Plugin APIs.

## 20. Definition of Done

Focused resilience/documentation checks and the full offline quality/package gate pass; current docs and e13 artifacts agree.
