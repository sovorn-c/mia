# e14 Agent Workspace Interaction — Threat Model

**Review scope:** `src/mia_cli/repl.py`, `src/mia_cli/interactive_input.py`,
`src/mia_cli/renderers/rich_stream.py`, their focused tests, and the user guide.

## Security boundaries

- The CLI is a presentation and approval adapter. It does not bypass Agent
  permissions, Tool middleware, or the canonical `AgentRunner` runtime.
- Tool arguments and results are untrusted display data. They are sanitized,
  serialized defensively, stripped of terminal control characters, and bounded
  to 4000 characters before display or audit retention.
- Approval uses a separate prompt-toolkit session. Missing input, cancellation,
  and approval errors return `False`.
- A follow-up is plain draft text. It is admitted only through the existing
  runtime after the current Run settles successfully; one occupied slot is
  rejected rather than silently replaced.

## Threat assessment

| Category | Data flow reviewed | Mitigation | Finding |
|---|---|---|---|
| Secrets exposure | Tool arguments/results → transcript, expandable row, audit view | `sanitize_arguments`, bounded serialization, fail-closed serialization | None at confidence >= 8 |
| Terminal/markup injection | Tool/error/user strings → Rich and prompt-toolkit output | Plain output for dynamic rows; `Text` for styled dynamic errors; HTML escaping in toolbar; control-character removal | None at confidence >= 8 |
| Approval bypass | Tool middleware callback → approval focus → boolean decision | Distinct buffer, explicit `y`/`yes`, fail-closed exceptions and empty input, draft restoration | None at confidence >= 8 |
| Scope or authorization bypass | Queue/selector commands → `MiaREPL` → `AgentRunner` | Existing Agent allowlists, middleware, and runtime admission remain authoritative | None at confidence >= 8 |
| Cross-turn contamination | Busy draft/queued text → later Run | Single-slot queue, success-only handoff, failure/cancellation restoration, no concurrent Run | None at confidence >= 8 |

## Verification evidence

- `uv run --offline pytest` — 404 passed after the final renderer correction and collapse-path fix.
- `uv run --offline ruff check .` — passed.
- `uv run --offline mypy src` — passed.
- The focused approval, Tool-row, lifecycle, selector, footer, and queue tests
  include denial, cancellation, redaction, occupied-slot, and failure paths.

No new high-confidence security finding was identified in the e14 affected
paths. Browser OAuth remains outside this CLI workspace review and is not
claimed as verified here.
