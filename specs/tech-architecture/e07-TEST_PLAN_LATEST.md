# Test Design: e07-production-runtime-integrity

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---|---|---|
| SC-e07s01-P0-01 | A validated `RunRequest` starts one Agent Run through `AgentRunner → AgentRuntimeFactory → AgentHarness` and preserves immutable runtime attribution on every envelope | P0 | Integration | `tests/test_agent_runtime.py`, `src/mia_agent/agent_runner.py` |
| SC-e07s01-P0-02 | Normal stream consumption emits exactly one matching terminal envelope and no event follows it | P0 | Integration | `tests/test_agent_runtime.py`, `src/mia_agent/runtime_events.py` |
| SC-e07s01-P0-03 | Invalid request, missing Agent, provider failure, and missing/duplicate terminal output become sanitized Core-owned terminal errors | P0 | Integration | `tests/test_agent_runtime.py` |
| SC-e07s01-P0-04 | Cancellation and awaited `aclose()` before finalization produce one cancelled outcome; late cancellation and post-delivery closure preserve the finalized outcome; bare abandonment is not guaranteed | P0 | Integration | `tests/test_agent_runtime.py`, `tests/test_cli_repl.py` |
| SC-e07s02-P0-01 | Agent, request, and global provider settings resolve in documented precedence order and invalid effective values fail before provider execution | P0 | Unit/Integration | `tests/test_agent_runtime.py`, `tests/test_agents.py` |
| SC-e07s02-P0-02 | One active Run per `(agent_id, session_id)` is admitted; a conflicting Run fails fast without corrupting append-only Session history | P0 | Integration | `tests/test_agent_runtime.py`, `tests/test_sessions.py` |
| SC-e07s02-P0-03 | Read-only, approval-required, and confirmed full-access policy remain enforced for every visible Tool, including delegated execution | P0 | Integration | `tests/test_access_policy.py`, `tests/test_delegation.py` |
| SC-e07s02-P1-04 | Security, audit, cost, and execution-limit middleware cannot be removed or reordered through Agent configuration; failures remain secret-free and truthful | P1 | Integration | `tests/test_middleware_pipeline.py`, `tests/test_e2e_scenarios.py` |
| SC-e07s03-P0-01 | Existing enabled Plugin Tool contributions are staged, attributed, deterministic, and rejected on duplicate or undeclared names/effects before execution | P0 | Integration | `tests/test_plugins.py`, `tests/test_agent_runtime.py` |
| SC-e07s03-P0-02 | Final Core validation runs after Plugin argument transformation and preserves access, security, effect, and approval truth | P0 | Integration | `tests/test_plugins.py`, `tests/test_access_policy.py` |
| SC-e07s03-P0-03 | Plugin observer/disposal failures are sanitized diagnostics; cooperative cleanup reaches a completion-or-timeout decision without rewriting domain-work truth | P0 | Integration | `tests/test_plugins.py`, `tests/test_agent_loop.py` |
| SC-e07s03-P1-04 | Plugin-free Agents retain existing Tool sets, event discriminators, CLI/REPL/TUI behavior, and Session output | P1 | E2E/Regression | `tests/test_agent_loop.py`, `tests/test_cli_print_mode.py`, `tests/test_cli_repl.py`, `tests/test_tui_app.py` |

## 2. Fixture Architecture & Isolation

- **Agent factories:** Use `AgentManager` with isolated `tmp_path` homes and explicit built-in/custom Agent definitions. Never use the user's real home or credentials.
- **Runtime factories:** Inject `AgentRuntimeFactory` and `MockProvider` through `AgentRunner` constructors. Use deterministic provider streams for success, handled errors, missing terminal, duplicate terminal, cancellation, and delayed cleanup cases.
- **Session state:** Create a fresh `JsonlSessionStore` per test under `tmp_path`; inspect entries after each run to prove append-only identity and no concurrent corruption.
- **Tool fixtures:** Use small test Tools with explicit effects and controlled argument transformations. Verify both Plugin-enabled and Plugin-free tool sets through public runtime construction.
- **Concurrency fixtures:** Coordinate two asyncio Tasks with an `Event`/`Barrier`-style gate around the first Run to deterministically test same-Session admission and distinct-Session concurrency.
- **Lifecycle fixtures:** Use cooperative async observer/disposer doubles that yield, fail, or exceed a short injected deadline. Do not use event-loop-blocking code as a passing timeout fixture; record it as a documented trust-boundary limitation.
- **Output safety:** Assert serialized envelopes, diagnostics, Session entries, and captured logs contain no API-key-shaped values, sensitive arguments, paths outside the isolated home, or raw Plugin exception data.

## 3. Risk-Scaled Level Strategy

- **Unit:** Request validation, identity sanitization, settings precedence, effect mapping, terminal-state transition guards, and final argument/schema checks.
- **Integration:** AgentRunner/factory/harness composition, Session admission, middleware ordering, Plugin staging/attribution/cleanup, and MockProvider streaming behavior.
- **E2E:** CLI print mode, REPL cancellation/closure, Textual adapter rendering, and Plugin-free compatibility through the canonical public entry point.
- **P0 policy:** Every P0 scenario must be deterministic, offline, and run in the targeted test command before a story can be marked complete.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Safety | No visible Tool bypasses access, security, audit, or execution-limit middleware | `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py -q` |
| Truthfulness | Every supported Run has one Core-owned terminal outcome and no post-terminal event | `uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py -q` |
| Isolation | Same-Session conflicts fail fast and Session history remains append-only | `uv run --offline pytest tests/test_sessions.py tests/test_agent_runtime.py -q` |
| Compatibility | Plugin-free CLI, REPL, TUI, and event serialization remain valid | `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py tests/test_agent_loop.py -q` |
| Security | Affected paths produce no new security findings and contain no secret-shaped diagnostics | `uv run --offline pytest tests/test_plugins.py tests/test_agent_runtime.py tests/test_access_policy.py -q && printf 'no new security findings in affected paths\n'` |
| Quality | Formatting, lint, strict types, full tests, and coverage remain green | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh` |

## 5. Out of Scope

- New providers, provider registries, schedulers, queues, remote execution, or lifecycle handles.
- Arbitrary external Plugin code or the full governed extension host planned by e08.
- OS/process sandbox guarantees or forced termination of trusted same-process Python.
- Bare async-generator abandonment timing beyond the supported consume/cancel/awaited-close contract.
- Visual redesign or new frontend interaction modes.
