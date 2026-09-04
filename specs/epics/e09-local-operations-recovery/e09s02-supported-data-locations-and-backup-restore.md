# e09s02 — Supported Data Locations and Backup/Restore

## 1. Identity

- **Story ID:** e09s02
- **Epic:** e09 — Local Operations and Recovery
- **Type:** feat
- **Risk:** P0
- **Context:** Agent-owned data layout, Plugin-owned data, diagnostics, credentials, archive integrity, and CLI operations
- **BCPs:** 5
- **Status:** passing
- **Requirement delta:** ADDED

## 2. User Story

As an operator, I want clear local data locations and a safe backup/restore workflow so that I can protect Agent-owned and Plugin-owned data without exporting credentials or accidentally overwriting unrelated files.

## 3. Context

`AgentManager` owns the Agent root, Agent definitions, and Session paths (`src/mia_agent/agents/manager.py:14-25,134-155`), while `FileCredentialStore` stores provider credentials separately at `~/.mia/credentials.json` (`src/mia_agent/auth/credentials.py:24-34`). Plugin data is placed below the owning Agent home by `PluginHost.activate` (`src/mia_agent/plugin_host.py:319-326`), and e09s01 adds a diagnostic root. There is currently no single data-layout contract, archive manifest, or safe restore path.

## 4. Problem

Operators must know which local paths contain durable Agent, Session, Plugin, diagnostic, and credential data before making a backup. A naive recursive copy can include credential values, follow symlinks, accept archive traversal, overwrite existing data, or restore files without integrity evidence.

## 5. Goal

Define one Core-owned local data layout descriptor and a standard-library backup/restore service that creates a versioned, checksummed archive of supported non-credential data and restores it only after complete validation into an explicitly selected destination.

## 6. Non-Goals

- Backing up, printing, or restoring credential values.
- Remote storage, hosted backup, encryption/key management, retention scheduling, or automatic destructive repair.
- Automatic package or Plugin installation, process isolation, or migration of unsupported user data.
- Silent overwrite, merge, delete, or rewrite of an existing Agent or Plugin home.

## 7. Stakeholders

- Operators protecting local Agent and Plugin data.
- Agent and Plugin users who need to understand ownership and storage locations.
- Core maintainers responsible for path confinement and archive integrity.
- Security reviewers protecting credentials and symlink boundaries.

## 8. Dependencies

- e04 Agent-owned storage and credential separation.
- e08 Plugin-owned data directories and Plugin-free compatibility.
- e09s01 diagnostic store location and records.
- `AgentManager` path ownership, atomic storage helpers, and Session JSONL format.
- Test scenarios SC-e09s02-P0-01 through SC-e09s02-P1-04 in `specs/tech-architecture/e09-TEST_PLAN_LATEST.md`.
- No new runtime dependency; use the standard library archive and hashing modules.

## 9. Assumptions

- The supported backup dataset is the configured Agent root, including Agent definitions, append-only Sessions, Plugin state/data, and local diagnostics, but excluding `credentials.json` and unrecognized external files.
- Backup archives are portable only across compatible Mia data-layout and archive versions; restore rejects unsupported versions rather than guessing.
- Restore is explicit and non-destructive: an existing destination is rejected unless it is empty and explicitly selected, and no source or destination data is deleted automatically.
- Archive integrity is established by a manifest containing schema version, relative file names, sizes, and cryptographic digests.

## 10. Constraints

- Data locations are derived from configured roots and rendered without credential values.
- Archive members are relative regular files within the supported root; symlinks, absolute paths, `..` traversal, duplicate names, and unsupported files are rejected.
- Backup and restore preserve file bytes and Session JSONL order; they do not reinterpret domain records.
- Restore validates the complete archive before committing any file and uses a temporary staging directory plus atomic rename where the platform permits.
- Permissions are restrictive for Agent, Plugin, diagnostic, and archive data; errors are sanitized and actionable.
- Credential location is shown as sensitive/excluded, never copied or included in archive manifests.

## 11. Domain Model

- **Data Layout:** Core-derived map of supported local data categories, ownership, path, and sensitivity.
- **Supported Backup Set:** Explicit list of non-credential files eligible for archive.
- **Backup Manifest:** Versioned archive metadata and per-file size/digest entries.
- **Restore Plan:** Fully validated set of destination writes before commit.
- **Restore Outcome:** `restored`, `rejected`, or `failed` with counts and sanitized diagnostics; no implicit partial success.

## 12. Requirements

### ADDED: Explicit local data locations

Core MUST expose the configured locations for Agent definitions, Sessions, Plugin state/data, diagnostics, and credentials. Each location MUST identify ownership and sensitivity. Credential values MUST never be returned; the credential path MUST be marked excluded from the supported backup set.

### ADDED: Integrity-checked supported backup

Core MUST create a versioned archive containing only supported non-credential local data, relative paths, file sizes, and cryptographic digests. Backup MUST not follow symlinks outside the supported root or include credentials, temporary files, unsupported files, or arbitrary paths.

### ADDED: Validated non-destructive restore

Core MUST validate archive version, manifest, member paths, duplicate names, file types, sizes, and digests before writing. Restore MUST stage the complete result and commit atomically or return a clear failure without presenting a partial restore as successful.

### ADDED: Operator-facing data commands

The supported CLI MUST provide data-location inspection and explicit backup/restore commands with dry-run/validation output, truthful exit codes, and plain secret-free errors. It MUST reject implicit overwrite and unsupported archive versions.

## 13. Non-Functional Requirements

- **Security:** credentials are excluded; archive and restore path handling is confined and symlink-safe.
- **Integrity:** manifest digests, sizes, and archive version are checked before commit.
- **Non-destructiveness:** valid source data is unchanged and existing destinations are not silently overwritten.
- **Portability:** use a documented standard-library archive format and relative paths.
- **Compatibility:** Agent, Session, Plugin, diagnostic, and credential ownership semantics remain stable.
- **Usability:** operators can identify what is backed up and what is intentionally excluded before running the command.

## 14. Contracts

### Existing contracts preserved

- `AgentManager` remains the owner of Agent and Session paths and path-confinement checks.
- `FileCredentialStore` remains separate from Agent and Plugin data; credential values never cross the operations API.
- Plugin data remains below the owning Agent's Plugin directory and is not deleted when a Plugin is disabled.
- Session JSONL remains append-only and byte-preserving during backup/restore.

### New contracts

- `DataLayout` exposes category, owner, path, sensitivity, and backup eligibility without secret values.
- `BackupService` writes an integrity-checked archive of the supported non-credential dataset.
- `RestoreService` validates a complete archive before a non-destructive atomic commit.
- `mia data locations`, `mia data backup`, and `mia data restore` (or the repository's canonical equivalent) provide explicit operator workflows and truthful exit status.

## 15. Reason for Depth and Zoom-Out

- **DataLayout abstraction:** required because Agent, Session, Plugin, diagnostic, and credential roots currently belong to different modules and must be presented consistently without duplicating path logic.
- **Manifest-driven archive:** required because a raw directory copy cannot prove exclusions, integrity, or restore completeness.
- **Staged restore:** required because path and digest validation must finish before any user data is changed.

`src/mia_agent/agents/manager.py` purpose: resolve and confine Agent, Session, and Agent-owned paths. Callers: runtime construction, CLI Session commands, Plugin activation, persistence, and tests. Contracts: normalized IDs, no symlink components, and paths below the configured Agent root. `src/mia_agent/auth/credentials.py` purpose: persist provider credentials separately. Callers: configuration resolution and login; contract: credential values stay in the credential store. `src/mia_agent/plugin_host.py` purpose: assign Plugin-owned data directories and lifecycle ownership. Callers: `AgentRunner`, `AgentRuntimeFactory`, Plugin tests; contract: Plugin data is attributed to one Agent/Plugin and is not Core-replaced. This story composes these existing path owners behind a read-only layout and explicit archive boundary.

## 16. Implementation Steps

1. Add failing tests for data-location ownership/sensitivity and the supported backup-set exclusion of credentials and temporary/unsafe files → verify: `uv run --offline pytest tests/test_operations.py -k 'location or ownership or sensitive or credential or exclude'`
2. Implement `DataLayout` and deterministic supported-file enumeration with configured-root, symlink, file-type, and permission checks → verify: `uv run --offline pytest tests/test_operations.py -k 'layout or enumerate or symlink or path or supported'`
3. Implement versioned archive creation with relative members, manifest sizes/digests, restrictive output handling, and no credential values → verify: `uv run --offline pytest tests/test_operations.py -k 'backup or archive or manifest or digest or credential'`
4. Implement full preflight validation, staged non-destructive restore, explicit overwrite rejection, and truthful restore outcomes → verify: `uv run --offline pytest tests/test_operations.py tests/test_sessions.py -k 'restore or checksum or traversal or duplicate or preserve or overwrite'`
5. Add CLI data-location, backup, and restore commands with plain output, validation/dry-run behavior, and secret-free failure handling → verify: `uv run --offline pytest tests/test_operations_cli.py -k 'location or backup or restore or dry or invalid or secret'`
6. Run the complete archive, path-security, compatibility, quality, and packaging checks with no new security findings in affected paths → verify: `uv run --offline pytest tests/test_operations.py tests/test_operations_cli.py tests/test_sessions.py tests/test_plugins.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv build --offline && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e09s02-P0-01: Locations expose ownership without secrets

```gherkin
Given a configured Mia data root with Agent, Session, Plugin, diagnostic, and credential paths
When an operator requests the data layout
Then each category reports its owning boundary, path, sensitivity, and backup eligibility
And credential values are never returned and credentials are marked excluded
```

### Scenario SC-e09s02-P0-02: Backup is supported and integrity checked

```gherkin
Given valid Agent definitions, append-only Sessions, Plugin state/data, diagnostics, credential files, and temporary/unsafe files
When an operator creates a backup
Then the archive contains only the supported non-credential dataset
And its versioned manifest contains relative paths, sizes, and digests
And source bytes and valid Session order remain unchanged
```

### Scenario SC-e09s02-P0-03: Restore validates before commit

```gherkin
Given a valid archive or one with traversal, symlink, duplicate, missing, stale-version, or checksum-invalid members
When an operator requests restore into an explicit destination
Then Core validates the complete archive before writing
And invalid archives are rejected without partial destination data or source mutation
And a valid archive commits atomically without implicit overwrite
```

### Scenario SC-e09s02-P1-04: Operators can complete a safe round trip

```gherkin
Given a supported local dataset in an isolated home
When an operator inspects locations, creates a backup, validates it, and restores it to a fresh destination
Then each command returns truthful status and plain actionable output
And Agent, Session, Plugin, and diagnostic data are restored byte-for-byte
And credential values are absent from the archive and output
```

## 18. Verification Script (Step-by-Step)

1. Create an isolated Agent root with one Agent definition, Session JSONL file, Plugin data file, diagnostic file, credential file, and orphan temporary file.
2. Run data-location inspection and verify category ownership, paths, sensitivity, and backup eligibility.
3. Create a backup in a new output path and inspect its manifest and member list for relative names, sizes, digests, and excluded credential/temp files.
4. Tamper with a digest, add a traversal member, and attempt restore; verify no destination commit occurs and the source remains unchanged.
5. Restore the untampered archive into a fresh destination and compare supported file bytes and Session ordering.
6. Attempt restore into a non-empty destination without explicit replacement and confirm rejection rather than overwrite.

## 19. Risks and Mitigations

- **Credential export:** define the supported backup set explicitly and assert credential sentinel absence in archive bytes, manifest, and CLI output.
- **Path traversal/symlink escape:** reject unsafe member names and links before extraction; never delegate trust to archive defaults.
- **Partial restore:** validate into a staging directory and commit only after every member passes.
- **Data loss through overwrite:** reject non-empty destinations and require a separate explicit policy for any future replacement.
- **Format drift:** version the manifest and reject unknown versions; do not guess archive semantics.

## 20. Definition of Done and Slopcheck

- All four scenarios pass through public layout, backup, restore, Session, Plugin, and CLI boundaries.
- Supported data can be archived and restored with integrity evidence, while credentials remain excluded.
- Invalid archives fail closed without partial writes or source mutation.
- Every task remains `failing` until its verify command passes during implementation.

### Slopcheck

- `[OK]` Python standard library — archive, hashing, filesystem, and temporary staging operations.
- `[OK]` Pydantic (already installed) — manifest and layout boundary models where needed.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic archive and path tests.
- No backup SDK, cloud service, encryption dependency, or new runtime package is proposed.

### Red-Flag Check

Rejected credential backup, symlink-following extraction, implicit overwrite, automatic deletion, raw directory copying without a manifest, and remote storage.
