# Impact — e07 Production Runtime Integrity

## Target

Deepen the existing `AgentRunner`, `AgentRuntimeFactory`, runtime event envelopes, Session admission/storage, and `ToolPipeline` boundaries to deliver the canonical closeable Run contract. The purpose of `AgentRunner` is to own one headless Agent prompt execution and terminal truth; its callers are `mia_cli.main`, `mia_cli.repl`, `mia_cli.tui.app`, delegation, package exports, and runtime tests (`src/mia_agent/agent_runner.py:58`, `src/mia_cli/repl.py:141`, `src/mia_cli/tui/app.py:103`). `AgentRuntimeFactory` owns provider/Tool/middleware/Session composition and is called by `AgentRunner`, `DelegationService`, and direct runtime tests (`src/mia_agent/runtime_factory.py:29`, `src/mia_agent/delegation.py:18`). `ToolPipeline` owns onion execution ordering and is used by `AgentHarness`, policy/security/audit tests, and end-to-end scenarios (`src/mia_middleware/pipeline.py:28`, `src/mia_agent/harness.py:31`).

## Dependents

- `src/mia_agent/agent_runner.py`: public headless prompt entry; currently exposes `prompt()` plus inspection helpers and emits cancellation/error envelopes directly.
- `src/mia_agent/runtime_factory.py`: builds every Agent runtime, resolves credentials/models, filters Tools, wires middleware, restores Sessions, and persists identity metadata.
- `src/mia_agent/delegation.py`: constructs delegated runtimes through the same factory and must retain bounded depth/access semantics.
- `src/mia_agent/harness.py`: executes provider turns and visible Tools through `ToolPipeline`; must remain headless and UI-independent.
- `src/mia_agent/runtime_events.py`: owns immutable attribution envelopes and sanitized terminal errors.
- `src/mia_cli/main.py`, `src/mia_cli/repl.py`, `src/mia_cli/tui/app.py`: frontend Adapters that must consume the canonical stream without classifying terminal state themselves.
- `src/mia_middleware/access.py`, `security.py`, and `telemetry.py`: permanent policy, security, audit, and cost controls around every visible Tool.
- `src/mia_agent/agents/manager.py` and `src/mia_agent/session/`: Agent-owned Session paths, append-only entries, and conflict admission boundaries.

## Affected Stories

- e07s01 Canonical Closeable Agent Run Stream.
- e07s02 Safeguarded Runtime Settings and Session Admission.
- e07s03 Final Core Tool Validation and Plugin Boundary.
- Preserve e04/e05/e06 identity, Plugin, Template, delegation, and clean-break contracts; e08 owns the broader governed extension host.

## Test Coverage

- `tests/test_agent_runtime.py`: current runner/factory composition, error conversion, and research sequencing.
- `tests/test_agent_loop.py`: harness stream, Tool calls, provider errors, and terminal events.
- `tests/test_access_policy.py`, `tests/test_middleware_pipeline.py`, `tests/test_e2e_scenarios.py`: onion ordering, access, security, audit, telemetry, and failure behavior.
- `tests/test_plugins.py`: current Plugin Tool resolution, effect mapping, duplicate rejection, and runtime composition.
- `tests/test_delegation.py`: bounded delegated runtime and access behavior.
- `tests/test_sessions.py`, `tests/test_agents.py`: append-only persistence and Agent-owned paths.
- `tests/test_cli_print_mode.py`, `tests/test_cli_repl.py`, `tests/test_tui_app.py`: frontend compatibility.
- Gap to close: no public `run(RunRequest)` contract, lifecycle finalization state machine, same-Session admission lock, or final Core validation/cleanup regression suite exists yet.

## Risk: High

This is a shared runtime and trust-boundary change with more than ten callers, provider and Session side effects, security-sensitive middleware ordering, and no existing exactly-once lifecycle contract. A faulty implementation can leak secrets, bypass approval/audit, corrupt append-only history, or report false terminal outcomes.

## Recommended action

Proceed with e07 story slicing and a P0 test plan before implementation. Implement the smallest canonical stream first, then settings/admission, then the final Core Tool/Plugin validation boundary. Use `MockProvider`, isolated temporary Agent homes, deterministic async gates, and public-interface regression tests. Do not implement e08's arbitrary installed-code extension host in this epic.
