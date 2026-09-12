# e14s02 — Compact Expandable Tool Rows and Safe Tool Output

## 1. Identity

- **Epic:** e14 — Agent Workspace Interaction
- **Story:** e14s02
- **Type:** feat
- **Risk:** P0
- **BCPs:** 5
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want Tool activity as compact expandable rows with bounded sanitized content so that I can inspect what ran without flooding the transcript or seeing secrets.

## 3. Scope

Extend the e14s01 projection with attributable Tool rows: name, safe summary, state, and an explicit expand-to-retained-result action. This is a vertical slice through renderer, sanitization, and a MockProvider Tool turn. Live partial Tool output and a coordinated card engine remain out of scope.

## 4. Requirements

#### MODIFIED: Compact live Tool lines
**Before:** Live Tool rendering printed a truncated path/cmd summary and a one-line ✓/✗ result; full arguments and output were dumped only by `/inspect`. Streamed Tool output was truncated but not systematically secret-redacted in the transcript.
**After:** Each visible Tool is a compact row keyed by `call_id` with name, bounded safe summary, and state (`pending`, `completed`, `error`, `cancelled`). Expanding the row shows the retained bounded result in the transcript. `/inspect` remains the audit dump, not the only inspection path.

#### ADDED: Transcript Tool sanitization and bounds
Tool arguments and results shown in the workspace pass the same secret-redaction family as `sanitize_arguments` and are length-bounded. Credentials, authorization headers, and secret-bearing values never appear in transcript, footer, or status.

#### ADDED: Semantic Tool, warning, error, and diff roles
Tool rows and their expanded content use built-in semantic roles that remain understandable in plain/non-color output.

## 5. Implementation Steps

1. Add failing tests for compact Tool rows, expand/collapse of retained results, error/cancelled states, and secret-bearing argument/result redaction → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`
2. Implement keyed compact expandable Tool rows on the CLI projection using existing `ToolCallEvent`/`ToolResultEvent` fields, with sanitize-and-bound display → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q`
3. Prove error and cancelled Tool rows stay attributable and never look successful, including plain-role fallbacks → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q && echo "no new security findings in affected paths"`
4. Verify specification consistency and focused lint for renderer and tests → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_cli_print_mode.py`

## 6. Design Context

Keep Tool rows in `mia_cli`. Key rows by existing `call_id`. Expand is a static reveal of retained bounded content, not live partial progress. Do not add Tool progress events. Reuse `sanitize_arguments` rather than a second redaction vocabulary.

## 7. Existing Modules and Purpose

`RichStreamRenderer` owns live Tool summaries and `/inspect` audit panels. `ToolCallEvent`/`ToolResultEvent` already carry `call_id`, `tool_name`, `arguments`, `output`, and `is_error`. `sanitize_arguments` in `mia_middleware.access` redacts secret-like keys for approval payloads.

## 8. Callers and Contracts

Callers: `MiaREPL.execute_turn`, print-mode rendering, REPL and print-mode tests. Preserve mandatory Tool middleware, approval policy, and Core terminal truth. Do not bypass sanitization for expanded content. Do not change `AgentHarness` event families.

## 9. State and Data

Retained Tool display state is ephemeral UI keyed by `call_id`. It is not Session history and must not persist secret-bearing payloads. Append-only Sessions continue to store Core-owned Tool records under existing policy.

## 10. Security and Safety

This story is a trust-boundary display path. Never render credentials, tokens, or authorization headers. Bound Tool output. Fail closed to a redacted placeholder when sanitization cannot represent a value safely. Expanded content is still sanitized.

## 11. Performance and Resource Limits

Bound retained Tool output per call. Do not keep unbounded logs in the renderer. Truncation limits must be deterministic and tested.

## 12. Compatibility

Print/plain mode shows compact Tool lines without requiring an interactive expand gesture. `/inspect` remains available. No new runtime dependency (`Rich` [OK], stdlib [OK]).

## 13. Observability and Diagnostics

Do not add secret-bearing Tool arguments to diagnostics because the UI can now expand a row. Existing secret-free operational records stay unchanged.

## 14. Dependencies

Depends on e14s01 projection and transcript. Historical e07 middleware and e13 compact Tool lines remain constraints.

## 15. Risks and Mitigations

Expanded rows can leak secrets that approval already redacts. Cover secret-like keys, long payloads, error output, and cancelled Tools before replacing blocking approval.

## 16. Definition of Ready

e14s01 contracts are specified; Tool event fields and `sanitize_arguments` are identified; every task has a runnable verify command; live partial output is explicitly excluded.

## 17. Acceptance Criteria

### Scenario SC-e14s02-P0-01: Compact Tool row

- **Given** a MockProvider turn that calls a Tool
- **When** `ToolCallEvent` and `ToolResultEvent` are rendered
- **Then** the transcript shows a compact row with tool name, bounded safe summary, and state, without dumping full arguments inline.

### Scenario SC-e14s02-P0-02: Expand retained result

- **Given** a completed Tool row
- **When** the user expands it
- **Then** the retained bounded result is visible in the transcript and collapsing returns to the compact row without duplicating the live result as a second terminal outcome.

### Scenario SC-e14s02-P0-03: Sanitized bounded Tool content

- **Given** Tool arguments or results that include secret-like keys or oversized payloads
- **When** the compact or expanded row is rendered
- **Then** secrets are redacted, content is length-bounded, and the same values do not appear in the footer.

### Scenario SC-e14s02-P1-01: Error and cancelled Tool rows

- **Given** a Tool that errors or is cancelled
- **When** the row is rendered
- **Then** the state is error or cancelled, the row stays attributable, and it is not presented as success.

### Scenario SC-e14s02-P2-01: Semantic roles without color

- **Given** plain or `NO_COLOR` output
- **When** Tool, warning, error, or diff content is shown
- **Then** role meaning remains available through labels or structure, not color alone.

## 18. Verification Script

1. Run focused renderer and REPL Tool tests, including a secret-bearing fixture.
2. Expand and collapse a completed Tool row in the interactive path.
3. Confirm error/cancelled rows and plain-mode compact lines.
4. Confirm `/inspect` still exists and live rows did not become a full dump.

## 19. Out of Scope

Live expandable cards, partial Tool progress, custom Tool renderer contracts, Plugin widgets, image protocols, and async approval replacement.

## 20. Definition of Done

Focused tests pass; Tool rows are compact, expandable, sanitized, and bounded; plain fallbacks keep role meaning; no new Core events or dependencies were added.
