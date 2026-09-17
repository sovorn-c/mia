# Impact Analysis — e15 Compact Terminal Workspace

## Target

The visual projection owned by `src/mia_cli/interactive_input.py`, `src/mia_cli/repl.py`, and `src/mia_cli/renderers/rich_stream.py`: status footer, startup presentation, working status, Tool rows, approval text, and built-in semantic styling.

## Dependents (22 import/reference sites)

- `MiaREPL._get_status_toolbar` consumes `format_status_toolbar`.
- `MiaREPL.print_banner`, `MiaREPL.execute_turn`, and slash-command handling own interactive startup and lifecycle presentation.
- `mia_cli.main` consumes `RichStreamRenderer` for non-interactive/print mode.
- `mia_cli.renderers.__init__` re-exports `RichStreamRenderer`.
- `LivePromptSession` owns prompt-toolkit toolbar, prompt prefix, approval input, and selector styling.
- `tests/test_cli_repl.py`, `tests/test_cli_print_mode.py`, and `tests/test_pty_prompt_layout.py` cover the affected public presentation paths.

## Affected Stories

- e15s01 — Compact Semantic Terminal Workspace (new visual refinement epic/story).
- e14 historical contracts remain regression constraints: transcript exactly-once behavior, Tool attribution and sanitization, approval focus, footer truthfulness, plain output, and queue restoration.

## Test Coverage

- `tests/test_cli_repl.py`: footer metrics, banner/stream output, Tool rows, approval, cancellation, and transcript grouping.
- `tests/test_cli_print_mode.py`: plain output, print-mode renderer, and banner output.
- `tests/test_pty_prompt_layout.py`: prompt/toolbar layout, approval focus, narrow terminal behavior, and completion interaction.
- Gap: there is no focused assertion that the interactive visual surface is free of decorative emoji noise or forced 24-bit color values; e15s01 adds those checks at the renderer/HTML output boundary.

## Contracts to Preserve

- `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only execution path.
- `AgentHarness` remains headless; no Core event family changes.
- Prompt-toolkit remains the interactive input owner; Rich is not run live beside an active editor.
- Plain and non-interactive output remain supported.
- Status values remain derived from Core-owned lifecycle events and never announce success, failure, or cancellation prematurely.
- Tool display remains bounded, sanitized, attributable, and middleware-mediated.

## Risk: Medium

The affected modules are shared by interactive and print-mode callers, but the change is presentation-only and existing lifecycle/safety tests cover the underlying state contracts. The main regression risks are clipped narrow-terminal output, color/markup escaping, duplicate Tool/transcript lines, and plain-mode drift.

## Recommended action

Proceed with one bounded e15 story. Centralize semantic terminal roles, remove the decorative banner from interactive startup, condense the footer, simplify working/Tool/approval lines, and add regression tests before changing any Core or persistence code. No new dependency or persistent compositor is justified by this request.
