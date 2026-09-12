# e14 Build Verification Report

**Epic:** e14 — Agent Workspace Interaction
**Candidate:** v0.7.0-agent-workspace
**Build result:** PASS
**Verified:** 2026-09-12T02:58:26Z
**Implementation commit:** `c23c1c8` (latest implementation correction)

## Story results

| Story | Result | Evidence |
|---|---|---|
| e14s01 — Visible Transcript and Truthful Run Lifecycle | PASS | Exactly-once admitted user blocks; derived thinking/responding/success/failure/cancelled phases; plain-mode coverage |
| e14s02 — Compact Expandable Tool Rows and Safe Tool Output | PASS | Call-ID keyed rows; explicit expansion; bounded and redacted arguments/results; attributable error/cancelled rows |
| e14s03 — Asynchronous Approval with Distinct Focus | PASS | Awaitable prompt-toolkit approval buffer; draft preservation; approve/deny/cancel and fail-closed paths; pipe-focus integration |
| e14s04 — Searchable Workspace Controls and Adaptive Footer | PASS | Searchable Agent/command controls; persisted no-network model picker; provider, lifetime/current context, and narrow footer output |
| e14s05 — Explicit Follow-up Queue and Resilient Workspace Fallbacks | PASS | Single-slot `/queue` and `Ctrl+Q`; success-only sequential handoff; occupied-slot rejection; failure/cancellation restoration |

All five story ledgers contain four passing tasks each. The epic and release index are marked
`passing`, not released.

## Commands run

All commands ran in the foreground from the repository root with offline dependencies:

```text
uv run --offline ruff format .                         PASS
uv run --offline ruff check .                         PASS
uv run --offline mypy src                             PASS
uv run --offline pytest                               PASS — 402 passed
uv build --offline                                    PASS — sdist and wheel built
uv run --offline python scripts/check-spec-consistency.py PASS — clean
git diff --check                                      PASS
```

The focused CLI/PTY suite also passed: **93 passed**. The full suite emitted four warnings:
three existing prompt-toolkit async-validator warnings from draft-buffer test setup and one
existing duplicate wheel-member warning in the artifact test. They did not fail the gate.

## Security and scope

`specs/security/epics/e14/THREAT_MODEL.md` records the affected-path review. No new
high-confidence finding was identified. Tool display data is sanitized and bounded; Rich
styled dynamic errors use `Text`; approval is fail-closed; queue admission remains behind
`AgentRunner` and existing middleware.

Browser OAuth was not exercised by this build and is not claimed as verified. Whole-epic review,
release, publish, push, tag, and production deployment remain separate gates.
