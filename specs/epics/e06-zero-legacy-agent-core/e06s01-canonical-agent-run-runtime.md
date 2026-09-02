# e06s01 — Canonical Agent Run Runtime

## 1. Identity

- **Story ID:** e06s01
- **Epic:** e06 — Zero-Legacy Agent Core
- **Type:** refactor
- **Risk:** P0
- **Context:** runtime, identity, events, Sessions, access, Plugins, and Delegation
- **BCPs:** 8
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia contributor, I want one Agent-only headless runtime seam so that every frontend executes the same trusted Agent, Tool, Plugin, Session, and access path.

## 3. Context

The released runtime already has `AgentRunner` and `AgentRuntimeFactory`, but their contracts still share files with Mode/Workflow models and the factory still contains a Profile branch. This story isolates the durable Agent Run contracts and makes direct Agent execution the only canonical composition path before the remaining legacy surfaces are removed.

## 4. Problem

A mixed runtime contract permits new callers to depend on obsolete identity concepts and makes it unclear which path enforces Plugin, access, Session, attribution, and cancellation rules. The duplicate branch also allows CLI, REPL, TUI, and Delegation behavior to drift.

## 5. Goal

Provide clean `RuntimeIdentity`, `AgentEventEnvelope`, `RunErrorEvent`, and `AgentRuntime` contracts; make the factory resolve one Agent from `AgentManager`; keep the private Research Agent sequence and bounded Delegation behavior; and preserve existing Agent/Plugin/access/Session semantics.

## 6. Non-Goals

- Removing CLI aliases, Profile files, Herd, or Textual code; e06s03 and e06s02 handle those after this seam exists.
- Changing `AgentHarness` turn semantics, provider contracts, middleware behavior, redaction, or Plugin lifecycle rules.
- Adding a public workflow graph, scheduler, generic strategy registry, or new collaboration protocol.
- Redesigning the Textual UI.

## 7. Stakeholders

- Agent and runtime contributors.
- CLI, REPL, and TUI adapter maintainers.
- Delegation and Plugin maintainers.
- Users relying on Session continuity, access policy, and truthful outcomes.

## 8. Dependencies

- `Agent`, `AgentManager`, `AgentHarness`, `AgentRunner`, `AgentRuntimeFactory`, `DelegationService`, Plugins, middleware, and Session packages.
- e04/e05 behavior and current focused tests.
- Existing Pydantic, pytest, Ruff, Mypy, and MockProvider dependencies.

## 9. Assumptions

- `AgentRunner.prompt()` remains the public headless prompt entry.
- One prompt creates one Run identity; a Session may span Runs.
- The Research Agent's architect-then-synthesis sequence remains private runner logic.
- Runtime construction changes affect later Runs, not an active Turn.
- Old mixed files may remain temporarily during this story only so dependent cleanup can land in e06s03; no new caller may import them.

## 10. Constraints

- Runtime modules remain independent from Rich, Textual, Typer, and prompt_toolkit.
- Agent, Run, Task, and Session attribution is validated and never blank.
- Every visible Tool still uses the existing capability filter and middleware pipeline.
- Plugin activation remains fail-closed and the complete effect map is built before access middleware.
- Session writes remain append-only and identity metadata remains sanitized.
- No new runtime dependency or generic compatibility abstraction.

## 11. Domain Model

- **Agent:** durable configured identity selected by a Run.
- **Run:** one prompt-scoped execution of one Agent.
- **Runtime Identity:** immutable Run/Task/Agent/Session attribution with optional parent Session.
- **Agent Event Envelope:** outer event carrying canonical attribution and one unchanged inner Agent event.
- **Run Error:** sanitized terminal failure/cancellation event for a Run operation.
- **Agent Runtime:** constructed AgentHarness, identity, Session store, and resolved Agent.

## 12. Requirements

### MODIFIED: Runtime composition

**Before:** `AgentRuntimeFactory` chooses between a Profile-backed compatibility branch and an Agent branch, and callers can enter through `ModeRuntime`.

**After:** `AgentRuntimeFactory` resolves one Agent from `AgentManager` and composes provider, Tools, Plugins, middleware, Session, and harness state for that Agent. `AgentRunner` is the canonical prompt entry.

### MODIFIED: Runtime identity

**Before:** runtime identity includes `mode` and optional `profile` fields.

**After:** runtime identity contains only `run_id`, `task_id`, `agent_id`, `session_id`, and optional `parent_session_id`; each field is validated as a non-blank identity.

### RENAMED: Event envelope

**Before:** `OrchestrationEventEnvelope` and `OrchestrationErrorEvent` expose historical orchestration names and mode/profile fields.

**After:** `AgentEventEnvelope` and `RunErrorEvent` expose Agent-centric names, canonical identity, and sanitized terminal errors without mode/profile fields.

### MODIFIED: Research execution

**Before:** Research composition is described and tested as a selected Mode/Workflow.

**After:** the built-in Research Agent privately runs the existing sequential specialist-and-synthesis behavior through the same Agent-only factory and event contracts.

### MODIFIED: Delegation integration

**Before:** Delegation imports mixed orchestration contracts.

**After:** Delegation creates child Agent Runtimes with the canonical runtime contracts and preserves bounded timeout, access intersection, lineage, cancellation, and truthful outcomes.

### ADDED: No second canonical runtime

All supported runtime callers MUST use AgentRunner/AgentRuntimeFactory; this story adds no alternate provider, Tool, Session, or middleware composition root.

## 13. Non-Functional Requirements

- **Security:** no access expansion, middleware bypass, secret leakage, or un-attributed Tool execution.
- **Durability:** append-only Session behavior and identity persistence remain intact.
- **Compatibility:** inner AgentEvent discriminators and Plugin-free Tool behavior remain unchanged.
- **Determinism:** MockProvider proves event order, Research handoff, and failure/cancellation offline.
- **Maintainability:** historical names do not appear in the canonical runtime import path.

## 14. Contracts

### Existing contracts preserved

- `AgentHarness.prompt(text) -> AsyncIterator[AgentEvent]`.
- AgentManager built-in/native resolution, Tool filtering, and Agent-owned Session paths as finalized by e06s03.
- Plugin activation, Tool attribution, Delegation bounds, access policy, redaction, and Session tree behavior.
- Provider injection and `AgentRunner.last_runtime` behavior.

### New contracts

- `RuntimeIdentity` has no Mode/Profile fields.
- `AgentEventEnvelope` retains one unchanged AgentEvent and canonical identity.
- `RunErrorEvent` sanitizes error text and distinguishes cancellation.
- `AgentRuntime` contains no Profile object.
- Factory construction accepts only Agent identity and one Agent-owned Session location.

## 15. Reason for Depth and Zoom-Out

- **Dedicated runtime contract module:** required because the existing module mixes removable legacy models with contracts used by every runtime caller; separating them lets the old file be deleted without weakening boundaries.
- **AgentEventEnvelope/RunErrorEvent:** required because multiple frontends need attributable typed streams and the old names encode a removed public architecture.
- **No new orchestration abstraction:** private Research sequencing stays in `AgentRunner`; a strategy registry would add depth without a second current strategy requirement.

`AgentRuntimeFactory` exists to build one complete Agent execution boundary. Its callers are AgentRunner, DelegationService, the CLI/REPL adapters, the retained TUI adapter, Plugins, and runtime tests. Its contracts are Agent-owned provider/Tool/middleware/Session composition, complete access effect maps, immutable Run attribution, append-only Session restoration, and truthful failures.

## 16. Implementation Steps

1. Add failing Agent-only runtime contract tests for identity validation, envelope payload preservation, sanitized Run errors, and absence of Mode/Profile fields → verify: `uv run --offline pytest tests/test_agent_runtime.py -k 'identity or envelope or error or no_mode or no_profile'`
2. Extract the canonical runtime models and event constructors into `src/mia_agent/runtime_models.py` and `src/mia_agent/runtime_events.py`, and update AgentRunner/Delegation imports without changing inner AgentEvent payloads → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_delegation.py -k 'identity or envelope or lineage or cancellation'`
3. Make AgentRuntimeFactory resolve only Agent identity, Agent-owned Session paths, Plugins, capability filtering, effect maps, access middleware, and harness state; remove its Profile branch and fixed legacy namespace → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_plugins.py tests/test_agents.py tests/test_access_policy.py -k 'factory or plugin or session or access or agent_only' && printf 'no new security findings in affected paths\n'`
4. Route AgentRunner's normal and private Research Agent journeys through the new contracts and preserve Delegation child runtime behavior, event ordering, cancellation, and error sanitization → verify: `uv run --offline pytest tests/test_agent_runtime.py tests/test_delegation.py tests/test_agent_loop.py -k 'runner or research or specialist or delegation or failure or cancellation' && printf 'no new security findings in affected paths\n'`
5. Update direct runtime consumers to import canonical modules and prove Plugin, access, Session, and provider regressions remain green before legacy file deletion → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agent_templates.py tests/test_sessions.py tests/test_delegation.py tests/test_agent_loop.py tests/test_e2e_scenarios.py && printf 'no new security findings in affected paths\n'`
6. Run the story quality checks and record the contract evidence → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_delegation.py tests/test_plugins.py tests/test_agent_templates.py tests/test_sessions.py && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e06s01-P0-01: Agent-only runtime identity

```gherkin
Given a named Agent and a Session
When AgentRunner starts a Run
Then the Runtime Identity contains Agent, Run, Task, and Session attribution
And it contains no Mode or Profile field
And a second prompt gets a new Run ID while retaining the selected Agent and Session
```

### Scenario SC-e06s01-P0-02: One composition root

```gherkin
Given a direct prompt, a delegated Task, or a Plugin-enabled Agent
When Mia constructs the runtime
Then AgentRuntimeFactory resolves the Agent and builds provider, Tools, access middleware, Plugins, and Session together
And no caller constructs a second harness composition path
```

### Scenario SC-e06s01-P0-03: Research remains private Agent behavior

```gherkin
Given the built-in Research Agent and deterministic specialist/coordinator responses
When the user runs the Research Agent
Then the architect specialist runs before synthesis
And events identify Agents, Runs, Tasks, and Sessions
And no public Mode or Workflow object is required
```

### Scenario SC-e06s01-P0-04: Failure and cancellation remain truthful

```gherkin
Given a provider failure, Tool failure, timeout, or cancellation
When the runtime reports the outcome
Then the error is sanitized and attributable
And later Research work does not start after specialist failure
And Mia never emits successful completion for the failed Run
```

### Scenario SC-e06s01-P1-05: Existing boundaries remain intact

```gherkin
Given a Plugin-enabled, read-only, approval-required, or delegated Agent
When its runtime is built
Then capability filtering, Plugin activation, access policy, security, audit, redaction, and Session persistence remain enforced
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_agent_runtime.py` and confirm canonical identity and envelope tests pass.
2. Run `uv run --offline pytest tests/test_plugins.py tests/test_access_policy.py tests/test_sessions.py tests/test_delegation.py` and confirm existing boundaries remain green.
3. Run the Research Agent tests and confirm specialist events precede synthesis events.
4. Inspect the runtime modules and confirm no canonical import references a Mode/Profile type.
5. Run Ruff, Mypy, and the focused test set from Step 6.

## 19. Risks and Mitigations

- **Hidden legacy importer:** search symbols and run import tests before deleting mixed modules.
- **Attribution regression:** preserve inner AgentEvent objects and assert all required identity fields.
- **Access drift:** reuse the existing factory filtering/effect logic and rerun Plugin/access security tests.
- **Session drift:** assert restored messages and appended identity metadata use the Agent-owned Session path.
- **Research regression:** retain deterministic specialist/coordinator tests before removing public composition types.

## 20. Definition of Done and Slopcheck

- Canonical runtime models and constructors have no Mode/Profile fields or names.
- AgentRunner, AgentRuntimeFactory, and Delegation use the Agent-only contracts.
- Research, Plugin, access, Session, and failure/cancellation scenarios pass.
- All tasks remain `failing` until their verify commands pass during implementation.
- No new dependency is proposed.

### Slopcheck

- `[OK]` Existing Pydantic, Python standard library, pytest, and MockProvider — required by current runtime boundaries.
- `[OK]` No new package, loader, event bus, or strategy framework.

### Red-Flag Check

Rejected keeping the mixed orchestration module as a public facade, adding a second TUI-specific runtime, translating old Profile state in the factory, or replacing the existing private Research behavior with a speculative generalized workflow engine.
