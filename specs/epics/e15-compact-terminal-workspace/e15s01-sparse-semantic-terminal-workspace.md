# e15s01 — Sparse Semantic Terminal Workspace

## 1. Identity

- **Epic:** e15 — Compact Terminal Workspace
- **Story:** e15s01
- **Type:** feat
- **Risk:** P1
- **BCPs:** 5
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want the inline workspace to be quiet, terminal-native, and easy to scan so that working state and Tool activity are useful without a decorative dashboard competing with my terminal.

## 3. Scope

Refine the existing e14 presentation in `mia_cli` only. Replace the boxed startup banner with one sparse brand/workspace line, remove non-essential decorative emoji, use terminal-default semantic styles, condense the footer, and simplify working/Tool/approval/lifecycle rows. Preserve the current event projection, scrollback, safety, selectors, approval focus, and queue behavior.

## 4. Requirements

#### MODIFIED: Startup presentation
**Before:** Interactive startup and `/clear` render a Rich Panel containing workspace, Agent, model, Session, token, thinking, Run state, and shortcut fields, with multiple emoji and forced hex colors.
**After:** Interactive startup and `/clear` render at most one quiet line containing the carrot brand mark and bounded workspace/Agent/model context. Detailed state and usage remain in the footer; no boxed telemetry banner is used.

#### MODIFIED: Interactive style hierarchy
**Before:** Prompt-toolkit styles and Rich working/stream styles force a bright hex palette across prompt, completion, toolbar, and live output.
**After:** Affected interactive paths use terminal defaults with bold, dim, reverse, and explicit text labels for hierarchy. No state depends on color or emoji, and no affected path emits forced hex color values.

#### MODIFIED: Working and Tool rows
**Before:** Working output uses multiple decorative symbols; Tool rows repeat the Tool name and append legacy state text, while approval and lifecycle messages use emoji/color for emphasis.
**After:** Working, Tool, approval, success, failure, and cancellation output uses compact text labels and simple terminal glyphs. Each Tool row contains one Tool summary, an attributable call ID, state, and optional duration; expansion remains bounded and keyed by the existing call ID.

#### MODIFIED: Footer
**Before:** The footer includes long labels, emoji badges, a help hint, full Session ID, and many separators; narrow mode has a separate verbose format.
**After:** The footer presents compact workspace, Agent/model/provider, usage, current context, thinking (when enabled), and lifecycle state. Missing values are omitted, values remain escaped/truthful, and narrow terminals retain only the highest-value fields without clipping.

## 5. Implementation Steps

1. Add failing assertions for sparse startup, no forced hex styles, compact footer labels, and non-color state cues while preserving existing lifecycle/tool tests → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py -q`
2. Implement sparse startup and terminal-default prompt/toolbar styles without changing prompt ownership or selector behavior → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py -q`
3. Simplify working, Tool, approval, lifecycle, and audit presentation while preserving typed event outcomes, safe bounds, expansion, and plain mode → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_pty_prompt_layout.py -q && echo "no new security findings in affected paths"`
4. Run specification consistency and the complete offline quality gate, then record verification evidence → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff format . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && uv build --offline`

## 6. Design Context

Use Pi as read-only prior art for sparse working-state hierarchy: a quiet transcript, a compact active status, attributable Tool rows, and a useful footer. Keep Mia's prompt-toolkit plus Rich foundation and normal scrollback. Terminal defaults are intentional: users' terminal themes should control color; bold/dim/reverse and text labels provide the hierarchy.

## 7. Existing Modules and Purpose

- `src/mia_cli/interactive_input.py` owns prompt-toolkit input, completion, selector presentation, and the bottom toolbar.
- `src/mia_cli/repl.py` owns interactive startup, slash-command presentation, approval wording, and lifecycle orchestration.
- `src/mia_cli/renderers/rich_stream.py` owns typed-event projection into transcript, working status, Tool rows, and audit output.

## 8. Callers and Contracts

Callers include `mia_cli.main`, `MiaREPL`, `LivePromptSession`, print-mode execution, and CLI/PTY tests. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, event-driven Run truth, mandatory Tool middleware, bounded/sanitized display, approval draft restoration, single-slot queue behavior, prompt-toolkit ownership, and plain/non-interactive output.

## 9. State and Data

No new persisted state. Existing ephemeral `ToolRow` state remains keyed by `call_id`; footer values remain derived from existing Agent, Session, runtime, and renderer state.

## 10. Security and Safety

Do not expose credentials, authorization headers, secret-bearing Tool values, or unbounded dynamic text. Keep `_safe_cli_text`, `_safe_display_text`, `_safe_value_text`, and HTML escaping in the display path. Styling changes must not bypass approval or middleware.

## 11. Performance and Resource Limits

Do not add a new renderer or background loop. Keep the existing single Rich live status lifecycle, bounded Tool rows, and local selector filtering. Avoid increasing retained output or refresh frequency.

## 12. Compatibility

Preserve plain mode, `NO_COLOR`, non-interactive output, narrow terminals, existing slash commands, `/tool` expansion, approval input, and queue behavior. No new dependency (`stdlib`, `prompt-toolkit`, and `Rich` are already approved).

## 13. Observability and Diagnostics

Presentation must reflect the current renderer phase and Core outcome. Do not add telemetry, secret-bearing status values, or new diagnostic persistence. `/inspect` remains available for detailed audit output.

## 14. Dependencies

Depends on e14's completed lifecycle, Tool, approval, footer, safety, and queue contracts. No Core change is required.

## 15. Risks and Mitigations

- Narrow terminals may clip the condensed footer; retain a focused width test.
- Removing color may weaken state recognition; retain explicit `[tool state]`, `[approval]`, `[ok]`, `[error]`, and `[cancelled]` labels.
- Shared renderer changes may affect print mode; run both interactive and print-mode suites.
- Styling refactors can accidentally change markup escaping; retain dynamic text and no-control tests.

## 16. Definition of Ready

Impact analysis identifies the shared CLI/print callers and existing coverage. The scope is limited to presentation. Each task has a runnable verification command, and no new abstraction or dependency is required.

## 17. Acceptance Criteria

### Scenario SC-e15s01-P1-01: Sparse startup

- **Given** an interactive REPL at normal or narrow width
- **When** the session starts or `/clear` runs
- **Then** one quiet carrot/workspace line appears without a boxed panel, telemetry dump, decorative emoji set, or forced hex color.

### Scenario SC-e15s01-P1-02: Terminal-native hierarchy

- **Given** a terminal with its own theme or `NO_COLOR`
- **When** prompt, toolbar, working, Tool, approval, and lifecycle output renders
- **Then** terminal defaults plus text labels/bold/dim/reverse preserve hierarchy without requiring a Mia color palette.

### Scenario SC-e15s01-P1-03: Compact attributable Tool state

- **Given** a Tool call and result with a retained bounded output
- **When** the row is rendered and expanded/collapsed
- **Then** the row contains one Tool summary, call ID, state, and duration when available; expansion remains safe and does not duplicate a terminal outcome.

### Scenario SC-e15s01-P1-04: Distinct working and approval states

- **Given** thinking, Tool execution, approval, success, failure, or cancellation
- **When** the state is shown in interactive or plain output
- **Then** users can identify the state from text labels and the existing focus/approval semantics remain unchanged.

### Scenario SC-e15s01-P1-05: Useful adaptive footer

- **Given** known or missing model/provider/context values at normal and narrow widths
- **When** the footer renders, including while a Run is active
- **Then** it shows truthful high-value fields, refreshes usage and current context as events arrive, uses the selected model's catalog context window when known, omits unknown values, escapes dynamic text, and does not clip into misleading fragments.

### Scenario SC-e15s01-P1-06: Reasoning level control

- **Given** a model with advertised reasoning levels
- **When** the user presses Shift+Tab or selects `/thinking <level>`
- **Then** Mia cycles or selects the model-supported level, applies it to the next Run, shows the active level in the footer, and keeps reasoning-trace visibility as a separate presentation setting.

### Scenario SC-e15s01-P1-07: Transcript separation

- **Given** a submitted prompt and a streamed Mia response
- **When** the response begins
- **Then** the `[user]` line is followed by a visible blank line before Mia output.

## 18. Verification Script

1. Run focused REPL, print-mode, and PTY tests.
2. Start an interactive session and confirm the top contains only the sparse carrot/workspace line.
3. Submit a prompt that uses a Tool; confirm the working row is compact, state-labeled, and expandable by call ID.
4. Trigger approval and confirm the approval line is concise while the draft remains intact.
5. Inspect the footer at normal and narrow widths; confirm model/state/usage/context remain truthful.
6. Run the complete offline quality gate.

## 19. Out of Scope

Persistent compositing, live Tool cards, partial Tool progress, new Core events, queue changes, Pi compatibility, user theme files, and broad command-output restyling outside the affected workspace surfaces.

## 20. Definition of Done

Focused regression tests and the complete offline quality gate pass; startup, footer, working, Tool, approval, and lifecycle output are sparse and terminal-native; e14 behavior and safety contracts remain intact; verification evidence is recorded.
