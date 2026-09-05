# Test Design: e10-accessible-product-documentation

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---:|---|---|
| SC-e10s01-P0-01 | Essential REPL prompt, completion, submit, clear/cancel, command discovery, and quit actions are keyboard-operable and deterministic in TTY and non-TTY contexts | P0 | Integration | `tests/test_cli_repl.py`, `tests/test_pty_prompt_layout.py`, `src/mia_cli/interactive_input.py` |
| SC-e10s01-P0-02 | Textual prompt focus, Agent switching, new-Agent, quit, and approval actions have keyboard bindings, visible textual labels, and accessible focus order | P0 | Integration | `tests/test_tui_app.py`, `src/mia_cli/tui/app.py`, `src/mia_cli/tui/widgets/` |
| SC-e10s01-P1-03 | Help and shortcut discovery exposes the same essential actions without requiring a mouse, color, or hidden icon meaning | P1 | E2E | `tests/test_cli_repl.py`, `tests/test_tui_app.py`, `src/mia_cli/repl.py` |
| SC-e10s02-P0-01 | Explicit plain mode, `NO_COLOR`, and non-TTY execution emit readable output without ANSI/control sequences or live-only updates | P0 | Integration | `tests/test_cli_print_mode.py`, `tests/test_cli_repl.py`, `src/mia_cli/main.py`, `src/mia_cli/renderers/rich_stream.py` |
| SC-e10s02-P0-02 | Running, success, error, cancellation, attention, and blocked states have text labels that remain meaningful without color or emoji | P0 | Integration | `tests/test_cli_print_mode.py`, `tests/test_recovery_cli.py`, `src/mia_cli/renderers/rich_stream.py` |
| SC-e10s02-P1-03 | Plain and accessible presentation never changes Agent/Run terminal truth, Tool policy, or exit-code semantics | P1 | Integration | `tests/test_agent_runtime.py`, `tests/test_cli_print_mode.py`, `src/mia_cli/main.py` |
| SC-e10s02-P1-04 | Existing interactive Rich/REPL/TUI presentation remains compatible when accessible plain mode is not selected | P1 | Regression | `tests/test_cli_repl.py`, `tests/test_tui_app.py`, `tests/test_cli_print_mode.py` |
| SC-e10s03-P1-01 | A fresh user can find installation, provider configuration, first Run, Agent, Session, and access guidance with executable examples | P1 | E2E | `README.md`, `docs/README.md`, `docs/user-guide.md` |
| SC-e10s03-P1-02 | Operators can find diagnostics, data locations, backup/restore, recovery, troubleshooting, and non-destructive limits | P1 | E2E | `docs/operator-guide.md`, `specs/epics/archive/e09-local-operations-recovery/` |
| SC-e10s03-P1-03 | Plugin authors can find trust, provenance, lifecycle, contribution, compatibility, data ownership, and unsandboxed-code limits | P1 | E2E | `docs/plugin-author-guide.md`, `specs/adr/0003-governed-core-extension-host.md` |
| SC-e10s03-P2-04 | Documentation links, command examples, terminology, version references, and known-limit statements are internally consistent and contain no placeholder guidance | P2 | Unit | `tests/test_documentation.py`, `scripts/` |

## 2. Fixture Architecture & Isolation

- **CLI fixtures:** Use Typer invocation or direct public command functions with `Console(record=True)` and `tmp_path`; capture stdout as text and assert no escape sequences in plain mode.
- **REPL fixtures:** Reuse `LivePromptSession`, prompt-toolkit `create_pipe_input`, `DummyOutput`, and existing `MiaREPL` fixtures. No real terminal, network, provider, or home directory is required.
- **TUI fixtures:** Reuse `MiaApp.run_test()` and Textual Pilot. Assert focus, bindings, labels, action routing, and rendered text through public widgets.
- **Runtime fixtures:** Use `MockProvider`, `AgentRunner`, and `contextlib.aclosing` only where output-mode tests must prove terminal truth is unchanged.
- **Documentation fixtures:** Use repository-relative path checks and a small standard-library validator for required headings, links, supported command examples, and forbidden placeholders. Do not fetch the network.
- **Isolation:** Tests use temporary Agent roots and synthetic data. They must not read credentials, mutate user Sessions, or depend on terminal dimensions, color support, or animation timing.

## 3. Risk and Level Strategy

P0 scenarios stay at integration boundaries because keyboard and presentation behavior must be proven through the actual frontend adapters while preserving Core ownership. P1 scenarios cover cross-frontend compatibility, truthful exit behavior, and documentation of security-sensitive operations. P2 documentation consistency checks remain fast unit tests. Prefer deterministic snapshots/text assertions over screenshots and wall-clock animation tests.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Keyboard | Essential prompt, selection, help, Agent, and quit actions work without a mouse in REPL and TUI | `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py tests/test_tui_app.py -k 'keybinding or shortcut or escape or prompt or select or agent or quit'` |
| Plain output | Plain, non-TTY, and `NO_COLOR` output contains readable semantic text and no ANSI control sequences | `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py -k 'plain or color or ansi or non_tty or status or error'` |
| Motion safety | Accessible output does not start live animation or require timing-sensitive updates; interactive mode remains compatible | `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py -k 'motion or spinner or animation or plain or render'` |
| Truthfulness | Presentation mode does not alter terminal outcomes, Tool policy, diagnostics, or exit codes | `uv run --offline pytest tests/test_agent_runtime.py tests/test_cli_print_mode.py tests/test_recovery_cli.py -k 'terminal or error or cancel or exit or status'` |
| Documentation | Required user, operator, and Plugin author guidance exists, links resolve locally, and examples use supported command names | `uv run --offline pytest tests/test_documentation.py` |
| Security | Documentation and output do not expose credential values and accurately state trust and unsandboxed-code boundaries | `uv run --offline pytest tests/test_documentation.py tests/test_cli_print_mode.py -k 'secret or credential or trust or sandbox or plain' && printf 'no new security findings in affected paths\n'` |
| Quality | Existing repository quality and package surfaces remain clean | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh && uv build --offline` |

## 5. Out of Scope

- Full visual redesign, new interaction model, localization, web documentation platform, screenshots, or hosted docs.
- Remote telemetry, dashboards, process/OS sandboxing, new providers, automatic Plugin installation, background Runs, or generic Core replacement.
- Changing AgentRunner, AgentRuntimeFactory, AgentHarness, Tool policy, Session persistence, Plugin authority, recovery mutation behavior, or terminal truth merely to support presentation.
- Testing real screen-reader integration or every terminal emulator; text labels and public adapter behavior are the supported evidence.

## 6. Test Data and Security Rules

Use synthetic prompts, Agent IDs, Session IDs, Plugin IDs, and sentinel secrets. Never place API keys or authorization values in documentation fixtures or captured output. Assertions must prove plain output and docs do not leak credential-shaped values, raw exception data, private paths, or unsupported claims. A new critical/high security finding blocks e10.

## 7. Exit Criteria

All eleven scenarios pass through supported public boundaries; keyboard, plain-output, motion-safety, truthfulness, documentation, and security NFR commands pass; no required package or quality gate fails; no placeholder or broken local link remains; and `bash scripts/lib/plan-consistency-check.sh specs/epics/e10-accessible-product-documentation/` reports `CRITICAL=0 HIGH=0` before implementation.
