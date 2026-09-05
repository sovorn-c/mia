# Mia Operator Guide

This guide describes operational maintenance, telemetry diagnostics, data ownership and sensitivity, backup and restore procedures, recovery verification, and non-destructive troubleshooting for Mia administrators and operators.

## Table of Contents

- [Operational Diagnostics](#operational-diagnostics)
- [Data Locations, Ownership, and Sensitivity](#data-locations-ownership-and-sensitivity)
- [Backup and Restore Procedures](#backup-and-restore-procedures)
- [Recovery Verification and Non-Destructive Limits](#recovery-verification-and-non-destructive-limits)
- [Troubleshooting Common Faults](#troubleshooting-common-faults)
- [Related Guides](#related-guides)

---

## Operational Diagnostics

Mia emits structured diagnostic events across tool executions, agent runs, and plugin lifecycles. Diagnostic records are completely secret-free and scrubbed of sensitive tokens.

### Inspecting Diagnostics

List recent operational diagnostic records:

```bash
uv run mia diagnostics list
```

### Filtering Diagnostics

Narrow diagnostic inquiries using targeted filters:

```bash
# Filter by source: 'tool', 'run', or 'plugin'
uv run mia diagnostics list --source tool

# Filter by named Agent
uv run mia diagnostics list --agent researcher

# Filter by Run ID
uv run mia diagnostics list --run <run_id>

# Filter by Session ID
uv run mia diagnostics list --session <session_id>

# Limit output record count (default: 50)
uv run mia diagnostics list --limit 20
```

---

## Data Locations, Ownership, and Sensitivity

Mia stores local state in well-defined categories with explicit sensitivity classifications. Inspect all managed local data locations using:

```bash
uv run mia data locations
```

### Local Storage Hierarchy

| Category | Typical Path | Sensitivity | Owned By | Backup Policy |
|---|---|---|---|---|
| **Agent Definitions** | `~/.mia/agents/` | Medium | AgentManager | Included in backups |
| **Session Trees** | `~/.mia/sessions/` | Medium-High | SessionStore | Included in backups |
| **Plugin Extensions** | `~/.mia/plugins/` | Low-Medium | PluginManager | Included in backups |
| **Diagnostics** | `~/.mia/diagnostics/` | Low | DiagnosticStore | Included in backups |
| **Provider Credentials** | `~/.mia/credentials.json` | **Critical** | CredentialStore | **Strictly Excluded** |

### Credential Separation Invariant

Provider credentials (API keys, authentication tokens) are stored in machine-global credential files with restricted file permissions (`0600`). They are logically and physically separated from Agent configurations and Session histories. Backup operations **never** package credentials into archives to prevent accidental key exposure.

---

## Backup and Restore Procedures

### Creating an Integrity-Checked Backup

Create a versioned, compressed archive containing all supported local state (Agents, Sessions, Plugins, and Diagnostics):

```bash
uv run mia data backup --output /backups/mia-backup-2026-09-05.tar.gz
```

During backup creation:
1. All files are checked for read locks and atomic write completion.
2. A manifest detailing item counts, SHA-256 digests, and format versions is generated.
3. Sensitive credential stores are actively skipped and guarded.

### Validating and Restoring Data

Restore a previously created backup archive into a target directory:

```bash
uv run mia data restore /backups/mia-backup-2026-09-05.tar.gz --destination ~/.mia/
```

During restore:
1. **Archive Integrity Check:** Verifies checksums against the internal manifest before writing any files.
2. **Path Safety Guard:** Prevents path traversal (`../`) attacks by rejecting any archive member pointing outside the designated destination.
3. **Collision Protection:** Refuses to overwrite existing files unless explicitly specified by the operator.

---

## Recovery Verification and Non-Destructive Limits

Mia enforces a **non-destructive operational boundary**: diagnostic and verification tooling only reads and assesses state; it never speculatively repairs, mutates, or deletes data without explicit operator direction.

### Running Recovery Verification

To run deterministic, read-only recovery checks across all local storage categories:

```bash
uv run mia data verify
```

`mia data verify` inspects:
- **Session JSONL Integrity:** Validates that each line contains well-formed JSON and matching parent hashes.
- **Interrupted-Write Detection:** Checks for orphaned `.tmp` files resulting from interrupted atomic write operations.
- **Manifest Consistency:** Confirms that Agent definitions match catalog schemas and referenced tools exist.

Verification exits with code `0` when all local data is clean and valid, or non-zero with actionable diagnostics when anomalies are detected.

---

## Troubleshooting Common Faults

### Interrupted Writes

If a process was forcefully terminated during a write operation (e.g. system power loss), Mia's atomic write pattern leaves a `.tmp` file behind while leaving the canonical destination intact. Run `mia data verify` to pinpoint any orphaned files.

### Corrupt Data Lines

If an append-only JSONL session file contains a corrupt or truncated trailing line, Mia's session loader logs a diagnostic record and gracefully isolates the intact history prefix. Corrupted records are not silently deleted.

### Unknown or Unsupported Data Formats

When opening state created by a newer version of Mia, legacy components cleanly report unsupported schema versions instead of failing catastrophically.

---

## Related Guides

- **[User Guide](user-guide.md)** — Day-to-day operation, command reference, and accessibility.
- **[Plugin Author Guide](plugin-author-guide.md)** — Plugin architecture, trust boundaries, and lifecycle.
- **[Documentation Index](README.md)** — Complete index of available documentation.
- **[Project README](../README.md)** — Repository root, public interface, and quality gate.
