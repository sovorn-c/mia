# Impact — Local Operations and Recovery

## Target

Plan e09 as the local operations boundary for the already-delivered e07 Run contract and e08 governed Plugin host. The change adds durable, bounded diagnostics, an explicit non-credential data layout and backup/restore boundary, and read-only recovery verification. It must not create a second execution root, event bus, hosted telemetry system, or automatic repair path.

Primary implementation seams:

- `src/mia_agent/diagnostics.py` — new validated, sanitized diagnostic records and bounded local store.
- `src/mia_middleware/telemetry.py` — preserve Tool audit behavior while forwarding only sanitized records.
- `src/mia_agent/agent_runner.py` and `src/mia_agent/plugin_host.py` — expose existing Run/Plugin lifecycle diagnostics without moving terminal or cleanup ownership.
- `src/mia_agent/agents/manager.py` and `src/mia_agent/auth/credentials.py` — preserve existing Agent/Session root and separate credential path contracts.
- `src/mia_agent/operations.py` — new Core-owned data layout and versioned archive/restore boundary.
- `src/mia_agent/session/jsonl.py` and `src/mia_agent/recovery.py` — preserve append-only Session validation and add non-destructive corruption classification.
- `src/mia_cli/main.py` — add read-only diagnostic, data-location, backup/restore, and recovery verification commands.

## Dependents (shared boundaries)

- `AgentRuntimeFactory` constructs `AuditLogMiddleware`, resolves Agent/Session paths, and composes Plugin data paths for every direct and delegated Run.
- `AgentRunner` owns terminal finalization, Plugin cleanup, quarantine, and admission release; e09 must observe these decisions rather than alter them.
- `ToolPipeline` and `ToolCallContext` provide attempted Tool identity, effect, arguments, and middleware metadata to audit records.
- `PluginHost` and `PluginManager` own Plugin activation, attribution, cleanup diagnostics, and Agent-owned Plugin directories.
- `AgentManager`, `JsonlSessionStore`, `SessionTree`, and atomic storage helpers own Agent definitions, append-only Sessions, and local writes.
- `FileCredentialStore` owns provider credentials under `~/.mia/credentials.json`; its values must remain outside diagnostics and backups.
- CLI, REPL, TUI, and tests are the operator-facing or regression callers that must retain existing Agent/Run behavior.

This is a high-risk shared trust/data-boundary change. The test plan covers the fan-in and preserves e04-e08 contracts.

## Affected stories

- **e09s01 — Attributed Local Diagnostics and Bounded Retention:** new Tool, Run, and Plugin operational record boundary and inspection command.
- **e09s02 — Supported Data Locations and Backup/Restore:** new data-layout descriptor, non-credential archive manifest, path/digest validation, staging, and CLI operations.
- **e09s03 — Non-Destructive Interrupted-Write and Corrupt-Data Recovery:** read-only detection and truthful status for temporary, truncated, corrupt, unsupported, or unsafe data, with explicit restore guidance.

Preserve delivered contracts from e04, e05, e06, e07, and e08: Agent identity, credential isolation, access/security/audit safeguards, append-only Session history, terminal truth, Plugin attribution, and Core-owned lifecycle cleanup.

## Test coverage and gaps

Existing coverage exercises the affected foundations:

- `tests/test_middleware_pipeline.py`, `tests/test_access_policy.py`, and `tests/test_plugins.py` cover Tool audit context, sanitation, attribution, Plugin lifecycle, and cleanup diagnostics.
- `tests/test_agent_runtime.py`, `tests/test_agent_loop.py`, and `tests/test_e2e_scenarios.py` cover terminal outcomes, Session admission, cleanup ordering, and failure propagation.
- `tests/test_sessions.py` covers JSONL storage, tree reconstruction, branching, and compaction.
- `tests/test_agents.py`, `tests/test_credentials.py`, and `tests/test_notes_plugin.py` cover Agent-owned storage, credentials, and Plugin-owned data.
- `tests/test_cli_print_mode.py`, `tests/test_plugin_cli.py`, and `tests/test_agent_template_cli.py` cover current CLI boundaries.

Required new coverage is specified in `specs/tech-architecture/e09-TEST_PLAN_LATEST.md`:

- `tests/test_diagnostics.py` and `tests/test_diagnostics_cli.py` for attribution, recursive sanitation, retention, persistence-health separation, and truthful inspection.
- `tests/test_operations.py` and `tests/test_operations_cli.py` for data ownership, credential exclusion, manifest/digest integrity, path confinement, staged restore, and non-overwrite behavior.
- `tests/test_recovery.py` and `tests/test_recovery_cli.py` for interrupted writes, corrupt/unsupported data, deterministic status, byte preservation, and explicit restore guidance.

Known gaps are intentional planning targets: no durable diagnostic store, unified data-layout API, archive/restore contract, or read-only recovery verifier currently exists.

## Risk: High

The change crosses local persistence, security sanitation, shared runtime callbacks, Plugin-owned data, archive extraction, CLI exit status, and append-only history. A faulty implementation could leak credentials, follow an archive path escape, overwrite valid data, suppress a real Run outcome, or manufacture a false clean/recovered state.

## Recommended action

Proceed with the three vertical slices in dependency order: e09s01 diagnostic evidence first, e09s02 supported archive/restore second, and e09s03 read-only recovery verification last. Use standard-library/Pydantic facilities only, keep credentials excluded, require byte-preservation and path-security regression tests, and run `bash scripts/lib/plan-consistency-check.sh specs/epics/e09-local-operations-recovery` before implementation.
