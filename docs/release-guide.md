# Mia Operator Release & Publication Guide

This document is the canonical operator runbook for verifying, authorizing, publishing, and superseding Mia distribution artifacts.

---

## 1. Release Architecture & Principles

Mia follows a fail-closed, verified distribution model:

1. **Exact-Candidate Verification**: Publication requires matching the project version in `pyproject.toml`, the Git commit ref, and cryptographic SHA-256 hashes in `dist/release-manifest.json`.
2. **Explicit Authorization Boundary**: Publication is never triggered automatically by branch pushes, pull requests, or Git tags. Publication requires explicit operator action (`--authorized` or `MIA_RELEASE_AUTHORIZED=1`).
3. **Secret-Safe Execution**: Build and release logs redact tokens, credentials, and sensitive environment variables.
4. **Immutable Evidence Retention**: Failed publication attempts never delete local artifacts, Git tags, or historical logs. Every attempt records structured evidence.
5. **Clear Trust Boundaries**: Python plugins run in-process and are unsandboxed. Publication does not expand the plugin API beyond `CORE_PLUGIN_API_VERSION = 1`.

---

## 2. Release Candidate Verification Checklist

Before publishing any candidate, execute the full offline verification pipeline:

```bash
# 1. Run the unified 7-step quality gate
bash scripts/check-release-gate.sh

# 2. Build wheels and sdist into dist/
uv build

# 3. Generate cryptographic artifact manifest
python scripts/check-artifact-integrity.py generate --dist-dir dist --version "0.6.0"

# 4. Verify artifact manifest and checksums
python scripts/check-artifact-integrity.py verify --dist-dir dist --version "0.6.0"

# 5. Check public surface and forbidden legacy paths
python scripts/check-artifact-integrity.py check-surface --dist-dir dist

# 6. Execute clean-install smoke test in isolated site
python scripts/check-artifact-integrity.py smoke --dist-dir dist

# 7. Perform release candidate dry-run check
python scripts/release.py verify --dist-dir dist --version "0.6.0"
```

If any step fails, publication is refused immediately.

---

## 3. Publication Procedure

### A. Local / Manual Publication (Authorized Operator)

When publishing manually from an authorized release workstation:

```bash
# Verify dry-run first
python scripts/release.py verify --dist-dir dist --version "0.6.0"

# Execute authorized publication
export UV_PUBLISH_TOKEN="<pypi-token>"
python scripts/release.py publish --dist-dir dist --version "0.6.0" --authorized
```

The script verifies:
- Artifact hashes match `dist/release-manifest.json` exactly.
- Candidate version matches `pyproject.toml`.
- Explicit `--authorized` flag or `MIA_RELEASE_AUTHORIZED=1` is present.
- All logs and stderr output redact `UV_PUBLISH_TOKEN` or credential patterns.

### B. CI Protected Workflow Publication

The GitHub Actions release workflow `.github/workflows/release.yml` is restricted to manual execution (`workflow_dispatch`) within the protected `release` environment:

1. Navigate to **Actions** -> **Release**.
2. Click **Run workflow**.
3. Set `version` (e.g., `0.6.0`).
4. Set `authorized` to `true` (default is `false`).
5. Set `dry_run` to `false` for actual release.
6. Trigger the workflow.

---

## 4. Failure Handling & Recovery Runbook

Every failed publication attempt records structured diagnostics to `dist/release-attempt.json` without deleting wheels, sdists, manifests, or Git tags.

The failure record classifies the incident into one of three recovery states:

### 1. RETRY (Transient Network / Gateway Failure)
- **Condition**: Network timeout, socket reset, or HTTP 502/503/504 before package upload completed.
- **Action**:
  1. Inspect `dist/release-attempt.json` to confirm the upload was aborted before registry acceptance.
  2. Verify network connectivity to PyPI.
  3. Re-run `python scripts/release.py publish --dist-dir dist --version "0.6.0" --authorized`.

### 2. WITHDRAW (Partial or Corrupted Publication)
- **Condition**: One artifact (e.g., wheel) succeeded but another failed, or a critical flaw was detected immediately post-publication.
- **Action**:
  1. Do NOT delete local artifacts or attempt to overwrite the same version.
  2. Log in to PyPI or use `twine`/API to mark the uploaded version as **yanked**:
     ```bash
     # PyPI yanking marks the version as unavailable to resolvers while retaining immutability
     # Follow PyPI web console: Project Settings -> Releases -> Manage -> Yank release
     ```
  3. Document the reason for withdrawal in release notes or an incident report.
  4. Preserve `dist/release-attempt.json` for audit traceability.
  5. Proceed to **SUPERSEDE**.

### 3. SUPERSEDE (Permanent Version Conflict / Fixed Release)
- **Condition**: Registry rejects upload due to duplicate version (HTTP 400/409), or a withdrawn release must be replaced. PyPI forbids re-uploading identical file names or versions.
- **Action**:
  1. Bump the patch version in `pyproject.toml` (e.g. `0.6.0` -> `0.6.1`).
  2. Document the change in `RELEASE_NOTES.md` under the new version header, referencing the superseded version.
  3. Re-run `bash scripts/check-release-gate.sh` and `uv build`.
  4. Generate a new manifest: `python scripts/check-artifact-integrity.py generate --dist-dir dist --version "0.6.1"`.
  5. Publish the superseding candidate:
     ```bash
     python scripts/release.py publish --dist-dir dist --version "0.6.1" --authorized
     ```

---

## 5. Security & Trust Boundaries

- **Secret Safety**: Tokens and authorization headers are never echoed in logs or error messages.
- **Plugin Sandbox Limits**: Mia core does not sandbox Python plugins. Plugins execute inside the same Python process as Mia. Operators must review and trust any plugin before installing it into their environment.
- **API Stability**: Third-party plugins target `CORE_PLUGIN_API_VERSION = 1` via `mia.plugins` entry points.
