# e06s02 — Agent-Native Textual TUI Adapter

## 1. Identity

- **Story ID:** e06s02
- **Epic:** e06 — Zero-Legacy Agent Core
- **Type:** refactor
- **Risk:** P1
- **Context:** Textual frontend, Agent selection, streaming events, and tests
- **BCPs:** 4
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia TUI user, I want the existing full-screen interface to select and run named Agents so that the frontend remains available while the obsolete worker backend is removed.

## 3. Context

The TUI is not the focus of this initiative, but it currently constructs `HerdManager`, transient `lead`/`coder` workers, Profile-backed harnesses, and an independent event bus. The visual widgets already render ordinary Agent events well. This story keeps the current layout and interaction shape and changes only the backend identity and event plumbing.

## 4. Problem

Deleting Herd without first rewiring the TUI would remove a supported command or force the UI to become a second runtime. Keeping Herd would preserve the wrong identity model and unrestricted worker behavior. The smallest safe path is to let the TUI call the canonical AgentRunner and render its envelopes.

## 5. Goal

Keep `mia tui`, Textual, the current header/sidebar/pane/editor widgets, model command, Agent switching, and basic new-Agent action. Replace Herd-specific construction and state with `AgentManager`, `AgentRunner`, `Agent`, and canonical Agent events. Defer all visual and multi-Agent product expansion.

## 6. Non-Goals

- New widgets, visual redesign, keybinding redesign, accessibility pass, or performance project.
- Persistent team orchestration, arbitrary worker spawning, direct messaging, or unrestricted subagent Tools.
- Replacing the TUI with the inline REPL.
- Removing the Textual dependency or `mia tui` command.
- Adding TUI-specific runtime, event bus, or policy bypass.

## 7. Stakeholders

- Existing Textual TUI users.
- Agent runtime maintainers.
- CLI/TUI test maintainers.
- Contributors who should see one Agent execution path.

## 8. Dependencies

- e06s01 canonical AgentRunner, RuntimeIdentity, AgentEventEnvelope, RunErrorEvent, and AgentRuntimeFactory.
- `AgentManager`, `Agent`, `AgentEvent`, `MockProvider`, and existing Textual widgets.
- Current `mia tui` command and `tests/test_tui_app.py`.

## 9. Assumptions

- The TUI can use built-in and persisted Agents; a typed `@agent` target must already resolve.
- The active Agent's prompt stream is executed by AgentRunner; the TUI only unwraps and renders events.
- Ctrl+N creates a persisted coding-style Agent through AgentManager, not a transient worker.
- Existing visual behavior is preserved where it does not depend on Herd-only state.
- A runtime error is displayed in the active Agent transcript without exposing secrets.

## 10. Constraints

- `mia_cli.tui` may depend on Textual and presentation libraries, but not on Profile, Mode, Workflow, or Herd modules.
- TUI code may not construct AgentHarness, provider, Tool, middleware, or Session state directly.
- TUI execution uses the same AgentRunner and AgentRuntimeFactory as the CLI/REPL.
- No new dependency, backend abstraction, event bus, or compatibility alias.
- Existing access approval, Plugin Tool filtering, Session persistence, and event sanitization remain in the core runtime.

## 11. Domain Model

- **Agent:** persisted or built-in identity shown in the sidebar.
- **Agent Run:** prompt execution initiated by the TUI through AgentRunner.
- **Agent Event Envelope:** canonical stream item unwrapped by the frontend.
- **Agent Transcript:** per-Agent visual history of user prompts and core events.
- **TUI adapter:** presentation code only; it owns no Agent execution semantics.

## 12. Requirements

### MODIFIED: TUI execution backend

**Before:** `MiaApp` builds and controls a HerdManager with transient workers and its own provider/harness path.

**After:** `MiaApp` receives or constructs AgentManager and AgentRunner and executes prompts through AgentRunner only.

### MODIFIED: TUI identity

**Before:** the default roster contains transient `lead` and `coder` workers whose display objects expose Profile and worker state.

**After:** the roster contains built-in or persisted Agents with canonical `agent_id`, display name, access policy, and Tool summary. The default target is a real Agent such as `mia`.

### MODIFIED: TUI event handling

**Before:** the app subscribes to HerdEvent and unwraps `AgentEventEnvelope` from a Herd event bus.

**After:** the app consumes AgentEventEnvelope values yielded by AgentRunner and renders their inner AgentEvent; RunErrorEvent is shown as an attributable sanitized error.

### MODIFIED: New Agent action

**Before:** Ctrl+N spawns a transient worker that exists only in HerdManager.

**After:** Ctrl+N creates a small persisted Agent through AgentManager and selects it. It does not create a second runtime or messaging system.

### ADDED: Frontend boundary

The TUI MUST remain a presentation adapter. It MUST NOT construct AgentHarness, provider clients, middleware, Tool pipelines, Session stores, or unrestricted worker Tools.

### ADDED: Deferred-depth boundary

This story MUST NOT redesign the TUI. Existing layout, widgets, and interaction affordances are retained unless a change is required to remove an obsolete identity dependency.

## 13. Non-Functional Requirements

- **Correctness:** submitted prompts reach the selected Agent and its stream renders in the correct transcript.
- **Security:** all Tools and approvals remain core-mediated; no Herd unrestricted Tools survive.
- **Compatibility:** `mia tui` remains launchable and Textual remains packaged.
- **Determinism:** tests inject AgentManager and MockProvider with temporary Agent homes.
- **Maintainability:** the TUI has one runtime caller and no legacy imports.

## 14. Contracts

### Existing contracts preserved

- `mia tui --model MODEL` remains a supported command.
- Existing Textual layout, prompt editor, tool cards, thought drawer, and transcript rendering remain.
- AgentRunner and AgentHarness event ordering remains unchanged.
- AgentManager persistence and access policy remain core-owned.

### New contracts

- `MiaApp` depends on AgentManager/AgentRunner rather than HerdManager.
- `AgentSidebar` and AgentListItem consume Agent values only.
- TUI workers iterate AgentEventEnvelope values and never call AgentHarness directly.
- Invalid Agent targets produce a safe visible error and do not create an implicit identity.

## 15. Reason for Depth and Zoom-Out

- **AgentRunner injection:** required because the TUI must share the canonical runtime and remain deterministic in tests; a new TUI runtime would duplicate security-sensitive composition.
- **Agent-only sidebar model:** required because ManagedAgent state belongs to the deleted Herd subsystem; deriving a new state machine would exceed the deferred UI scope.
- **No event bus replacement:** required because AgentRunner's async stream already supplies ordered events; another bus would be unnecessary abstraction.

`src/mia_cli/tui/app.py` exists to compose Textual widgets and route user actions. Its callers are the `mia tui` command and TUI tests. Its contracts are layout composition, Agent selection, prompt submission, stream rendering, and clean exit; runtime policy and persistence are delegated to AgentManager/AgentRunner.

## 16. Implementation Steps

1. Replace Herd-backed TUI tests with AgentManager/AgentRunner/MockProvider tests covering mount, built-in Agent roster, prompt submission, event rendering, Agent switching, and persisted Ctrl+N creation → verify: `uv run --offline pytest tests/test_tui_app.py -k 'mount or prompt or switch or rendering or create'`
2. Rewire MiaApp construction and background prompt workers to use AgentManager and AgentRunner, unwrap AgentEventEnvelope, and render sanitized RunErrorEvent values → verify: `uv run --offline pytest tests/test_tui_app.py tests/test_agent_runtime.py -k 'tui or runner or envelope or error' && printf 'no new security findings in affected paths\n'`
3. Replace ManagedAgent/AgentState sidebar data with Agent values and keep existing visual layout, model command, target switching, transcript routing, and minimal persisted Agent creation → verify: `uv run --offline pytest tests/test_tui_app.py tests/test_cli_print_mode.py -k 'tui or agent or model'`
4. Remove dead TUI-only input code and Herd imports from the retained frontend while keeping Textual packaging and the `mia tui` entrypoint → verify: `! grep -RInE 'mia_agent\.(herd|profiles)|HerdManager|ManagedAgent|AgentState|MiaHerdApp' src/mia_cli/tui tests/test_tui_app.py && uv run --offline pytest tests/test_tui_app.py`
5. Run the retained TUI plus core regression checks and package smoke test → verify: `uv run --offline pytest tests/test_tui_app.py tests/test_agent_loop.py tests/test_delegation.py tests/test_plugins.py tests/test_sessions.py && uv run --offline mia tui --help && uv build --offline`

## 17. Acceptance Criteria

### Scenario SC-e06s02-P1-01: TUI lists real Agents

```gherkin
Given a temporary AgentManager with built-in and persisted Agents
When MiaApp mounts
Then the sidebar displays those Agent IDs and names
And no transient lead/coder worker is created
And the default target is a real Agent
```

### Scenario SC-e06s02-P1-02: Prompt uses canonical runtime

```gherkin
Given a selected Agent and an injected MockProvider
When the user submits a prompt in the TUI
Then AgentRunner receives the Agent ID
And AgentRunner yields the canonical event stream
And the matching transcript renders the user and assistant events
```

### Scenario SC-e06s02-P1-03: Existing visual stream remains usable

```gherkin
Given Agent events for thought text, assistant text, a Tool call, and a Tool result
When the TUI receives them
Then the existing thought drawer, assistant card, and Tool card render
And no TUI-specific Tool execution occurs
```

### Scenario SC-e06s02-P1-04: TUI errors are truthful

```gherkin
Given AgentRunner yields a sanitized RunErrorEvent
When the TUI receives it
Then the active transcript displays an error
And no false successful completion is shown
And the error does not expose secret values
```

### Scenario SC-e06s02-P2-05: Deferred UI scope is respected

```gherkin
Given the Agent-native TUI adapter is complete
When a contributor reviews the diff
Then existing layout and controls remain recognizable
And no new UI framework, worker state machine, or collaboration feature exists
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline mia tui --help` and confirm the command remains available.
2. Run `uv run --offline pytest tests/test_tui_app.py` and confirm mount, prompt, switching, persisted Agent creation, and event rendering pass.
3. Inspect TUI imports and confirm only AgentManager, AgentRunner, Agent, AgentEvent, and presentation modules are used.
4. Run `uv build --offline` and confirm the Textual frontend remains in the wheel.

## 19. Risks and Mitigations

- **Accidental TUI redesign:** keep the story limited to imports, identity data, and stream routing.
- **Lost live status metrics:** derive only what existing Agent events provide; do not create a new state model.
- **Invalid `@agent` target:** show an error rather than silently creating arbitrary identities.
- **Second runtime path:** test that TUI workers call AgentRunner and never AgentHarness/factory directly.
- **Concurrent turns:** retain Textual's existing worker behavior but rely on AgentRunner/Session contracts; deeper concurrency is separate work.

## 20. Definition of Done and Slopcheck

- `mia tui` remains available and Textual remains a dependency.
- TUI source and tests contain no Herd/Profile/Mode imports or aliases.
- AgentManager and AgentRunner own identity, execution, Tools, policy, and Sessions.
- Existing visual tests pass with MockProvider.
- All tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Textual (already installed) — retained existing frontend only.
- `[OK]` Existing AgentManager, AgentRunner, MockProvider, and AgentEvent contracts — no new backend.
- No new package, event bus, or worker framework.

### Red-Flag Check

Rejected deleting the TUI, porting Herd's state machine, adding a TUI-specific harness, preserving transient worker identities, or using direct Tool calls from widgets.
