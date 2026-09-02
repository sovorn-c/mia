# e05 Impact Assessment — Plugin and Agent Template Foundation

## Target

Add one bundled Notes Plugin lifecycle and one bundled Notes Agent Template while extending these shared seams:

- `Agent` / `AgentManager` — persist per-Agent Plugin enablement/configuration and instantiate a safe template.
- `AgentRuntimeFactory` — resolve enabled Plugin Tools before capability and access filtering.
- `AgentHarness`, `ToolCallContext`, and audit events — preserve optional Plugin attribution through execution.
- `BaseTool` — identify Plugin-contributed Tools without changing existing Tool behavior.
- `mia_cli.main` — expose local Plugin lifecycle and Agent Template commands.

Net-new Notes storage and Plugin registry modules have no existing dependents.

## Zoom-Out: Purpose, Callers, and Contracts

### Agent and AgentManager

- **Purpose:** validate, resolve, persist, inspect, and select durable Agents while preserving legacy Profile compatibility.
- **Callers:** `AgentRunner`, `DelegationService`, `AgentRuntimeFactory`, CLI, REPL, and Agent/Delegation/orchestration tests.
- **Contracts to preserve:** path-safe IDs, atomic writes, built-in immutability, native-first legacy fallback, secret-free serialization, explicit full-access consent, Agent-owned Session lookup, and stable built-in behavior.

### AgentRuntimeFactory

- **Purpose:** construct every Agent runtime with one provider, Tool set, access policy, middleware pipeline, Session store, compactor, and attributed identity.
- **Callers:** `AgentRunner`, `ModeRuntime`, `DelegationService`, CLI, REPL, and orchestration/delegation tests (17 indexed references).
- **Contracts to preserve:** one-Agent headless harness, all visible Tools capability-filtered, read-only effect filtering, approval and permanent security middleware, delegation depth rules, append-only Session restoration, and deterministic provider injection.

### AgentHarness and Tool middleware

- **Purpose:** execute one Agent turn and route every Tool through the shared middleware pipeline with truthful, redacted results.
- **Callers:** runtime factory, direct harness tests, provider tests, CLI renderers, and orchestration envelopes.
- **Contracts to preserve:** async `AgentEvent` ordering, stable existing event fields, secret redaction at every output boundary, one result per call, middleware execution before Tool code, and append-only message persistence.

### CLI

- **Purpose:** provide the canonical Agent lifecycle and prompt entry point while retaining compatibility aliases.
- **Callers:** users, `uv run mia`, CLI tests, and REPL startup.
- **Contracts to preserve:** existing command names/options, actionable `BadParameter` errors, no secret rendering, no network requirement for local management, and no remote Git or package side effects.

## Dependents

1. `src/mia_agent/agent_runner.py` — builds canonical direct and research Runs.
2. `src/mia_agent/delegation.py` — builds constrained child runtimes through the same factory.
3. `src/mia_agent/mode_runtime.py` — compatibility execution path using the shared factory.
4. `src/mia_cli/main.py` — Agent management and one-shot execution.
5. `src/mia_cli/repl.py` — long-lived Agent selection and runtime initialization.
6. `src/mia_agent/profiles/manager.py` — compatibility projection from Agent fields.
7. `src/mia_middleware/access.py` — fail-closed capability/effect enforcement for every visible Tool.
8. `src/mia_middleware/telemetry.py` — attributed, redacted Tool audit records.
9. `src/mia_agent/session/*` — durable runtime history that must not become Plugin-owned.
10. Existing filesystem, shell, and Delegation Tools — must remain unchanged when no Plugin is enabled.

## Affected Stories

- **e01/e02 CLI and REPL stories:** command registration and rendering regressions are possible.
- **e03s01 Native Orchestration:** factory and harness event contracts are shared.
- **e04s01 Named Agent Vertical Slice:** Agent persistence and CLI lifecycle gain Plugin/template behavior.
- **e04s02 Agent State and Access Boundary:** Plugin capability, state, credentials, and access must remain monotonic and Agent-owned.
- **e04s03 Direct Agent Delegation:** delegated runtimes must receive the same enabled Plugin set without escalating caller/recipient access.
- **e04s04 Agent-First Compatibility Migration:** Profile/Mode adapters and canonical Agent execution must continue to use one runtime path.

## Test Coverage

- `tests/test_agents.py` — Agent schema, persistence, path safety, full-access confirmation, and secret-free serialization.
- `tests/test_orchestration.py` — factory Tool construction, Session restoration, canonical/legacy paths, and persisted consent.
- `tests/test_access_policy.py` — unknown Tool fail-closed behavior, effect classification, approval, and attributed telemetry.
- `tests/test_agent_loop.py` — Tool event ordering, execution, errors, and session persistence.
- `tests/test_delegation.py` — effective delegated access and child runtime behavior.
- `tests/test_cli_print_mode.py` / `tests/test_cli_repl.py` — command lifecycle and Agent selection.
- `tests/test_tools.py` — confined filesystem behavior and Tool effects.

### Gaps to close in e05

- No Plugin manifest, install, enable/disable, configuration, or compatibility tests.
- No Agent-scoped Plugin data isolation tests.
- No Plugin Tool attribution in events/audit tests.
- No duplicate Tool-name rejection or Plugin Tool effect-declaration tests.
- No Agent Template validation, secret exclusion, missing-requirement, or collision tests.
- No regression proving Plugin-free Agents receive an identical Tool set.

## Risk: High

`AgentRuntimeFactory` and the Tool execution boundary are shared security APIs with more than ten callers, and Agent persistence carries private-data and full-access invariants. Optional, backward-compatible fields and contract-first tests are required before implementation.

## Recommended Action

Proceed with three vertical stories and TDD. Keep Plugin code bundled and locally trusted, add no dependency, preserve existing Tool/event behavior when `plugin_id` is absent, reject duplicate Tool names and undeclared effects before runtime construction, resolve Plugin contributions before the existing capability/access pipeline, include Plugin Tools in effect classification, store Notes only under the owning Agent home, and instantiate templates only through existing AgentManager validation and atomic persistence.
