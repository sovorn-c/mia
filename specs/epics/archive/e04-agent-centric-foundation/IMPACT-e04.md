# Impact Assessment — e04 Agent-Centric Foundation

## Target

The initiative changes shared identity, runtime, persistence, trust, and CLI seams:

- `src/mia_agent/profiles/model.py`: `AgentProfile`
- `src/mia_agent/profiles/manager.py`: `ProfileManager`, built-ins, Tool filtering, Session directory selection
- `src/mia_agent/orchestration.py`: `ModeRuntime`, `ModeCatalog`, `RuntimeIdentity`, `OrchestrationEventEnvelope`, `AgentRuntimeFactory`
- `src/mia_agent/harness.py`: terminal event classification and Tool execution outcomes used by Delegation
- `src/mia_middleware/pipeline.py` and `src/mia_middleware/security.py`: Tool policy boundary
- `src/mia_tools/base.py` and built-in Tools: side-effect metadata
- `src/mia_cli/main.py` and `src/mia_cli/repl.py`: Profile/Mode selection, runtime construction, Session resume, and help
- `src/mia_agent/session/`: Agent-owned Session lookup and additive metadata
- `src/mia_agent/auth/`: machine-global credential resolution by Agent reference

The intended target is one canonical Agent model/registry, one Agent runner, one access-policy enforcement path, and one synchronous one-hop Delegation service. Existing Profile/Mode inputs become compatibility adapters rather than parallel runtimes.

## Dependents (shared fan-in)

### Profile and identity

- `src/mia_agent/orchestration.py`: resolves Profiles for runtime construction and Mode validation.
- `src/mia_cli/main.py`: lists and selects Profiles in commands and print mode.
- `src/mia_cli/repl.py`: stores active Profile, builds runtime identity, switches Profile, lists Sessions by Profile.
- `src/mia_agent/herd/manager.py`: legacy Herd imports ProfileManager.
- `tests/test_profiles.py`: built-ins, JSON loading, filtering, persistence.
- `tests/test_orchestration.py`: Profile-backed Mode/Runtime contracts.
- `tests/test_cli_repl.py`: interactive Profile switching and Session behavior.
- `tests/test_cli_print_mode.py`: print-mode Profile/Mode selection.
- `tests/test_e2e_scenarios.py`: read-only/minimal Tool filtering.
- Additional Session/config tests instantiate ProfileManager through runtime factories.

Cymbal found 18 `ProfileManager` references across eight usage groups and five direct `AgentProfile` references.

### Runtime and orchestration

- `src/mia_cli/main.py`: `_run_agent_loop()` constructs ModeRuntime and consumes attributed envelopes.
- `src/mia_cli/repl.py`: `_init_harness()` constructs RuntimeIdentity and uses ModeRuntime for research.
- `tests/test_orchestration.py`: validates Mode models, single/research event attribution, failure, cancellation, and child Session metadata.
- `tests/test_cli_print_mode.py`: invokes print execution with Mode selection.
- `tests/test_cli_repl.py`: interactive mode and prompt behavior.

Cymbal found six `ModeRuntime`, eight `AgentRuntimeFactory`, and six `RuntimeIdentity` references. `orchestration.py` is imported by both CLI frontends and its dedicated test module.

### Tool and middleware policy

- `src/mia_agent/orchestration.py`: builds the Tool list and middleware pipeline.
- `src/mia_agent/harness.py`: invokes ToolPipeline and converts all exceptions to `ToolResultEvent.is_error`.
- `tests/test_middleware_pipeline.py`: middleware order, guard, audit, and cost behavior.
- `tests/test_e2e_scenarios.py`: capability filtering through built-in Profiles.
- `tests/test_tools.py`: built-in Tool execution.

`SecurityGuardMiddleware` currently evaluates blocked shell patterns and filesystem paths only. It never reads the declared Profile permission. Adding access enforcement changes a shared security boundary and requires explicit deny/approval/full-access matrix coverage.

### Session and credential boundaries

- `AgentRuntimeFactory` derives Session paths from ProfileManager and resolves credential values through ConfigManager.
- `MiaREPL` lists/resumes/forks Session files under Profile directories.
- `tests/test_sessions.py`, `tests/test_session_tree.py`, `tests/test_session_pagination.py`, `tests/test_e2e_scenarios.py`, and `tests/test_orchestration.py` exercise append-only history and active paths.
- `tests/test_credentials.py` and `tests/test_auth_config.py` cover machine-global credential storage/resolution.

New Agent homes must preserve legacy path lookup without moving JSONL or copying resolved secrets.

## Affected Stories

- **e01s01 Minimal Streaming REPL:** default startup identity and runtime construction change from coding Profile to Mia Agent.
- **e01s02 Provider and Tool Execution:** Tool visibility and middleware execution gain access-policy enforcement.
- **e01s03 Durable Sessions:** Session directory ownership changes additively and must preserve replay.
- **e02 REPL polish stories:** help, banners, slash commands, Profile/model/session inspection, and aliases change.
- **e03s01 Native Orchestration Mode Vertical Slice:** ModeRuntime becomes compatibility/private strategy; single/research behavior and event attribution remain regression requirements.
- **e03s02 Slash Command Contract Alignment:** `/profile`, `/mode`, aliases, command hints, and Session inspection need Agent-first replacements.
- **e04s01 Named Agent Vertical Slice:** owns canonical Agent model, registry, default Mia, additive persistence, and canonical commands.
- **e04s02 Agent-Owned State and Access Boundary:** owns access levels, Tool effects, approval, global-secret references, and effective policy.
- **e04s03 Direct Agent-to-Agent Delegation:** owns Task contracts, one-hop runtime, terminal outcomes, and child Session attribution.
- **e04s04 Agent-First Compatibility Migration:** owns AgentRunner, prompt-scoped Run identity, private Research behavior, legacy adapters, and docs.

## Test Coverage

### Existing coverage to preserve

- `tests/test_profiles.py`: built-in/custom Profile loading, filtering, and persistence.
- `tests/test_orchestration.py`: Mode validation, single/research sequence, envelope attribution, failure/cancellation, child Session metadata.
- `tests/test_agent_loop.py`: provider streaming, multi-step Tool loop, max steps, and event ordering.
- `tests/test_middleware_pipeline.py`: onion execution, SecurityGuard, audit, and cost controls.
- `tests/test_cli_repl.py`: runtime initialization, Profile switching, Session resume/tree commands, interactive behavior.
- `tests/test_cli_print_mode.py`: non-interactive prompt execution and Mode selection.
- `tests/test_sessions.py`, `tests/test_session_tree.py`, `tests/test_session_pagination.py`: JSONL persistence, branches, active paths, pagination.
- `tests/test_credentials.py`, `tests/test_auth_config.py`: credential storage and provider resolution.
- `tests/test_e2e_scenarios.py`: full harness flow and read-only/minimal Tool filtering.

### Required new coverage

- `tests/test_agents.py`: Agent validation, default Mia, CRUD/default selection, native/legacy precedence, reserved IDs, additive Agent homes, Session fallback, secret-free persistence.
- `tests/test_access_policy.py`: three-level matrix, legacy mappings, Tool effects, approval callback, missing/denied approval, full-access permanent guards, effective-access intersection.
- `tests/test_delegation.py`: Task contracts, eligibility, one-hop execution, policy non-escalation, data minimization, unique attribution, timeout/cancellation, provider/max-step failure.
- Expanded CLI tests for canonical Agent commands and legacy warning aliases.
- Expanded orchestration tests for AgentRunner, prompt-scoped unique Run IDs, stable Session IDs, canonical envelopes, and Research Agent compatibility.

### Gaps in current tests

- No test enforces `AgentProfile.permission` below Tool filtering.
- No approval callback or per-invocation deny path exists.
- No test distinguishes policy rejection from Tool execution failure.
- No Agent CRUD/default selection or Agent-home persistence exists.
- No test proves credential values are absent from Agent, approval, Session, Delegation, and audit artifacts together.
- No public Task request/result or direct Delegation tests exist.
- No test rejects recursive/self/ineligible Delegation.
- No test treats provider error chunks and max_steps as failed delegated Tasks.
- No test requires a fresh Run ID for each interactive prompt in one Session.
- No test proves native-first legacy Session lookup without source rewrite.

## Churn and Sensitivity

Git history shows disproportionate churn in the frontends:

- `src/mia_cli/repl.py`: 47 commits
- `src/mia_cli/main.py`: 11 commits
- `src/mia_agent/auth/config.py`: 9 commits
- `src/mia_agent/orchestration.py`: 4 commits
- profile, Session entry, middleware pipeline, and security modules: 1 commit each

High REPL churn plus its direct ownership of runtime construction, Profile switching, Session inspection, and aliases makes it the most sensitive migration seam. The low commit count in profile/middleware modules does not lower risk because their APIs are shared and security-relevant.

## Risk: High

The change replaces a shared public identity/API, alters the central runtime factory and both CLI frontends, adds enforcement at the Tool security boundary, changes Session path resolution, and introduces multi-Agent execution. Fan-in exceeds ten callers, several contracts are security-sensitive, and the required Agent/access/Delegation tests do not yet exist.

## Recommended action

Proceed only in the ordered e04 stories with failing contract tests first:

1. Establish canonical Agent/AgentManager and additive legacy compatibility.
2. Enforce three access levels, approval, Tool effects, Agent ownership, and global-secret references.
3. Add one synchronous one-hop Delegation service and Tool with truthful terminal outcomes.
4. Route canonical/legacy frontends through one AgentRunner and finish Agent-first terminology.

Do not edit all Profile/Mode references in one rename. Keep changes additive until native Agent paths and compatibility fixtures pass. Before each story completes, run its targeted security/compatibility suite; before e04 completes, run Ruff format/check, strict Mypy, full pytest, package build, YAML/spec consistency, and active-document terminology checks.
