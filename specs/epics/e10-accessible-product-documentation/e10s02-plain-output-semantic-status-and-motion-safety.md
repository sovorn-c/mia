# e10s02 — Plain Output, Semantic Status, and Motion Safety

## 1. Identity

- **Story ID:** e10s02
- **Epic:** e10 — Accessible Product Experience and Documentation
- **Type:** feat
- **Risk:** P0
- **Context:** Rich renderer, headless CLI output, non-color status semantics, and live animation
- **BCPs:** 4
- **Status:** planned
- **Requirement delta:** MODIFIED

## 2. User Story

As a user running Mia in a pipe, log, accessibility setup, or reduced-motion environment, I want readable output that does not depend on ANSI color, emoji, or live animation so that I can understand progress and failure states from static text.

## 3. Context

`src/mia_cli/renderers/rich_stream.py` currently renders colored status, emoji, a live spinner, and transient updates. `src/mia_cli/main.py` routes headless `mia run` output through Rich, while `MiaREPL` uses the same renderer in interactive mode. Rich suppresses some styling in non-terminal output, but the project has no explicit plain presentation contract, no `--plain` run option, and no regression guarantee for `NO_COLOR`, captured logs, or motion-safe operation.

## 4. Problem

ANSI control sequences and transient live output are useful in an interactive terminal but can corrupt logs, confuse assistive tooling, or disappear when color is disabled. If status meaning is encoded only in green/red/blue styles, a user cannot distinguish success, error, cancellation, attention, and blocked recovery from plain output. Presentation must also remain a shallow adapter and never reinterpret Core terminal truth.

## 5. Goal

Add one explicit accessible presentation mode to the headless `run` command and renderer. `--plain`, `NO_COLOR`, or non-TTY output must suppress color and live animation and emit stable text labels; normal interactive Rich output remains compatible. Exit codes and event/Tool/Session behavior must remain unchanged.

## 6. Non-Goals

- Changing AgentRunner finalization, Tool policy, diagnostics, recovery decisions, or exit-code truth.
- Replacing Rich or adding a terminal capability detection package.
- Supporting every terminal emulator, screen reader, or a full reduced-motion preference framework.
- Removing decorative color/animation from normal interactive mode when accessible mode is not selected.
- Adding output formats such as JSON or a new logging service.

## 7. Stakeholders

- Users piping `mia run` into files or automation.
- Users with color- or motion-sensitive accessibility needs.
- Operators reading recovery, diagnostics, approval, and failure output.
- Maintainers relying on stable CLI exit behavior and renderer tests.

## 8. Dependencies

- e10s01's stable command/help vocabulary.
- e07 terminal outcome and CLI adapter contracts.
- e09 diagnostics, data, and recovery commands/statuses.
- Existing Rich `Console`, `Live`, `RichStreamRenderer`, Typer, and pytest fixtures.
- No new package or external service.

## 9. Assumptions

- `--plain` is the explicit opt-in for a TTY; `NO_COLOR` and non-TTY imply the same safe output behavior.
- Plain mode uses stable textual markers such as `[running]`, `[ok]`, `[error]`, `[cancelled]`, `[attention]`, and `[blocked]`; the exact vocabulary is tested and documented.
- Rich's ordinary interactive mode may retain existing styles and spinner behavior.
- A live spinner is presentation only and may never determine whether a Run succeeded.

## 10. Constraints

- Keep `RichStreamRenderer` a frontend renderer and preserve the typed event stream.
- Do not catch or transform Core exceptions into success.
- Do not expose credentials, raw exception data, or private paths in new output.
- Keep `NO_COLOR` handling local to presentation; it must not disable security, audit, access, or diagnostics.
- Use existing Rich/Typer behavior and standard library environment access; all proposed dependencies are `[OK]` existing packages.

## 11. Domain Model

- **Agent Run:** emits typed events and one Core-owned terminal outcome; presentation consumes but does not classify it.
- **Terminal Outcome:** success, failure, rejection, cancellation, timeout, or blocked state that must map to truthful text and exit behavior.
- **Presentation Mode:** interactive Rich or accessible plain output selected by explicit option or environment/TTY capability.
- **Live Status:** transient progress decoration that is disabled in plain mode.

## 12. Requirements

### MODIFIED: Accessible terminal output

**Before:** Rich and CLI output primarily use styles, colors, emoji, transient live spinners, and terse success/error decoration; captured output has no explicit plain-mode contract.

**After:** `mia run --plain`, `NO_COLOR`, and non-TTY execution emit stable readable text with explicit status labels and no ANSI/control sequences or live animation. Interactive Rich mode remains available and compatible when plain mode is not selected.

### MODIFIED: Status and exit truth

**Before:** Frontend renderers display event/error text but do not define a common non-color vocabulary for cancellation, attention, or blocked recovery output.

**After:** Success, failure, cancellation, attention, blocked, approval, and recovery states retain their existing truthful exit semantics and have text cues that remain meaningful without color or emoji.

### ADDED: Motion-safe presentation

Accessible plain output must not start `rich.live.Live`, update a spinner, or require timing-sensitive redraws. Static output must be complete when the command returns and safe for redirected logs.

## 13. Non-Functional Requirements

- Plain output is deterministic for the same event sequence.
- No ANSI escape/control sequence is emitted in plain, `NO_COLOR`, or non-TTY mode.
- No live thread/timer/status object is started in plain mode.
- Existing interactive output and event ordering remain compatible.
- Output tests use `Console(record=True)`, synthetic events, `CliRunner`/public commands, and `tmp_path`; no network or real credentials.

## 14. Contracts

### Existing contracts preserved

- `AgentRunner` and `AgentRuntimeFactory` remain the only runtime composition path.
- `RichStreamRenderer.on_event` consumes typed events without changing their order or terminal truth.
- CLI non-zero behavior for failed Run, rejected Tool, and blocked recovery remains unchanged.
- Rich interactive mode remains the default when a TTY supports it.

### New contracts

- `run` exposes a documented `--plain` option.
- Renderer mode selection is explicit/testable and treats non-TTY and `NO_COLOR` as plain-safe.
- Plain status labels are stable, textual, and tested for success and failure paths.

## 15. Reason for Depth and Zoom-Out

`RichStreamRenderer` is called by `src/mia_cli/main.py` and `src/mia_cli/repl.py`, while `run_command` owns the public Typer boundary and `_run_agent_loop` owns renderer construction. The contracts are event consumption, status/exit presentation, and no mutation of Core truth. Because these shared callers must agree on mode selection and terminal semantics, the change needs a CLI-to-renderer vertical slice; a generic output abstraction would be premature.

## 16. Implementation Steps

1. Add public tests and a small presentation-mode contract for explicit `--plain`, `NO_COLOR`, and non-TTY detection → verify: `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py -k 'plain or color or ansi or non_tty'`
2. Thread the selected mode from `mia run` into `RichStreamRenderer` without changing `AgentRunner` or event handling → verify: `uv run --offline pytest tests/test_cli_print_mode.py -k 'run or renderer or plain or output'`
3. Replace color/emoji-only outcome cues with stable textual labels in plain mode and disable `Live`/spinner updates there → verify: `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py -k 'status or error or cancel or spinner or animation or plain'`
4. Prove interactive compatibility and truthful exit behavior across CLI, REPL, runtime, and recovery commands → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_recovery_cli.py`

## 17. Acceptance Criteria

### Scenario SC-e10s02-P0-01: Plain output is static and readable

- Given `mia run --plain`, `NO_COLOR`, or a non-TTY stdout, when a Run emits progress and a terminal result, then output contains stable text and no ANSI/control sequence or live-only update.
- Given an accessible plain run, then `RichStreamRenderer` does not start a live spinner or require timer-based redraw.

### Scenario SC-e10s02-P0-02: Status meaning survives without color

- Given success, error, cancellation, attention, blocked recovery, or approval output, then the captured plain text identifies the state using explicit labels without relying on color or emoji.

### Scenario SC-e10s02-P1-03: Presentation cannot alter truth

- Given the same typed event sequence, then plain and interactive modes preserve terminal outcome, Tool policy, diagnostics, and command exit status.

### Scenario SC-e10s02-P1-04: Default interactive mode remains compatible

- Given a color-capable TTY without `--plain`, then existing Rich/REPL/TUI rendering and tests continue to work.

## 18. Verification Script (Step-by-Step)

1. Run `mia run --help` and verify `--plain` explains static, non-color output.
2. Execute a synthetic or MockProvider run with `--plain` and capture stdout; verify status labels are present and `\x1b[` is absent.
3. Repeat with `NO_COLOR=1` and redirected stdout; verify no live spinner/control sequences appear.
4. Exercise a failed or blocked command; verify the textual state and non-zero exit code remain truthful.
5. Run the ordinary interactive renderer tests; verify default Rich mode still renders the existing stream.

## 19. Risks and Mitigations

- A mode flag may be applied only to success output; cover Run errors, cancellation, Tool errors, approval, diagnostics, and recovery states.
- Rich may emit control sequences through a different path; assert captured bytes/text, not just style configuration.
- Disabling a spinner could accidentally hide progress; emit `[running]`/equivalent static text and test completion ordering.
- A renderer change could swallow terminal events; compare terminal event counts and CLI exit codes through existing runtime tests.

## 20. Definition of Done and Slopcheck

- Every task has a runnable verification command and starts `failing` in its ledger.
- All four scenarios pass and plain output is covered at the public CLI/renderer boundary.
- No required runtime, policy, recovery, or package check fails.
- No new package is proposed; Rich, Typer, pytest, and standard library are `[OK]`.
- No claim is made that plain mode is a full screen-reader or terminal-emulator guarantee.

### Slopcheck

No new dependency or output framework is justified. A boolean presentation mode and stable text markers are sufficient; JSON/logging formats are explicitly deferred.

### Red-Flag Check

The plan rejects a renderer rewrite and a generic accessibility service. It keeps mode selection at the CLI/presentation boundary and tests terminal truth separately.
