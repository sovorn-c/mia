# e04s04 — Agent-First Compatibility Migration

## 1. Identity

- **Story ID:** e04s04
- **Epic:** e04 — Agent-Centric Foundation
- **Type:** refactor
- **Risk:** P0
- **Context:** architecture, CLI, runtime events, compatibility, and documentation
- **BCPs:** 5
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As an existing Mia user, I want current single, research, coding, architect, code-mode, minimal, Session, and Tool journeys to continue through Agent-first commands so that the product can adopt one identity model without losing useful behavior or data.

## 3. Context

The first three e04 stories establish Agent identity, state/access boundaries, and direct Delegation. The current product still presents Profile and Mode in CLI flags, slash commands, help, event envelopes, runtime identity, tests, and documentation. Research composition remains the only first-party behavior requiring a private specialist/coordinator sequence. This story moves preferred surfaces to Agent while preserving legacy inputs as visible compatibility adapters for v0.4.

## 4. Problem

Leaving old surfaces unchanged would create dual product language and encourage new code to depend on Profile/Mode. Removing them abruptly would break commands, custom Profile data, saved Sessions, tests, and integrations. Current interactive runtime identity also reuses one Run ID derived from the Session, which conflicts with correct per-prompt attribution during the migration.

## 5. Goal

Make Agent the canonical CLI, runtime, event, and documentation concept; preserve existing named configurations as built-in or compatibility Agents; keep single and research journeys working through one Agent runner; emit prompt-scoped Run attribution; and retain `--profile`, `/profile`, `profile`, `--mode`, and ModeRuntime imports as deprecated adapters with actionable warnings and no destructive data rewrite.

## 6. Non-Goals

- Removing every compatibility alias in v0.4.
- Rewriting archived plans or immutable scope snapshots.
- General Plugin SDK, YAML Agent packages, marketplace, or remote distribution.
- New research algorithms, parallel specialists, or recursive Delegation.
- TUI redesign beyond labels needed for semantic parity.
- Session storage migration beyond the additive/fallback rules from e04s01/e04s02.
- Public lifecycle state-machine expansion beyond truthful Task/Run attribution required here.

## 7. Stakeholders

- Existing CLI users and scripts using Profile or Mode flags.
- Users with built-in/custom Profiles and saved Session JSONL.
- New users who should see Agent-first language only.
- Runtime/event consumers and renderer maintainers.
- Documentation, test, release, and migration maintainers.

## 8. Dependencies

- e04s01 canonical Agent APIs and compatibility Profile projection.
- e04s02 access, Agent state, and credential boundary.
- e04s03 direct Delegation and terminal Task outcomes.
- Existing `ModeRuntime`, `ModeCatalog`, `AgentRuntimeFactory`, `RuntimeIdentity`, `OrchestrationEventEnvelope`, REPL, Typer CLI, renderers, and Session entries.
- Existing e01–e03 tests and current release/spec documentation.

## 9. Assumptions

- Compatibility aliases remain supported for the v0.4 release and emit deprecation guidance toward Agent commands.
- Canonical commands never require users to choose Mode or Profile.
- Existing built-in configurations become Agents with stable IDs: `coding`, `architect`, `code-mode`, and `minimal`; legacy `code_mode` is accepted as an alias.
- A built-in `research` Agent owns the private specialist/coordinator strategy; Workflow remains implementation detail.
- Legacy `--mode research` retains its selected legacy Profile as coordinator through the compatibility adapter.
- Each submitted prompt gets a fresh Run ID while the selected Session remains stable across prompts.
- Canonical event consumers use Agent/Run/Task/Session fields; legacy mode/profile fields remain optional compatibility data for one release.
- Warnings go to stderr or rendered notices without corrupting machine-readable primary output.

## 10. Constraints

- No destructive migration or implicit rewrite of Profile/Session files.
- Agent-first runtime path is the source of truth; legacy adapters translate into it and may not duplicate execution logic.
- Core modules do not import Typer, Rich, Textual, or prompt_toolkit.
- One Run ID per prompt, unique within resumed Sessions.
- Existing event ordering and inner `AgentEvent` payloads remain compatible.
- Research remains sequential and bounded to one specialist plus one coordinator.
- Full-access and other access semantics remain unchanged by compatibility flags.
- Archived `docs/initial_plan/`, snapshots, and completed epic history retain historical terminology where clearly marked.
- No new runtime dependency.

## 11. Domain Model

- **Agent Runner:** canonical headless entry that executes one selected Agent for one prompt and emits attributed envelopes.
- **Run Identity:** prompt-scoped Run/Task/Agent/Session attribution, with optional parent and caller fields.
- **Agent Event Envelope:** canonical outer event contract carrying Agent, Run, Task, Session, and inner AgentEvent data.
- **Research Agent:** first-party Agent whose private runtime strategy obtains specialist findings and produces a final response.
- **Compatibility Adapter:** translation from legacy Profile/Mode command or import into Agent selection/private strategy; not a second runtime.

## 12. Requirements

### MODIFIED: Canonical runtime entry

**Before:** `ModeRuntime.prompt()` accepts `mode_name` and `profile_name`, resolves a Mode/Workflow, and emits `OrchestrationEventEnvelope` with mode/profile fields.

**After:** AgentRunner accepts an Agent ID and emits canonical Agent/Run/Task/Session attribution. Existing ModeRuntime calls translate into AgentRunner arguments and execute the same underlying path.

### MODIFIED: Prompt-scoped Run identity

**Before:** interactive single mode may reuse `run_id=f"run_{session_id}"` across prompts and a long-lived runtime identity.

**After:** every submitted prompt receives a unique Run ID while Session ID remains stable. Resuming a Session starts new prompt-scoped Runs without mutating prior identity metadata.

### MODIFIED: Event envelope

**Before:** mode and profile are required identity fields, while Session attribution is indirect.

**After:** Agent ID, Run ID, Task ID, and Session ID are required canonical fields. Caller/parent attribution is included when relevant. Optional mode/profile compatibility fields may be populated only for legacy adapter calls.

### MODIFIED: Single journey

**Before:** Mode `single` wraps one coordinator Profile.

**After:** selecting any normal Agent directly executes one Agent Run. Legacy `single` maps to the selected Agent without a public Workflow object.

### MODIFIED: Research journey

**Before:** Mode `research` hard-codes architect specialist and selected Profile coordinator stages.

**After:** the built-in Research Agent owns the private sequential strategy and uses core Task/Delegation attribution. Canonical users select Agent `research`; legacy `--mode research --profile X` maps to the same strategy with Agent X as coordinator for compatibility.

### MODIFIED: Preferred CLI and REPL language

**Before:** `--profile`, `/profile`, `profile`, `--mode`, and Mode-oriented help are primary.

**After:** `--agent`, `/agent`, and `agent` are primary; normal execution has no Mode option. Legacy commands remain aliases that emit clear deprecation guidance and preserve behavior.

### MODIFIED: Built-in configuration continuity

**Before:** `coding`, `architect`, `code_mode`, and `minimal` are built-in Profiles.

**After:** those configurations resolve as built-in Agents, with canonical ID `code-mode` and legacy alias `code_mode`. Tool allowlists, prompts, model defaults, step limits, and compaction behavior remain equivalent unless the new access policy intentionally restricts them.

### MODIFIED: Session/runtime metadata

**Before:** new entries use the `orchestration` namespace and Profile/Mode identity.

**After:** new entries use canonical Agent/Run/Task/Session metadata and read old orchestration entries without rewriting them. Parent/child and active-path invariants remain unchanged.

### MODIFIED: Product documentation

**Before:** README/help/module descriptions call Mia a coding agent and teach Profile/Mode as primary.

**After:** current docs present Mia as a general-purpose local Agent core with default Mia Agent, named Agents, access levels, Sessions, and direct Delegation. Coding and Research are first-party Agents/capabilities. Historical files remain labeled historical rather than rewritten.

## 13. Non-Functional Requirements

- **Compatibility:** legacy commands, imports, Profile files, and Sessions remain usable in v0.4.
- **Clarity:** canonical help and docs use Agent consistently and do not require Mode/Workflow knowledge.
- **Attribution:** every prompt and delegated Task has unique Run identity and direct Session/Agent attribution.
- **Security:** adapters cannot bypass access, capability, credential, or permanent security controls.
- **Maintainability:** one execution implementation serves canonical and legacy callers.
- **Testability:** compatibility mappings and warnings are deterministic and offline.

## 14. Contracts

### Existing contracts preserved

- Inner `AgentEvent` types and streaming order.
- Provider/tool/session behavior for equivalent built-in configurations.
- Legacy Profile JSON and Session JSONL input.
- Legacy command acceptance for one compatibility release.
- Existing Python imports through thin aliases where documented.

### New contracts

- AgentRunner is the canonical headless prompt entry.
- Each prompt gets a unique Run ID independent of Session ID.
- Agent event envelopes require Agent/Run/Task/Session attribution.
- Canonical Research selection is Agent-based; its sequence is private implementation.
- Compatibility adapters warn and translate only; they do not own runtime logic.

## 15. Reason for Depth

- **AgentRunner:** Required because CLI, REPL, print mode, Delegation, and compatibility adapters need one canonical prompt execution seam after Mode ceases to be public architecture.
- **Agent event envelope and Run identity:** Required because Profile/Mode fields cannot represent durable Agent ownership or prompt-scoped Runs truthfully.
- **Compatibility adapter:** Required to preserve existing commands, files, Sessions, and imports without maintaining two runtime implementations.

Do not introduce a new frontend framework, generic strategy registry, Plugin loader, event bus, migration database, or alias framework.

## 16. Implementation Steps

1. Add failing canonical AgentRunner/envelope tests covering Agent/Run/Task/Session attribution, unique Run IDs per prompt, stable resumed Session IDs, and additive legacy metadata reads → verify: `uv run --offline pytest tests/test_orchestration.py tests/test_agents.py tests/test_sessions.py -k 'agent_runner or envelope or unique_run or resumed or legacy_metadata' && printf 'no new security findings in affected paths\n'`
2. Route single-Agent execution through AgentRunner and convert ModeRuntime/legacy identity classes into thin compatibility adapters or aliases with no duplicated provider/Tool/Session logic → verify: `uv run --offline pytest tests/test_orchestration.py -k 'single or agent_runner or compatib or mode_runtime' && printf 'no new security findings in affected paths\n'`
3. Move Research behavior behind the built-in Research Agent/private strategy and retain legacy research coordinator behavior through translation into the same execution path → verify: `uv run --offline pytest tests/test_orchestration.py tests/test_delegation.py -k 'research or specialist or coordinator or legacy_mode' && printf 'no new security findings in affected paths\n'`
4. Make `--agent`, `/agent`, and `mia agent` canonical across interactive and print paths; keep Profile/Mode inputs as warning aliases and preserve built-in configuration behavior → verify: `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py tests/test_profiles.py tests/test_agents.py -k 'agent or profile_alias or mode_alias or warning or builtin' && printf 'no new security findings in affected paths\n'`
5. Synchronize README, current specs, help text, module descriptions, and session inspection labels with approved Agent terminology while leaving archived history marked as historical → verify: `uv run --offline python - <<'PY'
from pathlib import Path
for path in [Path('README.md'), Path('src/mia_cli/main.py'), Path('src/mia_cli/repl.py')]:
    text = path.read_text()
    assert 'Agent' in text, path
print('agent terminology present')
PY`
6. Run all compatibility, runtime, Delegation, access, Session, CLI, and quality gates; document the v0.4 alias/removal boundary → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e04s04-P0-01: Canonical single-Agent execution

```gherkin
Given a selected named Agent and Session
When the user submits two prompts through the canonical Agent command
Then both prompts execute through AgentRunner
And each has a unique Run ID
And both retain the same Agent and Session attribution
```

### Scenario SC-e04s04-P0-02: Research is an Agent journey

```gherkin
Given the built-in Research Agent
When the user submits a research prompt with --agent research
Then a specialist Task runs before the final coordinator response
And events/results identify Agents, Tasks, Runs, and Sessions
And the user is not required to select a Mode or Workflow
```

### Scenario SC-e04s04-P0-03: Legacy research command remains functional

```gherkin
Given an existing command using --mode research and --profile coding
When it runs under v0.4
Then a deprecation warning identifies the Agent replacement
And the same private research execution path runs with coding as coordinator
And access/security behavior is unchanged
```

### Scenario SC-e04s04-P0-04: Built-in behavior continues

```gherkin
Given coding, architect, code_mode, and minimal legacy selections
When each is resolved through compatibility input
Then it maps to one canonical Agent
And prompts, Tool capability, model/limits, and Session behavior remain equivalent
And code_mode maps to canonical code-mode
```

### Scenario SC-e04s04-P0-05: Legacy data is read without rewrite

```gherkin
Given existing Profile JSON, orchestration metadata, and Session JSONL
When canonical Agent execution resumes that data
Then it remains readable
And new canonical metadata is appended only when needed
And the original files and entries are not rewritten or deleted
```

### Scenario SC-e04s04-P0-06: Compatibility cannot bypass policy

```gherkin
Given a legacy Profile or Mode flag selects an Agent
When a Tool or Delegation is attempted
Then canonical capability, access, approval, credential, and permanent security rules apply
And no adapter can broaden access
```

### Scenario SC-e04s04-P1-07: Canonical help teaches one identity

```gherkin
Given a new user runs mia --help, mia agent --help, or /help
When current guidance is rendered
Then Agent is the primary identity term
And default Mia, named Agents, access levels, Sessions, and Delegation are discoverable
And Profile/Mode appear only in migration guidance
```

### Scenario SC-e04s04-P1-08: Historical artifacts stay honest

```gherkin
Given archived plans and immutable snapshots contain Mode/Profile language
When current documentation is validated
Then active product/runtime docs use Agent terminology
And historical files remain unchanged or explicitly labeled historical
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_orchestration.py -k 'agent_runner or single or research or envelope or unique_run or compatib'`.
2. Run `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -k 'agent or profile or mode or warning or help'`.
3. Run `uv run --offline pytest tests/test_agents.py tests/test_profiles.py tests/test_sessions.py -k 'builtin or legacy or alias or metadata or resume'`.
4. Run `uv run --offline pytest tests/test_delegation.py tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'research or policy or escalation or security'`.
5. Run active-document terminology checks and verify archived/snapshot files are excluded from rewrite requirements.
6. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
7. Run `uv run --offline pytest`.

## 19. Risks and Mitigations

- **Dual runtime paths:** Legacy and canonical commands could diverge. Mitigation: adapters translate into AgentRunner and tests assert one provider/Tool/Session path.
- **Broken scripts:** Removing flags would break users. Mitigation: v0.4 aliases with actionable warnings and compatibility tests.
- **Incorrect Run attribution:** Session-derived IDs could persist. Mitigation: fresh UUID per prompt and multi-prompt/resume tests.
- **Research regression:** Private composition could lose selected coordinator semantics. Mitigation: canonical Research tests plus legacy mapping tests.
- **Data rewrite:** Metadata migration might mutate history. Mitigation: append/read compatibility only and fixture hash checks.
- **Terminology churn:** Archived docs could be incorrectly rewritten or active docs remain mixed. Mitigation: active/historical file classification and targeted checks.

## 20. Definition of Done and Slopcheck

- All tasks remain `failing` until their verify commands pass during implementation.
- All eight acceptance scenarios have deterministic automated coverage.
- Canonical CLI, REPL, runtime, event, and current docs use Agent-first language.
- Legacy commands/imports/data work through tested adapters and warnings.
- Every prompt has a unique Run ID with stable Agent/Session attribution.
- No unresolved P0/P1 compatibility or security finding remains.
- Full project format, lint, type, test, and build gates pass.

### Slopcheck

- `[OK]` Python standard library — UUID identity and warnings.
- `[OK]` existing Agent/runtime/event/CLI/session modules — migration seams.
- `[OK]` Typer, Rich, prompt_toolkit, Pydantic, pytest (already installed) — public surfaces and validation.
- No new runtime or development package is proposed.

### Red-Flag Check

Rejected these shortcuts: deleting old commands or data in v0.4; keeping Profile/Mode primary in help; maintaining two orchestration implementations; reintroducing public Workflow; reusing Session ID as Run ID; rewriting immutable history; and moving Agent execution into legacy Herd merely because it contains multi-agent code.
