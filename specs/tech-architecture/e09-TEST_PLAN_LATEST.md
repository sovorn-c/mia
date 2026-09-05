# Test Design: e09-local-operations-recovery

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---:|---|---|
| SC-e09s01-P0-01 | Attempted Tool actions produce attributed, secret-free diagnostic records for success, rejection, and failure | P0 | Integration | `tests/test_diagnostics.py`, `src/mia_agent/diagnostics.py`, `src/mia_middleware/telemetry.py` |
| SC-e09s01-P0-02 | Run terminal outcomes and Plugin activation, observer, disposal, timeout, and quarantine failures remain attributable and do not rewrite domain truth | P0 | Integration | `tests/test_agent_runtime.py`, `tests/test_plugin_host.py`, `tests/test_diagnostics.py` |
| SC-e09s01-P0-03 | Diagnostic persistence is append-only, bounded by a documented retention policy, and fails explicitly without changing the Tool or Run outcome | P0 | Integration | `tests/test_diagnostics.py`, `src/mia_agent/diagnostics.py` |
| SC-e09s01-P1-04 | Operators can inspect local diagnostics with stable ordering and filters without credential-shaped values or raw exception data | P1 | E2E | `tests/test_diagnostics_cli.py`, `src/mia_cli/main.py` |
| SC-e09s02-P0-01 | Data-location inspection distinguishes Agent, Session, Plugin, diagnostics, and credential paths while never exposing credential values | P0 | Unit | `tests/test_operations.py`, `src/mia_agent/operations.py` |
| SC-e09s02-P0-02 | Backup archives contain only supported non-credential data, include a versioned manifest, and preserve file metadata needed for restore | P0 | Integration | `tests/test_operations.py`, `src/mia_agent/operations.py` |
| SC-e09s02-P0-03 | Restore validates archive paths, manifest, checksums, and destination ownership before an atomic non-destructive commit | P0 | Integration | `tests/test_operations.py`, `src/mia_agent/operations.py` |
| SC-e09s02-P1-04 | A supported backup round trip restores Agent, Session, Plugin, and diagnostic data without changing valid Session JSONL content | P1 | E2E | `tests/test_operations.py`, `tests/test_sessions.py` |
| SC-e09s03-P0-01 | Interrupted atomic-write artifacts and truncated Session records are detected and reported without rewriting valid history | P0 | Integration | `tests/test_recovery.py`, `src/mia_agent/recovery.py`, `src/mia_agent/session/jsonl.py` |
| SC-e09s03-P0-02 | Interior corruption, unsupported record versions, path escapes, and invalid Plugin data fail closed with actionable sanitized results | P0 | Integration | `tests/test_recovery.py`, `src/mia_agent/recovery.py` |
| SC-e09s03-P1-03 | Explicit recovery verification is repeatable, preserves Plugin-owned data, and reports when a verified backup restore is required | P1 | E2E | `tests/test_recovery_cli.py`, `src/mia_cli/main.py` |

## 2. Fixture Architecture & Isolation

- **Data roots:** Every test uses `tmp_path` with an explicit `AgentManager` root and an isolated diagnostic root; no test reads or writes the operator's home.
- **Runtime fixtures:** Use `AgentRunner`, `AgentRuntimeFactory`, `MockProvider`, `RuntimeIdentity`, and `contextlib.aclosing` so Run, Tool, and Plugin records are produced through supported boundaries.
- **Diagnostic fixtures:** Use synthetic IDs, API-key-shaped sentinel values, authorization headers, and exception text to prove recursive redaction without persisting secrets.
- **Plugin fixtures:** Use in-memory trusted Plugin implementations with cooperative observers/disposers that succeed, fail, timeout, or quarantine; Plugin data remains below its owning Agent home.
- **Archive fixtures:** Build archives in `tmp_path` with valid manifest/checksums plus malicious traversal, symlink, duplicate, missing, and stale-version cases. Restore into a fresh destination and never overwrite an existing destination implicitly.
- **Recovery fixtures:** Create valid JSONL, partial final lines, malformed interior lines, unsupported entries, and orphan atomic-write temporary files. Assertions compare bytes before and after verification.
- **Isolation:** No network, remote telemetry, credential backup, automatic deletion, or uncontrolled process/sleep behavior is required.

## 3. Risk and Level Strategy

P0 scenarios use unit tests for path and schema invariants and integration tests for the runtime-to-diagnostic and archive-to-restore boundaries. P1 scenarios exercise the CLI and complete local round trips after the lower-level trust and data-integrity contracts are proven. Tests must use public diagnostics, operations, recovery, Agent, Session, Plugin, and CLI interfaces; private helpers are inspected only to prove a boundary invariant.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Attribution | Tool attempts, Plugin lifecycle failures, and Run outcomes retain Run/Agent/Session/Plugin identity | `uv run --offline pytest tests/test_diagnostics.py tests/test_agent_runtime.py tests/test_plugin_host.py -k 'attribut or diagnostic or audit or cleanup or terminal'` |
| Security | Diagnostics and archives contain no credentials, sensitive Tool arguments, raw exception data, or path escapes | `uv run --offline pytest tests/test_diagnostics.py tests/test_operations.py tests/test_recovery.py -k 'secret or redact or credential or traversal or escape or unsafe' && printf 'no new security findings in affected paths\n'` |
| Retention | Diagnostic storage is append-only, bounded, deterministic, and explicit when persistence fails | `uv run --offline pytest tests/test_diagnostics.py -k 'append or retention or bounded or persistence or failure'` |
| Recovery | Verification detects incomplete/corrupt data without mutating valid Sessions or Plugin data | `uv run --offline pytest tests/test_recovery.py tests/test_sessions.py tests/test_operations.py -k 'recover or corrupt or interrupted or preserve or restore'` |
| Compatibility | Existing Agent, Session, Plugin, Notes, and Plugin-free behavior remains unchanged | `uv run --offline pytest tests/test_agent_runtime.py tests/test_sessions.py tests/test_plugins.py tests/test_notes_plugin.py -k 'compatibility or append or notes or plugin_free or session'` |
| CLI | Diagnostic, data-location, backup/restore, and recovery verification commands return truthful exit status and secret-free output | `uv run --offline pytest tests/test_diagnostics_cli.py tests/test_recovery_cli.py tests/test_cli_print_mode.py -k 'diagnostic or data or backup or restore or recover'` |
| Quality | Repository quality and packaging remain clean | `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh && uv build --offline` |

## 5. Out of Scope

- Remote telemetry, dashboards, hosted monitoring, exporters, or support services.
- Automatic destructive repair, migration, deletion, or rewriting of user files.
- Credential values in diagnostic output or backup archives; credential location guidance is included, but credential export is not.
- OS/process sandboxing, background Run scheduling, new providers, automatic package installation, or a generic event/service framework.

## 6. Test Data and Security Rules

Fixtures use synthetic Agent, Run, Session, Tool, Plugin, and archive identifiers. Assertions must prove that API keys, authorization headers, provider objects, raw sensitive arguments, absolute paths outside the configured root, and unsanitized Plugin exceptions do not enter diagnostics, archives, CLI output, or logs. Any new critical or high security finding in an affected path blocks the epic.

## 7. Exit Criteria

All eleven scenarios pass through supported public boundaries; all NFR commands pass; valid Session and Plugin data are byte-preserved by verification and round trips; no critical/high security finding or failing required gate remains; and `bash scripts/lib/plan-consistency-check.sh specs/epics/e09-local-operations-recovery` reports `CRITICAL=0 HIGH=0` before implementation starts.
