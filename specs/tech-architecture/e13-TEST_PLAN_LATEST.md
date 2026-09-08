# Test Design: e13 Inline REPL Visual and Interaction Experience

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---|---|---|
| SC-e13s01-P1-01 | Truthful idle/running/approval/completed/cancelled/error state presentation | P1 | Integration | `MiaREPL`, `RichStreamRenderer`, `tests/test_cli_repl.py` |
| SC-e13s01-P1-02 | Readable streaming and Tool grouping without duplicate terminal output | P1 | Integration | `RichStreamRenderer`, `tests/test_cli_print_mode.py` |
| SC-e13s01-P1-03 | Rendered outcome agrees with Core terminal truth | P1 | Integration | `MiaREPL.execute_turn`, `tests/test_cli_repl.py` |
| SC-e13s02-P0-01 | Compose during Run without submission, queue, or concurrency | P0 | PTY/integration | `LivePromptSession`, `MiaREPL`, `tests/test_pty_prompt_layout.py` |
| SC-e13s02-P0-02 | Draft survives cancellation | P0 | PTY/integration | `LivePromptSession`, `tests/test_cli_repl.py` |
| SC-e13s02-P0-03 | Approval focus is distinct from draft input | P0 | Integration | approval path, `tests/test_cli_repl.py` |
| SC-e13s03-P1-01 | Help and completion expose implemented controls | P1 | Unit/integration | `print_command_menu`, `SlashCompleter` |
| SC-e13s03-P1-02 | Selector and inspection focus preserves draft | P1 | PTY/integration | selectors, SessionTree, `tests/test_pty_prompt_layout.py` |
| SC-e13s03-P1-03 | Busy retargeting cannot mutate active Run | P1 | Integration | `MiaREPL`, `AgentRunner` boundary |
| SC-e13s04-P1-01 | Narrow/plain/non-interactive/reduced-motion accessibility fallback | P1 | PTY/integration | `LivePromptSession`, `RichStreamRenderer` |
| SC-e13s04-P1-02 | Resize and multiline paste preserve text and stream contract | P1 | PTY/integration | `tests/test_pty_prompt_layout.py` |
| SC-e13s04-P1-03 | Fresh quality and packaging gate covers e13 | P1 | System/release | repository quality and artifact commands |

## 2. Fixture Architecture & Isolation

- Use `MockProvider` and deterministic async streams for normal, Tool, approval, completion, failure, and cancellation paths.
- Use `prompt_toolkit` pipe input and existing PTY fixtures for key sequences, multiline paste, resizing, completion, selectors, and draft preservation.
- Use Rich recording consoles for interactive rendering assertions and plain-mode consoles for non-interactive output.
- Use isolated temporary homes, Agent roots, Session stores, and history files; never alter user data.
- Assert Run/session identifiers and event order where terminal truth matters; do not assert decorative spacing unless it protects layout contracts.

## 3. Test Level Distribution

- Unit: state formatting, command registry/help mapping, status cue selection, and pure layout helpers.
- Integration: MiaREPL + LivePromptSession + MockProvider + Rich renderer, including approval and cancellation boundaries.
- PTY: prompt editing, keybindings, selector focus, multiline paste, resize, and plain terminal behavior.
- System/release: full offline quality gate, build, clean-install/artifact checks, and current documentation/spec consistency.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Accessibility | Essential meaning does not depend on color or animation; plain output remains usable | `uv run --offline pytest tests/test_pty_prompt_layout.py tests/test_cli_print_mode.py -q` |
| Compatibility | Existing CLI/REPL and print-mode tests remain green | `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -q` |
| Integrity | No concurrent Run, accidental approval, dropped draft, or false terminal outcome | `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q` |
| Packaging | Fresh v0.6 candidate passes formatting, lint, type, tests, and build gates | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && uv build --offline` |

## 5. Out of Scope

- Full-screen Textual, web, desktop, or alternate-screen UI.
- Visual snapshot testing of decorative styling without a behavior contract.
- Concurrent Runs, automatic prompt queues, or new Core runtime APIs.
- Remote telemetry, browser automation, and unapproved runtime dependencies.

## 6. Sequencing

Implement and verify e13s01 first because it establishes truthful state presentation. e13s02 then adds the P0 draft/focus contract. e13s03 builds discoverability and safe selectors on that contract. e13s04 hardens accessibility and runs the renewed release gate.
