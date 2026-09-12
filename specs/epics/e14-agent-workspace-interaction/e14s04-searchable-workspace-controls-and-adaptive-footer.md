# e14s04 — Searchable Workspace Controls and Adaptive Footer

## 1. Identity

- **Epic:** e14 — Agent Workspace Interaction
- **Story:** e14s04
- **Type:** feat
- **Risk:** P1
- **BCPs:** 3
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want searchable commands, Agent/model/Session selectors, and a truthful adaptive footer so that I can change context without losing a draft, mutating an active Run, or mixing lifetime usage with current context.

## 3. Scope

Extend existing prompt-toolkit selectors with a searchable Agent picker and command discovery, and make the footer label provider, Run phase, Session/workspace, and usage vs context honestly. Narrow terminals drop secondary fields instead of clipping into nonsense. This slice stays inside `LivePromptSession` and `MiaREPL`.

## 4. Requirements

#### MODIFIED: Selector coverage
**Before:** Model, scoped-model, Session resume/tree, and login/logout pickers were searchable via `interactive_select`. Agent switching used `/agent` list or `/agent <id>` without a picker. Commands used prefix `SlashCompleter` plus `/help`, not a searchable command selector.
**After:** Command, Agent, model, and Session selectors are searchable. Selectors preserve drafts, reject busy retargeting of an active Run, support narrow terminals, and do not perform network discovery merely because a picker opens.

#### MODIFIED: Footer contents
**Before:** `format_status_toolbar` showed workspace, optional agent/session, model, lifetime token count optionally as a window percent, thinking on/off, and coarse `[run_state]`. There was no provider field and no labeled split between lifetime usage and current context.
**After:** The footer presents model, provider, derived Run phase, Session/workspace context, and usage. Lifetime usage and current context are labeled as distinct values. Missing metrics are omitted, not invented. Narrow widths drop secondary fields rather than clip them into misleading fragments.

## 5. Implementation Steps

1. Add failing tests for searchable command and Agent selectors, draft-preserving busy protection, no network on picker open, and footer provider/usage/context labeling including narrow degrade → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
2. Implement searchable Agent and command selectors on the existing `interactive_select` path without adding a second command system → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
3. Implement adaptive truthful footer labels from the e14s01 projection, including provider and lifetime vs current context, with narrow-width degradation → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py tests/test_cli_print_mode.py -q`
4. Verify specification consistency and focused lint → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline ruff check src/mia_cli tests/test_cli_repl.py tests/test_pty_prompt_layout.py`

## 6. Design Context

Reuse `interactive_select` filter/token matching. Keep selectors on a worker thread when invoked from the async loop, as e13 already requires. Do not open provider network probes from a picker. Footer values stay HTML-escaped through `_safe_status_text`.

## 7. Existing Modules and Purpose

`interactive_select` / `interactive_multi_select` own searchable lists. `SlashCompleter` and `COMMAND_HINTS` own command discovery. `format_status_toolbar` owns the footer. `MiaREPL` rejects busy retargeting for agent/model/session/auth commands.

## 8. Callers and Contracts

Callers: `MiaREPL` slash handlers and keybindings; PTY and REPL tests. Preserve draft restoration, busy fail-fast retargeting, and no mutation of an in-flight `RunRequest`. Print-mode banner/status remains a non-interactive sibling, not a second footer owner with different facts.

## 9. State and Data

No new persistence. Selector choices affect only future explicit Runs. Footer values are derived from current Agent, Session, provider settings, and the workspace projection.

## 10. Security and Safety

Do not place credentials, tokens, or raw Tool arguments in the footer. Escape footer text before HTML rendering. Opening a selector is not an authentication or model-probe action.

## 11. Performance and Resource Limits

Selector lists remain bounded and width-safe. Filtering is local. Do not scan the network or hit provider APIs on open.

## 12. Compatibility

Existing model/session/tree pickers remain. e13 help and busy-retarget tests remain required. No new runtime dependency (`prompt-toolkit` [OK]).

## 13. Observability and Diagnostics

Footer is presentation only. It must not become an operational log or invent context-window capacity.

## 14. Dependencies

Depends on e14s01 for derived Run phase and e14s03 so selectors cannot steal approval focus or consume a draft during approval.

## 15. Risks and Mitigations

A picker that probes providers will look like model discovery. Cover local-only open, busy reject, draft restore, and footer labeling before adding `/queue`.

## 16. Definition of Ready

Existing selector and toolbar contracts are identified; lifecycle projection is specified; every task has a runnable verify command; no network-on-open behavior is implied.

## 17. Acceptance Criteria

### Scenario SC-e14s04-P1-01: Searchable selectors

- **Given** command, Agent, model, and Session choices
- **When** the user opens the corresponding selector and types a filter
- **Then** matching items are shown and a selection can be confirmed or cancelled explicitly.

### Scenario SC-e14s04-P1-02: Drafts and active Runs are protected

- **Given** a non-empty draft and/or an active Run
- **When** a selector opens or an Agent/model/Session change is attempted
- **Then** the draft is preserved, and an active Run is not silently retargeted.

### Scenario SC-e14s04-P1-03: No network discovery on open

- **Given** a command, Agent, model, or Session picker
- **When** the picker opens
- **Then** it lists already-known local choices and does not perform provider or network discovery as a side effect of opening.

### Scenario SC-e14s04-P1-04: Adaptive truthful footer

- **Given** idle and running workspace states at normal and narrow widths
- **When** the footer renders
- **Then** model, provider, Run phase, and Session/workspace are shown when known; lifetime usage and current context are labeled distinctly; missing metrics are omitted; narrow widths drop secondary fields instead of clipping them into misleading values.

## 18. Verification Script

1. Run focused selector, toolbar, and PTY tests.
2. Open Agent and command selectors with a draft present and confirm the draft returns.
3. Confirm busy Agent/model/Session changes remain rejected.
4. Confirm narrow footer output still identifies model and Run phase.

## 19. Out of Scope

Follow-up queue, overlay focus stacks, user theme files, and provider catalog browsing.

## 20. Definition of Done

Focused tests pass; selectors are searchable and safe; footer labels are truthful and adaptive; no network-on-open or new dependency was added.
