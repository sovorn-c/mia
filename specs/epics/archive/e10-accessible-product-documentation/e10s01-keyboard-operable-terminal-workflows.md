# e10s01 — Keyboard-Operable Essential Terminal Workflows

## 1. Identity

- **Story ID:** e10s01
- **Epic:** e10 — Accessible Product Experience and Documentation
- **Type:** feat
- **Risk:** P0
- **Context:** CLI, prompt-toolkit REPL, Textual TUI, keyboard interaction, and help discovery
- **BCPs:** 5
- **Status:** done
- **Requirement delta:** MODIFIED

## 2. User Story

As a keyboard-only user, I want to complete essential Mia workflows from the terminal so that I can submit prompts, inspect or change context, select an Agent or model, recover from accidental input, and quit without a mouse or hidden shortcut knowledge.

## 3. Context

Mia already has prompt-toolkit bindings in `src/mia_cli/interactive_input.py`, slash-command routing in `src/mia_cli/repl.py`, and Textual bindings in `src/mia_cli/tui/app.py`. Existing tests cover individual shortcuts and prompt routing, but there is no single accessible interaction contract tying essential actions to visible labels, focus behavior, and non-TTY fallbacks. e10s01 strengthens the presentation adapters without changing `AgentRunner`, `AgentRuntimeFactory`, `AgentHarness`, Tool policy, or Session semantics.

## 4. Problem

A shortcut can exist in code and still be inaccessible if it is not discoverable, has no text equivalent, depends on color or an icon, loses focus, or blocks when stdin is not a TTY. The REPL and TUI currently expose overlapping but different shortcut vocabularies, so users and documentation cannot rely on one essential workflow matrix.

## 5. Goal

Provide a deterministic keyboard interaction contract for prompt entry, submit, clear/cancel, command discovery, Agent/model selection, transcript inspection, and quit across REPL and TUI. Every essential action must have a visible textual cue and a supported non-TTY or command fallback where that frontend can be used non-interactively.

## 6. Non-Goals

- Replacing prompt-toolkit, Textual, Rich, Typer, or the canonical Agent runtime.
- Adding a mouse-driven interaction model, screen-reader integration, localization, or a full visual redesign.
- Changing Agent identity, Tool authorization, Plugin lifecycle, Session persistence, or Run terminal truth.
- Solving plain output or motion suppression beyond the interaction hooks needed by this story; e10s02 owns presentation mode.

## 7. Stakeholders

- Keyboard-only users operating the REPL or Textual TUI.
- Users working through SSH, minimal terminals, or stdin/stdout automation.
- Operators who need reliable help, inspection, Agent selection, and quit behavior.
- Maintainers of the CLI adapters and their regression tests.

## 8. Dependencies

- e07 canonical closeable Run and frontend adapter contracts.
- e08 governed Plugin and Agent Template vocabulary shown by Agent selection surfaces.
- e09 diagnostics, data, and recovery commands that must remain discoverable.
- Existing `LivePromptSession`, `MiaREPL`, `MiaApp`, prompt-toolkit, and Textual pilot fixtures.
- No dependency on e10s02 implementation; e10s02 consumes this story's stable interaction vocabulary.

## 9. Assumptions

- Standard terminal key events supported by prompt-toolkit and Textual are the supported keyboard surface.
- Command aliases remain backward-compatible unless an explicit deprecation is documented.
- Non-TTY selector behavior may use numbered or textual input; it must never wait for raw terminal bytes.
- Existing emoji and color styling may remain as decoration when text labels carry the meaning.

## 10. Constraints

- Keep `mia_agent` independent from terminal UI frameworks.
- Keep CLI, REPL, and TUI as shallow adapters over the canonical runtime.
- Do not write user Sessions, credentials, or Agent data during accessibility tests.
- Use existing dependencies only: prompt-toolkit, Textual, Rich, Typer, pytest, and standard library are `[OK]`.
- Preserve current command names, Agent IDs, Session IDs, and approval semantics.

## 11. Domain Model

- **Agent:** selected durable identity shown in the REPL/TUI and never replaced by a frontend shortcut.
- **Run:** prompt submission routed through `AgentRunner`; keyboard handling must not classify its outcome.
- **Session:** append-only history inspected or resumed through explicit commands.
- **Frontend Adapter:** CLI, REPL, or TUI presentation layer that owns input and rendering but not Core truth.
- **Essential action:** submit, clear/cancel, discover help, select Agent/model, inspect context, or quit.

## 12. Requirements

### MODIFIED: Keyboard-operable essential terminal workflow

**Before:** REPL and TUI expose several keyboard bindings and slash commands, but the surfaces are not specified as one essential interaction contract and some actions are communicated mainly by colored/icon-styled hints.

**After:** REPL and TUI provide tested keyboard paths for prompt submission, clear/cancel, command discovery, Agent/model selection, inspection, and quit. Each path has a visible text label or command equivalent, predictable focus behavior, and a deterministic non-TTY fallback where applicable.

### ADDED: Consistent interaction discovery

The REPL `/help` output, TUI help response, footer, and selector prompts must name the supported essential actions in plain text and must not require the user to infer meaning from color or an icon.

### ADDED: Safe non-TTY interaction

Non-TTY prompt and selector paths must return, cancel, or report an actionable result without raw terminal mode, infinite waiting, or mutation of user data.

## 13. Non-Functional Requirements

- Keyboard actions are deterministic and covered through public frontend interfaces.
- Focus remains on the prompt after supported actions unless an explicit selector or modal owns focus.
- No essential action is mouse-only or color-only.
- Existing interactive behavior remains compatible when the new checks are added.
- Test fixtures use `tmp_path`, `DummyOutput`, pipe input, and Textual Pilot; no real terminal or network.

## 14. Contracts

### Existing contracts preserved

- `AgentRunner.run(RunRequest)` remains the sole execution path.
- REPL and TUI route prompts through `AgentRunner` and do not construct Core internals.
- Existing slash aliases, Agent selection, approval callbacks, Session resume, and Ctrl+C/Ctrl+D behavior remain truthful.
- `mia_agent` remains UI-independent.

### New contracts

- The essential interaction matrix is represented by tests for REPL and TUI.
- Help and footer text exposes keyboard and command equivalents.
- Non-TTY input never enters raw terminal mode and returns a bounded result.

## 15. Reason for Depth and Zoom-Out

`LivePromptSession` owns prompt input and bindings; callers include `MiaREPL`, `LiveInteractivePrompt`, and prompt-layout tests. `MiaREPL` owns slash-command dispatch and calls `AgentRunner`; `MiaApp` owns Textual bindings and calls the same runner. Their contracts are input routing, focus/action dispatch, visible discovery, and frontend-only presentation. The story crosses three adapters and therefore needs an integration-level slice rather than a single binding tweak, but it must not add a new abstraction or execution root.

## 16. Implementation Steps

1. Define and test the essential REPL interaction matrix, including prompt submission, Ctrl+C clear, Escape behavior, help discovery, Agent/model selection, inspection, and quit → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -k 'keybinding or shortcut or escape or prompt or select or help or quit'`
2. Align REPL command/help text and selector prompts with visible keyboard and textual alternatives while preserving aliases and non-TTY behavior → verify: `uv run --offline pytest tests/test_cli_repl.py -k 'slash or command or help or non_tty or select'`
3. Exercise TUI focus, prompt submission, Agent switching, new-Agent, approval, help, and quit actions through Textual Pilot and add missing labels/bindings → verify: `uv run --offline pytest tests/test_tui_app.py -k 'prompt or agent or approval or help or quit or focus'`
4. Run the combined frontend regression suite and confirm no runtime or package boundary changed → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py tests/test_tui_app.py tests/test_cli_print_mode.py`

## 17. Acceptance Criteria

### Scenario SC-e10s01-P0-01: REPL essentials are keyboard-operable

- Given a supported prompt session, when the user submits, clears, cancels, invokes help, selects an Agent/model, inspects, or quits, then the documented key or command dispatches the expected action.
- Given non-TTY input, when a prompt or selector is used, then it returns a bounded text/number result or cancellation without raw terminal control.

### Scenario SC-e10s01-P0-02: TUI essentials have focus and labels

- Given the Textual app, when the user uses the prompt, Agent switch, new-Agent, approval, help, and quit paths, then focus and action routing remain deterministic and visible text identifies the action.

### Scenario SC-e10s01-P1-03: Discovery does not depend on a mouse or color

- Given REPL `/help` or TUI help/footer output, then essential actions and their keyboard/command equivalents are readable from captured text without interpreting color or emoji.

## 18. Verification Script (Step-by-Step)

1. Run the REPL and type `/help`; verify the essential keyboard and command actions are listed in text.
2. Submit a prompt, press Ctrl+C while editing, and confirm only the input buffer clears.
3. Use the documented Agent/model selection and inspection commands; verify focus returns to the prompt after completion.
4. Launch the TUI test workflow, move focus to the prompt, switch Agent, open help, and quit using documented bindings.
5. Pipe a non-TTY selector response; verify it completes or cancels without hanging or changing user data.

## 19. Risks and Mitigations

- A binding may conflict with prompt completion; cover actual prompt-toolkit binding resolution and preserve Tab completion tests.
- A TUI action may steal focus or mutate the wrong Agent; use Textual Pilot assertions for active IDs and target widgets.
- Help text may drift from implementation; centralize or test the canonical action names and make documentation validation consume them.
- Terminal-specific behavior may pass under a fake TTY but fail in pipes; retain explicit non-TTY tests.

## 20. Definition of Done and Slopcheck

- Every task has a runnable verification command and starts `failing` in its ledger.
- All three scenarios pass through public REPL/TUI interfaces.
- No required existing CLI/REPL/TUI regression fails.
- No product-code dependency is added; prompt-toolkit, Textual, Rich, Typer, pytest, and standard library are `[OK]`.
- No accessibility behavior is claimed for screen readers, arbitrary terminal emulators, or a redesigned frontend.

### Slopcheck

No new package or framework is proposed. The plan reuses existing frontend dependencies and keeps the keyboard contract explicit rather than introducing a generic interaction framework.

### Red-Flag Check

The plan deliberately avoids a new accessibility abstraction: tests and small adapter changes are sufficient for the bounded interaction matrix.
