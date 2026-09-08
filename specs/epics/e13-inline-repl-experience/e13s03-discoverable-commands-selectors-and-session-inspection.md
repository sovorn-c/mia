# e13s03 — Discoverable Commands, Selectors, and Session Inspection

## 1. Identity

- **Epic:** e13 — Inline REPL Visual and Interaction Experience
- **Story:** e13s03
- **Type:** feat
- **Risk:** P1
- **BCPs:** 3
- **Status:** planned
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, I want commands, shortcuts, selectors, and Session inspection to be discoverable and focus-safe so that I can operate the inline REPL without memorizing hidden controls.

## 3. Scope

Unify help and keyboard vocabulary with explicit selector/inspection focus and safe Agent/model/Session navigation.

## 4. Requirements

- **ADDED:** Help accurately exposes supported command and keyboard actions in each relevant state.
- **ADDED:** Selectors and Session inspection have explicit focus and exit behavior and preserve the draft.
- **ADDED:** An active Run cannot be silently retargeted by Agent, model, or Session changes.

## 5. Implementation Steps

1. Add tests for command/key discovery, selectors, Session inspection, and focus-preserving Agent/model/Session changes → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
2. Implement the discoverable interaction vocabulary and explicit selector/inspection focus behavior using existing command infrastructure → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_pty_prompt_layout.py -q`
3. Verify busy-state retargeting is rejected or deferred explicitly and cannot mutate an active Run → verify: `uv run --offline python scripts/check-spec-consistency.py && uv run --offline pytest tests/test_cli_repl.py -q`

## 6. Design Context

Reuse slash completion, existing selectors, `/tree`, `/inspect`, and current SessionTree behavior. Improve discoverability and focus transitions rather than adding a second command system.

## 7. Existing Modules and Purpose

`print_command_menu`, `SlashCompleter`, `interactive_select`, Session resume/tree paths, and `LivePromptSession` key bindings are affected; `main.py` remains an adapter.

## 8. Callers and Contracts

The primary callers are the inline `MiaREPL` loop and its `LivePromptSession` input adapter; print mode shares rendering where stated below. Preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, Core terminal truth, mandatory Tool middleware, append-only Sessions, and the CLI adapter boundary. Do not introduce a second execution root, queue, or frontend framework.

## 9. State and Data

No new persistence. Session inspection reads append-only records and selector choices affect only future explicit Runs.

## 10. Security and Safety

Inspection and help must remain secret-free; selector actions cannot bypass Agent permissions or active Session admission.

## 11. Performance and Resource Limits

Help/completion should remain responsive and avoid rendering stale menus after state changes.

## 12. Compatibility

Existing slash command names and documented shortcuts remain compatible unless a deprecation is explicitly documented.

## 13. Observability and Diagnostics

Use existing diagnostics and test recordings; do not add telemetry or remote dependencies.

## 14. Dependencies

Depends on e13s01 state presentation and e13s02 focus/draft contract.

## 15. Risks and Mitigations

Hidden command aliases and selector focus can drift; test help output against the command registry and PTY behavior.

## 16. Definition of Ready

The command registry, selector paths, SessionTree contract, and draft focus behavior are identified; each task has a runnable verification command; and no new command family is required.

## 17. Acceptance Criteria

### Scenario SC-e13s03-P1-01: Discover controls

- **Given** the user requests help or begins command completion
- **When** the REPL presents available commands and key equivalents
- **Then** the list matches implemented behavior and distinguishes actions unavailable while busy.

### Scenario SC-e13s03-P1-02: Safe selector focus

- **Given** a draft exists and the user opens Agent/model/Session selection or inspection
- **When** the user exits or completes the selection
- **Then** the draft is preserved and focus returns explicitly to the correct context.

### Scenario SC-e13s03-P1-03: Protect active Run

- **Given** a Run is active and the user attempts to change its Agent/model/Session target
- **When** the REPL handles the request
- **Then** it rejects or explicitly defers retargeting and never mutates the active Run.

## 18. Verification Script

1. Open help and command completion and compare entries with the command registry.
2. Open each selector and Session inspection path with a draft present.
3. Confirm explicit exit and draft preservation.
4. Attempt retargeting during a Run and confirm the active Run is unchanged.
5. Run focused REPL and PTY tests.

## 19. Out of Scope

New command families, plugin-provided UI, remote control, and arbitrary command remapping.

## 20. Definition of Done

Help, selectors, Session inspection, and busy-state protection are covered with public-interface tests and documentation consistency checks.
