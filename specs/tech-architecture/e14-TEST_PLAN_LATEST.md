# Test Design: e14 Agent Workspace Interaction

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---|---|---|
| SC-e14s01-P0-01 | Admitted user prompt appears exactly once in the live transcript | P0 | Integration | `RichStreamRenderer`, `MiaREPL`, `tests/test_cli_repl.py` |
| SC-e14s01-P0-02 | Derived thinking/responding/success/failure/cancellation matches Core envelopes | P0 | Integration | workspace projection, `tests/test_cli_repl.py` |
| SC-e14s01-P0-03 | Intermediate stream events never announce success or cancellation | P0 | Integration | `MiaREPL.execute_turn`, `tests/test_cli_repl.py` |
| SC-e14s01-P1-01 | Session restore does not duplicate a live user block for the same turn | P1 | Integration | restore path, `tests/test_cli_repl.py` |
| SC-e14s01-P1-02 | Print/plain mode remains compatible and does not require interactive chrome | P1 | Integration | `tests/test_cli_print_mode.py` |
| SC-e14s02-P0-01 | Compact Tool row shows name, safe summary, and state | P0 | Integration | `RichStreamRenderer`, `tests/test_cli_repl.py` |
| SC-e14s02-P0-02 | Expanding a completed Tool row shows the retained bounded result | P0 | Integration | `RichStreamRenderer`, `tests/test_cli_repl.py` |
| SC-e14s02-P0-03 | Tool arguments and results in the transcript are sanitized and bounded | P0 | Integration | renderer + `sanitize_arguments`, `tests/test_cli_repl.py` |
| SC-e14s02-P1-01 | Error and cancelled Tool rows remain attributable and non-successful | P1 | Integration | `tests/test_cli_repl.py` |
| SC-e14s02-P2-01 | Tool/warning/error/diff roles remain understandable without color | P2 | Unit | renderer roles, `tests/test_cli_print_mode.py` |
| SC-e14s03-P0-01 | Approval is asynchronous and the event loop remains responsive | P0 | Integration | `MiaREPL` approval callback, `tests/test_cli_repl.py` |
| SC-e14s03-P0-02 | Approval focus is distinct; ordinary draft keystrokes cannot authorize a Tool | P0 | PTY/integration | `LivePromptSession`, `tests/test_pty_prompt_layout.py` |
| SC-e14s03-P0-03 | Approve, deny, and cancel restore the exact draft; deny remains fail-closed | P0 | PTY/integration | `tests/test_cli_repl.py`, `tests/test_pty_prompt_layout.py` |
| SC-e14s03-P1-01 | Approval callback errors remain fail-closed and do not consume the draft | P1 | Integration | `tests/test_cli_repl.py` |
| SC-e14s04-P1-01 | Command, Agent, model, and Session selectors are searchable | P1 | Unit/integration | `interactive_select`, `tests/test_cli_repl.py` |
| SC-e14s04-P1-02 | Selectors preserve drafts and cannot mutate an active Run | P1 | PTY/integration | `tests/test_pty_prompt_layout.py` |
| SC-e14s04-P1-03 | Opening a picker does not perform network discovery | P1 | Integration | selector paths, `tests/test_cli_repl.py` |
| SC-e14s04-P1-04 | Footer labels provider, Run phase, and lifetime vs current context; narrow widths degrade | P1 | Unit | `format_status_toolbar`, `tests/test_cli_repl.py` |
| SC-e14s05-P0-01 | Ctrl+Q and `/queue` move the current draft into the single follow-up slot while busy | P0 | PTY/integration | `LivePromptSession`, `MiaREPL` |
| SC-e14s05-P0-02 | The queued follow-up starts only after successful Core settlement | P0 | Integration | `MiaREPL`, `tests/test_cli_repl.py` |
| SC-e14s05-P0-03 | Cancellation or failure restores queued text to the draft and does not auto-run | P0 | Integration | `tests/test_cli_repl.py`, `tests/test_pty_prompt_layout.py` |
| SC-e14s05-P0-04 | A second enqueue while the slot is occupied is rejected; no concurrent Runs | P0 | Integration | `MiaREPL`, `AgentRunner` admission |
| SC-e14s05-P1-01 | `/queue` remains available when terminal flow control consumes Ctrl+Q | P1 | Unit/integration | command registry, `tests/test_cli_repl.py` |
| SC-e14s05-P1-02 | Plain, narrow, and reduced-motion fallbacks keep queue and role meaning | P1 | PTY/integration | `tests/test_cli_print_mode.py`, `tests/test_pty_prompt_layout.py` |
| SC-e14s05-P1-03 | Help distinguishes compose-during-run, approval, and follow-up queue | P1 | Unit | `print_command_menu`, `COMMAND_HINTS` |

## 2. Fixture Architecture & Isolation

- Use `MockProvider` and deterministic async streams for normal, Tool, approval, completion, failure, and cancellation paths. Do not add a second execution root.
- Use existing `prompt_toolkit` pipe input and PTY fixtures for key sequences, approval focus, Ctrl+Q, `/queue`, selectors, resize, and draft restoration.
- Use Rich recording consoles for interactive rendering assertions and plain-mode consoles for non-interactive output.
- Use isolated temporary homes, Agent roots, Session stores, and history files; never alter user data.
- Assert Run/session identifiers, event order, and sanitized Tool payloads where truth or safety matters. Do not assert decorative spacing unless it protects a layout or accessibility contract.
- Reuse `sanitize_arguments` fixtures with secret-like keys (`api_key`, `authorization`, token-bearing values) to prove transcript bounding.
- Queue tests must drive one admitted Run to a terminal envelope, then observe whether a follow-up `RunRequest` starts. Concurrent-admission failures remain the Core fail-fast contract.

## 3. Test Level Distribution

- Unit: workspace projection/reducer, status/footer formatting, selector filtering, command availability, role fallback labels, queue-slot occupancy.
- Integration: `MiaREPL` + `LivePromptSession` + `RichStreamRenderer` + `MockProvider`, including Tool rows, approval, cancellation, and follow-up auto-run.
- PTY: transcript visibility is not PTY-primary; use PTY for focus, Ctrl+Q, draft restoration, searchable selectors, and narrow/plain fallbacks.
- System/release: full offline quality gate after the last story; no publication claim.

Default: push each scenario to the lowest level that can fail for the wrong reason. Footer labeling is unit-testable. Follow-up auto-run needs integration against `AgentRunner` admission.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Integrity | Rendered terminal state matches Core envelopes; no concurrent Run from the queue | `uv run --offline pytest tests/test_cli_repl.py tests/test_agent_runtime.py -q` |
| Safety | Transcript, footer, and Tool rows never display credentials or unbounded Tool payloads | `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q` |
| Accessibility | Essential meaning does not depend on color or animation; plain output remains usable | `uv run --offline pytest tests/test_pty_prompt_layout.py tests/test_cli_print_mode.py -q` |
| Compatibility | Existing e13 compose-during-run, busy Enter block, and print-mode contracts remain green | `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py -q` |
| Responsiveness | Approval does not block the event loop with sync `input()` | `uv run --offline pytest tests/test_cli_repl.py -q -k approval` |
| Packaging | Offline format, lint, type, tests, and build remain green after delivery | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && uv build --offline` |

## 5. Out of Scope

- Full-screen Textual, web, desktop, or alternate-screen UI.
- Visual snapshot testing of decorative styling without a behavior contract.
- In-flight steering, multi-item queue managers, background scheduling, or concurrent Runs.
- New Core event families, Tool progress events, custom Tool renderer contracts, Plugin widgets, attachments, or user theme files.
- Live expandable Tool cards, overlay focus stacks, and flicker-free differential rendering.
- Remote telemetry, browser automation, and unapproved runtime dependencies.
- Changing terminal flow control so Ctrl+Q is guaranteed.

## 6. Sequencing

Implement and verify e14s01 first because the CLI-local projection and exactly-once transcript are the integration spine. e14s02 adds compact sanitized Tool rows on that projection. e14s03 replaces blocking approval with async distinct focus against those rows. e14s04 extends searchable controls and truthful footer labeling. e14s05 adds the single-slot follow-up queue and hardens accessible fallbacks last so queue help and status have a complete workspace to describe.

## 7. Mapping to existing tests

Extend, do not delete, these locked e13 contracts:

- `tests/test_cli_repl.py`: busy retarget reject, draft preservation, stream/Tool scrollback, error vs cancel labels, approval ≠ draft.
- `tests/test_pty_prompt_layout.py`: Enter while busy does not submit; add an explicit queue path instead of weakening the Enter contract.
- `tests/test_cli_print_mode.py`: `--plain` / `NO_COLOR` / non-tty semantic tags remain required.
- `tests/test_agent_runtime.py`: same-Session admission fail-fast remains the concurrency backstop for queue tests.
