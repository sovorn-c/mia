# Impact — e10 Accessible Product Experience and Documentation

> Historical planning artifact. Its Textual paths describe the pre-e12 implementation; the current supported terminal surface is the inline CLI/REPL.

## Target

Deliver e10 by hardening the existing terminal presentation boundaries and documenting the supported Agent product. The work covers keyboard-operable CLI/REPL/Textual workflows, explicit non-color/plain output and motion-safe behavior, and user/operator/Plugin author documentation. It must preserve the canonical `AgentRunner → AgentRuntimeFactory → AgentHarness` execution path and must not introduce a visual redesign, hosted documentation platform, or new runtime dependency.

Primary implementation seams:

- `src/mia_cli/interactive_input.py` — prompt editing, slash completion, keyboard bindings, and non-TTY selection fallbacks.
- `src/mia_cli/repl.py` — REPL command discovery, status/help presentation, and canonical Run adapter.
- `src/mia_cli/renderers/rich_stream.py` — Rich/live output, spinner behavior, and terminal status semantics.
- `src/mia_cli/main.py` — Typer command help, headless `run` entrypoint, exit status, and output-mode options.
- `src/mia_cli/tui/app.py`, `src/mia_cli/tui/widgets/`, and `src/mia_cli/tui/theme.py` — Textual focus, bindings, labels, and presentation adapter.
- `README.md` and new `docs/` guides — install, configuration, trust/lifecycle, operations, recovery, accessibility, authoring, troubleshooting, upgrades, and known limits.

## Dependents (shared boundaries)

- `AgentRunner` and `AgentRuntimeFactory` are called by CLI, REPL, TUI, Delegation, and runtime tests; e10 must only change presentation adapters.
- `LivePromptSession` is used by `MiaREPL` and prompt-layout tests; keybindings and non-TTY behavior must remain deterministic.
- `RichStreamRenderer` is used by the CLI and REPL; plain mode must not alter event ordering or terminal truth.
- `MiaApp` and its widgets are exercised by Textual pilot tests and must retain the shallow-adapter boundary.
- Typer command help and exit codes are consumed by command-line users and CLI tests.
- README and documentation are release artifacts consumed by users, operators, and Plugin authors.

## Affected stories

- **e10s01 — Keyboard-Operable Essential Terminal Workflows:** strengthen existing CLI/REPL/TUI interaction contracts and accessible textual labels.
- **e10s02 — Plain Output, Semantic Status, and Motion Safety:** add explicit and automatic non-color/non-live presentation behavior without changing Run semantics.
- **e10s03 — Complete User, Operator, and Plugin Documentation:** document the supported product and extension limits with executable command examples.

Preserve e04–e09 contracts: Agent identity, access policy, Plugin trust/lifecycle, append-only Sessions, diagnostics, recovery, terminal truth, and local-only operation.

## Test coverage and gaps

Existing coverage includes:

- `tests/test_cli_repl.py` for slash commands, prompt behavior, selectors, shortcut dispatch, non-TTY fallbacks, and animated status helpers.
- `tests/test_pty_prompt_layout.py` for prompt-toolkit input layout.
- `tests/test_cli_print_mode.py` for headless CLI rendering and command behavior.
- `tests/test_tui_app.py` for Textual mount, prompt routing, approvals, Agent switching, and canonical event rendering.
- `tests/test_surface_checks.py` and package checks for retained public surfaces.

Required new coverage closes these gaps:

- An explicit interaction matrix for essential keyboard actions across REPL and TUI, including visible labels and non-TTY fallback behavior.
- Plain, `NO_COLOR`, and non-TTY output assertions that reject ANSI/control sequences and do not start live animation.
- Truthful text status and exit-code assertions for success, error, cancellation, attention, and blocked recovery paths.
- Documentation presence, cross-link, command-example, and forbidden-placeholder checks.

## Risk: High

The target modules are shared frontend adapters with more than ten callers across CLI, REPL, TUI, and tests. Accessibility regressions can strand keyboard-only users, while output changes can hide failures, emit control sequences into automation logs, or misstate a Run outcome. Documentation omissions can also cause unsafe Plugin trust or recovery decisions.

## Recommended action

Proceed with three dependency-ordered vertical slices. Implement e10s01 first so every later output and documentation example has a stable interaction vocabulary; implement e10s02 second with public CLI/renderer tests; finish e10s03 against the resulting commands and supported trust/recovery boundaries. Reuse Typer, Rich, prompt-toolkit, and Textual already present in the project; add no package. Run `bash scripts/lib/plan-consistency-check.sh specs/epics/e10-accessible-product-documentation/` before implementation.
