# Test Design: e08-governed-core-extension-host

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---:|---|---|
| SC-e08s01-P0-01 | Declarative Plugin manifests expose strict static Skills/Templates without executing code | P0 | Integration | `tests/test_plugin_host.py`, `src/mia_agent/plugin_models.py` |
| SC-e08s01-P0-02 | Trusted-code provenance and explicit trust are required before executable activation | P0 | Integration | `tests/test_plugin_host.py`, `src/mia_agent/plugins.py` |
| SC-e08s01-P0-03 | API versions, declarations, IDs, effects, and secret-free metadata fail closed | P0 | Unit | `tests/test_plugins.py`, `src/mia_agent/plugin_models.py` |
| SC-e08s01-P1-04 | Existing Notes catalog, Template inspection, and Plugin-free behavior remain compatible | P1 | Integration | `tests/test_notes_plugin.py`, `tests/test_agent_templates.py`, `tests/test_plugin_host.py` |
| SC-e08s02-P0-01 | Complete enabled Plugin set is validated and activated in deterministic dependency order | P0 | Integration | `tests/test_plugin_host.py`, `src/mia_agent/plugins.py` |
| SC-e08s02-P0-02 | Staged registrations publish atomically and partial activation rolls back effects in reverse order | P0 | Integration | `tests/test_plugin_host.py`, `src/mia_agent/plugins.py` |
| SC-e08s02-P0-03 | Runtime contributions and owned effects are immutable and scoped to one Run snapshot | P0 | Integration | `tests/test_plugin_host.py`, `tests/test_agent_runtime.py` |
| SC-e08s02-P0-04 | Cooperative disposal is idempotent, diagnosed, deadline-bounded, and quarantines timed-out Plugins | P0 | Integration | `tests/test_plugin_host.py`, `tests/test_agent_runtime.py` |
| SC-e08s03-P0-01 | Plugin Tool middleware cannot bypass the final Core validation and approval gate | P0 | Integration | `tests/test_plugin_host.py`, `tests/test_access_policy.py`, `tests/test_middleware_pipeline.py` |
| SC-e08s03-P0-02 | Plugin API cannot replace Core identity, credentials, access, Session, attribution, or terminal truth | P0 | Integration | `tests/test_plugin_host.py`, `tests/test_agent_runtime.py`, `tests/test_e2e_scenarios.py` |
| SC-e08s03-P0-03 | Notes migration preserves Plugin identity, Tool effects, Template, data ownership, and Plugin-free compatibility | P0 | Integration | `tests/test_notes_plugin.py`, `tests/test_plugins.py`, `tests/test_agent_runtime.py` |
| SC-e08s03-P1-04 | Public API/version inspection and clean wheel installation expose only the supported host surface | P1 | E2E | `tests/test_surface_checks.py`, `scripts/check-wheel-surface.py` |

## 2. Fixture Architecture & Isolation

- **Agent homes:** Every test creates an `AgentManager` rooted at `tmp_path / "agents"`; Plugin data remains below the owning Agent home.
- **Plugin catalog fixtures:** Use small in-memory declarative and trusted-code test Plugins with strict manifests, explicit provenance, dependency declarations, and deterministic IDs.
- **Runtime fixtures:** Use `AgentRuntimeFactory` with `MockProvider`, `RuntimeIdentity`, isolated Session paths, and `contextlib.aclosing` for every early stream exit.
- **Lifecycle probes:** Use async callbacks/disposers that append ordered markers, yield cooperatively, fail, or exceed a short test timeout. Never use real network or uncontrolled sleeps in the normal suite.
- **Policy fixtures:** Use existing access, security, audit, and cost middleware with a final Core validator; inspect final arguments and executor call counts.
- **Packaging fixtures:** Build the wheel offline into a temporary output directory and inspect only the declared public packages, Plugin API exports, entry-point metadata, and retained Notes surface.
- **Isolation:** Clear `PluginManager` quarantine state in fixture teardown. Do not modify a user's home, credentials, or persistent Session data.

## 3. Risk and Level Strategy

P0 scenarios use unit tests for strict model invariants and integration tests for host-to-factory-to-run behavior. The host boundary is tested through public `PluginManager`/`PluginHost`, `AgentRuntimeFactory`, `AgentRunner`, and middleware interfaces; private helpers are inspected only when needed to prove ordering. P1 scenarios cover compatibility and package surfaces after the trust boundary is proven. No network, remote catalog, automatic installation, process sandbox, or hosted E2E is required.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Determinism | Dependency order, staged publication, rollback, and cleanup order are stable | `uv run --offline pytest tests/test_plugin_host.py -k 'order or deterministic or rollback or staged'` |
| Security | No supported Plugin hook bypasses final Core policy, identity, attribution, or secret sanitation | `uv run --offline pytest tests/test_plugin_host.py tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'security or policy or attribution or secret or bypass or final' && printf 'no new security findings in affected paths\n'` |
| Lifecycle | Cooperative activation/disposal failures are bounded, idempotent, attributed, and quarantine timed-out Plugins | `uv run --offline pytest tests/test_plugin_host.py tests/test_agent_runtime.py -k 'activation or dispose or cleanup or timeout or quarantine'` |
| Compatibility | Notes and Plugin-free Agents preserve behavior and serialized surfaces | `uv run --offline pytest tests/test_notes_plugin.py tests/test_plugins.py tests/test_agent_runtime.py -k 'notes or plugin_free or compatibility'` |
| Package surface | Clean wheel contains the supported Plugin API and no retired or undeclared extension surface | `rm -rf dist && uv build --offline && WHEEL=$(find dist -maxdepth 1 -name 'mia_ai-0.6.0*.whl' -print -quit) && test -n "$WHEEL" && uv run --offline python scripts/check-wheel-surface.py "$WHEEL"` |
| Quality | Complete repository quality gate remains clean | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh` |

## 5. Out of Scope

- Arbitrary project-local code loading, remote catalogs, automatic package/dependency installation, hot reload, background work, or process isolation.
- Generic service/dependency-injection containers, Core/provider replacement, Plugin commands/UI, Tool overrides, mutable Session hooks, or arbitrary event buses.
- Testing malicious code termination guarantees that Python's same-process authority cannot provide.

## 6. Test Data and Security Rules

Fixtures must contain synthetic Plugin IDs, configuration, and note data only. Assertions must prove credentials, authorization headers, provider instances, mutable Session stores, and unsanitized exceptions do not cross the Plugin context or appear in events, diagnostics, logs, or artifacts. Any new security finding in an affected path blocks the story.

## 7. Exit Criteria

All twelve scenarios pass through supported public boundaries; all NFR commands pass; no critical/high security finding or failing required gate remains; and the plan-consistency check reports `CRITICAL=0 HIGH=0` before implementation starts.
