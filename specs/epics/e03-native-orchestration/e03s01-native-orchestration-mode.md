# e03s01 — Native Orchestration Mode Vertical Slice

## 1. Identity

- **Story ID:** e03s01
- **Epic:** e03 — Native Orchestration Runtime
- **Type:** feat
- **Risk:** P0
- **Context:** domain and infrastructure
- **BCPs:** 5
- **Status:** passing

## 2. User Story

As a Mia user, I want every prompt to run through a selected orchestration mode so that simple work keeps today's fast single-agent behavior while explicit workflows can coordinate specialized Mia agents without a separate Herdr process.

## 3. Context

Mia currently constructs `AgentHarness` independently in the interactive REPL and headless CLI. `AgentProfile` effectively acts both as a role description and the top-level user execution selector. The agreed product model separates those responsibilities: Mode composes; Profile configures; Workflow coordinates; Agent executes; Plugin extends. This story proves that model vertically while preserving the existing Pi/Tau-style experience.

## 4. Problem

There is no active, headless orchestration entry point shared by `mia` and `mia run`. Adding specialized agents directly to either CLI would duplicate provider, tool, middleware, session, cancellation, and event logic. Reusing the experimental `src/mia_agent/herd/` path would make a legacy terminal feature the backend architecture.

## 5. Goal

Route both active CLI paths through one native mode runtime. Preserve all current behavior in the default one-node mode. Add one explicit research mode that runs a task-local architect specialist followed by a coordinator, with attributable events and durable session lineage.

## 6. Non-Goals

- Continuable children or follow-ups after restart.
- Persistent team rosters, mailboxes, task DAGs, or work stealing.
- Automatic selection of modes or workflows.
- User-installed mode/plugin discovery.
- Built-in memory.
- Full-screen or legacy Herd UI work.
- Parallel workflow execution.
- Refactoring the internal `AgentHarness` turn loop.

## 7. Stakeholders

- Mia terminal users who require unchanged default behavior.
- Mode and profile authors who need separate composition and role concepts.
- Future plugin authors who need a stable headless runtime rather than UI coupling.
- Maintainers responsible for session integrity, tool permissions, and deterministic tests.

## 8. Dependencies

- `src/mia_agent/harness.py`
- `src/mia_agent/events.py`
- `src/mia_agent/profiles/`
- `src/mia_agent/session/`
- `src/mia_cli/main.py`
- `src/mia_cli/repl.py`
- `src/mia_cli/renderers/rich_stream.py`
- Existing Pydantic, pytest, Ruff, and Mypy packages.

## 9. Assumptions

- Mode selection is explicit in this slice.
- `single` is the default mode and uses the currently selected profile as coordinator.
- `research` uses the built-in `architect` profile for its specialist and the user's selected profile for coordinator synthesis.
- Specialist and coordinator execute sequentially.
- A specialist is task-local: its session remains on disk, but the runtime does not retain a live agent or follow-up address.
- The legacy Herd modules can continue importing `AgentHarness`, but they neither define nor participate in the new runtime.

## 10. Constraints

- Python 3.12+, strict Mypy, Ruff formatting, offline verification.
- No new runtime package; PyYAML is development-only for repository planning gates.
- `AgentHarness` remains a one-agent executor with no UI dependency.
- `AgentProfile` remains a one-role configuration.
- Tool allowlists and middleware are resolved independently for every agent instance.
- Session writes remain append-only.
- Existing interactive and headless command behavior remains compatible unless explicitly modified below.
- Existing uncommitted working-tree changes must not be overwritten.

## 11. Domain Model

- **Mode:** named composition containing one coordinator profile policy and one Workflow.
- **Profile:** existing role configuration consumed by agent construction.
- **Workflow:** validated ordered stages; e03s01 supports either one coordinator stage or one specialist stage followed by coordinator synthesis.
- **Agent instance:** one `AgentHarness`, session, identity, and profile assignment.
- **Plugin:** documented extension concept only; no plugin runtime in e03s01.
- **Orchestration event:** immutable envelope identifying mode, workflow run, task, agent, and profile around one existing `AgentEvent`.
- **One-shot specialist:** task-local child agent whose final assistant content becomes coordinator input.

## 12. Requirements

### ADDED: Every prompt enters a Mode runtime

All prompts submitted by the default interactive `mia` command and `mia run` MUST execute through the same headless mode runtime before reaching any `AgentHarness`.

### MODIFIED: CLI execution composition

**Before:** `MiaREPL._init_harness` and `src/mia_cli/main.py::_run_agent_loop` independently resolve providers, tools, middleware, sessions, compaction, and construct `AgentHarness` directly.

**After:** one shared agent runtime factory performs that construction, and both CLI paths obtain execution through the mode runtime.

### MODIFIED: Profile responsibility

**Before:** the active profile is the user-facing top-level execution selector and directly determines the only running harness.

**After:** a profile configures one role; the selected mode composes one or more profile-backed agent instances. `--profile` and `/profile` continue selecting the coordinator role profile for compatibility.

### ADDED: Default one-node mode

The built-in `single` mode MUST stream one coordinator agent and preserve existing event order, tools, middleware, profile permissions, model selection, token/cost accounting, session resume, and tree navigation.

### ADDED: Deterministic research workflow

The built-in `research` mode MUST execute one task-local specialist with the `architect` profile, collect its final assistant output, then execute the selected coordinator profile with the original request and specialist result. It MUST NOT run stages in parallel.

### ADDED: Explicit mode selection

`mia run --mode <name>` and interactive `/mode [name]` MUST select validated modes. `/mode` without a name MUST show the current and available modes. Unknown names MUST fail loud with available choices.

### ADDED: Attributable event stream

Every event emitted by the mode runtime MUST identify `mode`, `run_id`, `task_id`, `agent_id`, and `profile`, while retaining the original typed `AgentEvent` as its payload. Single and research modes MUST use the same envelope contract.

### ADDED: One-shot child lineage

The specialist MUST use a separate append-only session. Its durable metadata MUST identify the parent root session, workflow run, task, mode, and profile without making the child continuable.

### ADDED: Failure and cancellation semantics

A stage error or cancellation MUST emit a typed terminal orchestration error, stop later workflow stages, and leave already-written session records readable. Cancellation MUST not be translated into successful completion.

## 13. Non-Functional Requirements

- **Compatibility:** existing focused tests for `AgentHarness`, profiles, sessions, headless CLI, REPL, and renderer remain green.
- **Determinism:** MockProvider scripts prove exact stage order and handoff content offline.
- **Security:** every agent's tools are filtered by its own profile; every tool execution uses the existing middleware pipeline.
- **Observability:** no child output is unattributed in the runtime event stream.
- **Maintainability:** CLI modules do not implement workflow scheduling.
- **Performance:** `single` mode adds no extra model request.

## 14. Contracts

### Existing contracts preserved

- `AgentHarness.prompt(text) -> AsyncIterator[AgentEvent]` remains unchanged.
- `AgentHarness` remains headless and executes tools through `ToolPipeline` when configured.
- `ProfileManager` continues built-in/custom profile discovery and tool filtering.
- `JsonlSessionStore` remains append-only and `SessionTree` remains the active-path authority.

### New contracts

- Mode definitions fail validation on blank names, missing coordinator profile, invalid stage order, or unknown referenced profiles.
- Mode runtime prompt execution yields only attributable orchestration envelopes.
- Root and child agent construction is delegated to one factory.
- The renderer unwraps orchestration envelopes but renders the inner `AgentEvent` with current visual behavior.

## 15. Reason for Depth

- **Mode runtime:** Required because both active CLIs and future adapters need one place to own workflow order, cancellation, lineage, and event attribution without teaching `AgentHarness` about multiple agents.
- **Agent runtime factory:** Required because provider, profile, tools, middleware, sessions, compaction, and resume assembly is currently duplicated in two production composition roots and must remain security-consistent.
- **Mode and Workflow definitions:** Required because user-selected composition and ordered specialist stages must be validated as data independently from reusable role profiles.
- **Orchestration event envelope:** Required because multiple agent streams cannot be rendered, persisted, or tested safely when origin identity is implicit.

All e03s01 orchestration types SHOULD remain in one cohesive `src/mia_agent/orchestration.py` module until size or independent reuse proves a split necessary.

## 16. Implementation Steps

1. Add failing contract tests and validated Mode, Workflow, stage, and orchestration-envelope models in one orchestration module → verify: `uv run --offline pytest tests/test_orchestration.py -k 'models or envelope'`
2. Add the shared agent runtime factory with profile-specific tools, middleware, provider injection, session resume, compaction, and lineage metadata → verify: `uv run --offline pytest tests/test_orchestration.py -k factory && uv run --offline pytest tests/test_e2e_scenarios.py -k security_guardrail && printf 'no new security findings in affected paths\n'`
3. Implement default `single` mode and route both CLI execution paths through it without changing inner `AgentEvent` order or session behavior → verify: `uv run --offline pytest tests/test_orchestration.py -k single && uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py`
4. Implement sequential research specialist-to-coordinator execution, child lineage, result handoff, fail-fast errors, and cancellation → verify: `uv run --offline pytest tests/test_orchestration.py -k 'research or lineage or failure or cancellation' && uv run --offline pytest tests/test_profiles.py -k architect && printf 'no new security findings in affected paths\n'`
5. Add explicit `--mode` and `/mode` selection and teach Rich rendering to display agent attribution while unwrapping the existing event payload → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -k mode`
6. Synchronize Mia's glossary and technical architecture with the implemented runtime and deferred capabilities → verify: `grep -q 'Mode composes; Profile configures; Workflow coordinates; Agent executes; Plugin extends' specs/product/GLOSSARY_LATEST.yaml && grep -q 'Mode composes; Profile configures; Workflow coordinates; Agent executes; Plugin extends' specs/tech-architecture/tech-stack.md`
7. Run all project quality gates and record verification evidence before changing task status from failing → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest`

## 17. Acceptance Criteria

### Scenario SC-e03s01-P0-01: Default mode preserves one-agent behavior

```gherkin
Given Mia is configured with the coding profile and single mode
When the user submits a prompt through either the interactive or headless CLI
Then exactly one AgentHarness executes
And its inner AgentEvent order matches direct AgentHarness execution
And no additional model request is made
And existing tools, middleware, tokens, costs, and session behavior remain intact
```

### Scenario SC-e03s01-P0-02: Research mode delegates deterministically

```gherkin
Given Mia is configured with research mode
And deterministic provider responses exist for architect and coordinator stages
When the user submits a research prompt
Then the architect specialist runs before the coordinator
And the coordinator receives the original prompt and specialist result
And each stage uses its assigned profile and separate session
And every emitted event identifies its originating mode, run, task, agent, and profile
```

### Scenario SC-e03s01-P0-03: Child lineage is durable

```gherkin
Given a research workflow completes
When its child session JSONL is reloaded after the runtime is gone
Then metadata identifies the root session, run, task, mode, and specialist profile
And its transcript remains readable
And no follow-up operation is exposed for that child
```

### Scenario SC-e03s01-P0-04: Stage failure stops the workflow

```gherkin
Given the research specialist fails or is cancelled
When the mode runtime observes the terminal failure
Then coordinator synthesis does not start
And a typed terminal error event is emitted
And persisted root and child session records remain readable
```

### Scenario SC-e03s01-P1-05: Invalid mode fails loud

```gherkin
Given the user selects an unknown mode
When Mia validates the selection
Then execution does not start
And the error names the unknown mode and available choices
```

### Scenario SC-e03s01-P1-06: Profile permissions remain agent-local

```gherkin
Given the research specialist uses architect and the coordinator uses coding
When their harnesses are constructed
Then the specialist sees only architect-allowed tools
And the coordinator sees coding-allowed tools
And all visible tools execute through ToolPipeline
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_orchestration.py` and confirm model validation, one-node compatibility, research order, lineage, failures, and cancellation pass.
2. Run `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py` and confirm `/mode`, `--mode`, session resume, rendering, and current commands pass.
3. Run `uv run --offline pytest tests/test_agent_loop.py tests/test_profiles.py tests/test_sessions.py tests/test_e2e_scenarios.py` and confirm core execution, permissions, persistence, branching, compaction, and security remain compatible.
4. Run `uv run --offline ruff format --check .` and `uv run --offline ruff check .`.
5. Run `uv run --offline mypy src`.
6. Run `uv run --offline pytest`.
7. Inspect one deterministic research run and confirm specialist events are visibly attributed before coordinator events and both session logs are readable.

## 19. Risks and Mitigations

- **Event-protocol migration:** wrapping events can break renderers or token accounting. Mitigation: preserve the inner `AgentEvent` unchanged and test both adapters before enabling research mode.
- **Security-policy drift:** centralized construction could accidentally broaden tools. Mitigation: factory tests assert profile-local tool schemas and existing security E2E tests remain required.
- **Session collision or broken resume:** child naming/metadata could interfere with root sessions. Mitigation: separate session identities, append-only lineage metadata, and reload tests.
- **Coordinator prompt pollution:** specialist handoff could become indistinguishable from user text. Mitigation: use a deterministic internal handoff frame and assert exact coordinator input in MockProvider tests.
- **Legacy conflict:** old Herd imports may suggest two orchestration roots. Mitigation: new active paths import only the native runtime; no legacy code is reused.
- **Scope expansion:** continuable teams, plugins, memory, parallelism, and UI can turn one story into a platform rewrite. Mitigation: enforce §6 exclusions.

## 20. Definition of Done and Slopcheck

- All seven tasks in `e03s01-tasks.yaml` have verification evidence and are changed from `failing` to `passing` only after their commands exit zero.
- All six Gherkin scenarios are covered by deterministic automated tests.
- `specs/verifications/e03s01-verify.yaml` records commands and outcomes.
- Impact and architecture documents match implementation.
- No unresolved P0/P1 defect or security finding remains in affected paths.
- Plan consistency gate passes before implementation and again before handoff.

### Slopcheck

- `[OK]` Python standard library — IDs, paths, cancellation primitives, and sequential control flow.
- `[OK]` Pydantic (already installed) — validation for mode/workflow/event data.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic async contract tests.
- `[OK]` existing Rich, prompt_toolkit, Typer, HTTPX, and AnyIO dependencies — compatibility only.
- `[OK]` PyYAML (development only) — required by the restored repository-standard planning consistency, timing, and status scripts; it is not shipped as a Mia runtime dependency.
- No new runtime package is proposed.

### Red-Flag Check

Caught and rejected these rationalizations: reusing legacy Herd because it already exists; merging Mode into AgentProfile to avoid a new term; implementing durable teams before proving one-shot flow; and adding a plugin framework before a real plugin contract is needed.
