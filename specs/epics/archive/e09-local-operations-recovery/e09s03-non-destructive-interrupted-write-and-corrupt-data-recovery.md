# e09s03 — Non-Destructive Interrupted-Write and Corrupt-Data Recovery

## 1. Identity

- **Story ID:** e09s03
- **Epic:** e09 — Local Operations and Recovery
- **Type:** feat
- **Risk:** P0
- **Context:** Append-only Sessions, atomic local writes, corruption detection, recovery verification, and safe operator guidance
- **BCPs:** 3
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As an operator, I want Mia to identify interrupted writes and corrupt or unsupported local data without silently repairing it so that I can recover deliberately while preserving valid Session history and Plugin-owned data.

## 3. Context

`JsonlSessionStore.append_entry` uses append-only file flags but does not classify a partial final line, and `load_entries` raises one generic `SessionJsonlError` for malformed JSON or schema data (`src/mia_agent/session/jsonl.py:22-58`). Atomic Agent/configuration helpers write through temporary files and replace the target (`src/mia_agent/agents/storage.py:52-78`), but orphan temporary files and incomplete writes are not surfaced. e09s02 supplies a verified explicit restore path; this story defines non-destructive detection and operator-facing recovery verification around it.

## 4. Problem

A process interruption can leave an orphan temporary file or a truncated final JSONL record. A corrupt interior record, unsupported schema, path escape, or damaged Plugin file can be worse than a clean failure if the system silently drops, rewrites, or deletes data. Operators need to distinguish recoverable signals from blocked corruption and know when a verified backup restore is required.

## 5. Goal

Add a recovery verifier that scans supported local data, classifies interrupted and invalid states, preserves bytes during verification, and exposes explicit CLI status and guidance. It must never claim repair when it only detected a problem and must reuse e09s02's validated restore boundary for any actual replacement.

## 6. Non-Goals

- Automatic deletion of temporary files, truncation of JSONL, migration, repair, or merge.
- Rewriting valid Session history or modifying Plugin-owned data during verification.
- Best-effort loading that hides interior corruption, unsupported records, or path escapes.
- Remote recovery, scheduled backups, process supervision, or OS-level durability guarantees beyond existing fsync/replace behavior.

## 7. Stakeholders

- Operators recovering after interruption, disk errors, or unsupported upgrades.
- Session and Plugin maintainers protecting append-only and owned data.
- Core maintainers defining truthful recovery status and CLI exit codes.
- Security reviewers protecting path, archive, and error boundaries.

## 8. Dependencies

- e04 append-only Session model and Agent-owned path confinement.
- e09s01 diagnostic store for sanitized recovery findings.
- e09s02 DataLayout and validated backup/restore service.
- Existing `JsonlSessionStore`, atomic write helpers, `SessionTree`, and Pydantic validation.
- Test scenarios SC-e09s03-P0-01 through SC-e09s03-P1-03 in `specs/tech-architecture/e09-TEST_PLAN_LATEST.md`.
- No new runtime dependency; use standard-library filesystem and JSON behavior.

## 9. Assumptions

- Verification is read-only by default and compares file bytes or hashes before and after scanning.
- A truncated final JSONL line may be classified as an interrupted append, but it is not silently removed; the operator is directed to restore from a verified backup or preserve the file for explicit support.
- Interior malformed records, unsupported schema versions, invalid paths, and damaged Plugin data are blocked states, not successful recovery.
- The only supported data-changing recovery is an explicit validated restore from e09s02; no automatic repair is included in v0.6.0.

## 10. Constraints

- Recovery scans operate only below the configured supported roots and reject symlink/path escapes.
- Valid Session entries and Plugin data are never rewritten, truncated, or deleted by verification.
- Findings contain sanitized relative paths and bounded error text; no credential values or raw exception data appear.
- Exit status distinguishes clean, warnings/recoverable interruption, and blocked corruption/unsupported data.
- Verification is repeatable and deterministic; repeated scans of unchanged data return the same classification.
- Event-loop, filesystem, and archive failures are reported honestly without claiming stronger durability than the platform provides.

## 11. Domain Model

- **Recovery Finding:** sanitized category, severity/status, relative path, evidence, and recommended action.
- **Recovery Status:** `clean`, `attention`, or `blocked`, with deterministic precedence.
- **Interrupted Write:** orphan temporary artifact or incomplete final append that remains untouched.
- **Corrupt/Unsupported Data:** data that cannot be validated against the supported schema or ownership boundary.
- **Recovery Verification:** read-only scan that proves the state and directs an explicit restore when necessary.

## 12. Requirements

### ADDED: Interrupted-write detection

Core MUST detect supported atomic-write temporary artifacts and incomplete final Session records. Verification MUST preserve the original bytes and report an `attention` state with an explicit non-destructive next action.

### ADDED: Fail-closed corruption and unsupported-data detection

Core MUST classify malformed interior Session records, unsupported schema/manifest versions, invalid or escaped paths, archive-integrity failures, and unsafe Plugin data as `blocked`. It MUST not skip, reinterpret, delete, or rewrite invalid data to manufacture a clean result.

### ADDED: Repeatable recovery verification

Core MUST provide a deterministic read-only verification command over supported local data. Clean data returns success; attention returns a distinct actionable status; blocked data returns non-zero failure. Findings MUST be attributed to safe relative locations and contain no secrets.

### ADDED: Explicit repair boundary

Recovery verification MUST direct operators to the e09s02 validated backup restore path when replacement is required. No automatic destructive repair, Session rewrite, Plugin-data deletion, or silent partial recovery is supported.

## 13. Non-Functional Requirements

- **Integrity:** verification does not change valid Session or Plugin bytes.
- **Truthfulness:** detection, attention, blocked, and restored states are not conflated.
- **Security:** paths and errors are sanitized; credential values never appear in findings or output.
- **Determinism:** classification, ordering, and exit status are stable for unchanged inputs.
- **Compatibility:** normal Session loading, append-only semantics, Plugin data ownership, and e09s02 restore remain supported.

## 14. Contracts

### Existing contracts preserved

- `JsonlSessionStore` remains append-only and continues to validate supported Session entries.
- `SessionTree` remains the reconstruction boundary and does not silently discard invalid entries.
- Atomic Agent/configuration persistence continues to use temporary-file replacement and does not gain automatic cleanup that could delete evidence.
- e09s02 remains the only data-changing restore boundary.

### New contracts

- `RecoveryVerifier` returns a bounded, sanitized, deterministic report over supported roots.
- Recovery status has explicit clean/attention/blocked semantics and truthful CLI exit codes.
- Verification is byte-preserving for valid Session and Plugin data and reports a verified restore requirement instead of repairing unsupported data.
- `mia data verify` or the repository's canonical equivalent exposes the check without mutating data.

## 15. Reason for Depth and Zoom-Out

- **RecoveryVerifier abstraction:** required because Session parsing, atomic temporary artifacts, archive validation, and Plugin-owned data need one read-only classification boundary without embedding repair into each store.
- **Recovery status taxonomy:** required to distinguish a warning that needs operator attention from corruption that must block use; a boolean health result would encourage unsafe automation.
- **CLI verification command:** required so operators can run the same deterministic check before and after backup/restore without importing private Python modules.

`src/mia_agent/session/jsonl.py` purpose: append and validate Session JSONL entries. Callers: `AgentRuntimeFactory`, `AgentHarness`, Session tests, and tree reconstruction; contracts: append-only bytes, typed entries, and explicit parse failure. `src/mia_agent/agents/storage.py` purpose: atomically persist Agent/configuration text and JSON. Callers: `AgentManager` and tests; contracts: temp-file write, fsync, replace, and no credential leakage. `src/mia_agent/operations.py` from e09s02 purpose: own supported data layout and validated archive restore. Callers: CLI and operations tests; contracts: non-credential dataset and preflight before commit. This story adds read-only classification and reuses those owners rather than adding a repair subsystem.

## 16. Implementation Steps

1. Add failing tests and fixtures for orphan temporary files, truncated final Session lines, interior corruption, unsupported records, invalid paths, and byte preservation → verify: `uv run --offline pytest tests/test_recovery.py tests/test_sessions.py -k 'interrupted or corrupt or unsupported or preserve or temp'`
2. Implement deterministic `RecoveryVerifier` classification, sanitized findings, status precedence, and byte-preserving scans of Session, Plugin, diagnostic, and archive data → verify: `uv run --offline pytest tests/test_recovery.py -k 'verify or classify or finding or clean or attention or blocked'`
3. Integrate verified-restore guidance with e09s02 and add read-only CLI recovery verification with truthful exit statuses → verify: `uv run --offline pytest tests/test_recovery_cli.py tests/test_operations_cli.py -k 'recover or verify or restore or status or secret'`
4. Run recovery, Session, Plugin-data preservation, quality, security, and packaging checks with no new security findings in affected paths → verify: `uv run --offline pytest tests/test_recovery.py tests/test_recovery_cli.py tests/test_operations.py tests/test_sessions.py tests/test_plugins.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv build --offline && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e09s03-P0-01: Interrupted writes are detected without mutation

```gherkin
Given valid Session and Plugin data plus an orphan atomic-write temporary file or truncated final Session line
When an operator runs recovery verification
Then Core reports an actionable attention state with a safe relative location
And the original valid and incomplete bytes remain unchanged
And Core does not claim that repair or restore has occurred
```

### Scenario SC-e09s03-P0-02: Corruption and unsupported data fail closed

```gherkin
Given an interior malformed Session entry, unsupported record or archive version, unsafe path, or damaged Plugin data
When an operator runs recovery verification
Then Core reports a blocked state with a sanitized reason and explicit restore guidance
And it does not skip, rewrite, delete, or reinterpret the invalid data
```

### Scenario SC-e09s03-P1-03: Verification is repeatable and truthful

```gherkin
Given unchanged supported local data in clean, attention, or blocked state
When the operator repeats verification before and after a valid e09s02 restore
Then findings, ordering, and exit status are deterministic for each state
And a clean restored dataset is reported only after the complete validated restore succeeds
```

## 18. Verification Script (Step-by-Step)

1. Create an isolated supported data root with valid Session JSONL and Plugin files, an orphan atomic-write temporary file, and a truncated final Session record.
2. Run recovery verification twice and compare findings, exit status, and all supported file bytes.
3. Add an interior malformed record, unsupported schema marker, and unsafe path; verify the report becomes blocked and contains only sanitized relative evidence.
4. Attempt an invalid archive restore and confirm verification still reports blocked without modifying source or destination data.
5. Restore a valid archive through e09s02 into a fresh destination, rerun verification, and confirm clean status only after all checks pass.

## 19. Risks and Mitigations

- **Silent data loss:** make verification read-only and assert byte preservation around every scan.
- **False clean state:** classify interior corruption and unsupported data as blocked; never drop invalid lines.
- **Unsafe path handling:** reuse configured-root ownership and reject symlinks/path escapes in scanner and archive inputs.
- **Repair authority creep:** direct only to explicit e09s02 restore and do not add automatic deletion or migration.
- **Misleading exit status:** define clean/attention/blocked precedence and test CLI status independently.

## 20. Definition of Done and Slopcheck

- All three scenarios pass through public recovery, Session, Plugin-data, archive, and CLI boundaries.
- Verification is deterministic, byte-preserving, secret-free, and honest about what requires explicit restore.
- Invalid data is blocked rather than silently repaired or discarded.
- Every task remains `failing` until its verify command passes during implementation.

### Slopcheck

- `[OK]` Python standard library — JSON/file scanning, hashing, and path checks.
- `[OK]` Pydantic (already installed) — reuse existing Session and archive boundary validation.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic failure and preservation tests.
- No recovery SDK, cloud service, migration framework, or new runtime dependency is proposed.

### Red-Flag Check

Rejected automatic repair, truncation, deletion, history rewriting, best-effort corruption skipping, remote recovery, and claims of process-level durability beyond existing local filesystem guarantees.
