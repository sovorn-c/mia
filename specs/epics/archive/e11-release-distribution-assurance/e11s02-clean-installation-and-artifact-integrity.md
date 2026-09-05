# e11s02 — Clean Installation and Artifact Integrity

## 1. Identity

- **Story ID:** e11s02
- **Epic:** e11 — Release and Distribution Assurance
- **Type:** infra
- **Risk:** P0
- **Context:** sdist/wheel construction, package surface, Plugin API compatibility, provenance, hashes, and isolated installation
- **BCPs:** 5
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As a Mia maintainer, I want to verify the exact distributable artifacts in a clean environment so that a release is based on installable, version-matched packages rather than a successful source-checkout test alone.

## 3. Context

`pyproject.toml` declares the `mia-ai` distribution, Hatchling build backend, Python 3.12+ support, package directories, and a public `mia` entry point. `scripts/check-wheel-surface.py` already checks retained and retired package paths, while `src/mia_agent/plugin_models.py` defines `CORE_PLUGIN_API_VERSION` and `src/mia_agent/plugins.py` discovers the allowlisted Plugin entry-point group. No release artifact manifest, tamper check, or clean-install smoke contract currently binds these surfaces together.

## 4. Problem

A source-tree test run can pass while a wheel omits a package, contains a retired module, has mismatched metadata, cannot discover an installed Plugin, or is not reproducibly attributable to the source and lock state. Without a pre-install integrity check, tampered or incomplete artifacts can progress toward publication.

## 5. Goal

Build sdist and wheel artifacts into an isolated output, generate and verify a versioned provenance/hash manifest, inspect package and Plugin API surfaces, and install-smoke the artifacts in a temporary supported environment without importing the source checkout. Detect tampering or mismatch before the artifact is accepted.

## 6. Non-Goals

- Publishing to PyPI or any registry; publication authorization belongs to e11s03.
- Changing the runtime Plugin contract, adding a package manager, or installing arbitrary remote dependencies.
- Guaranteeing byte-identical builds across all operating systems when build metadata is outside repository control; the contract is deterministic verification and explicit provenance.
- OS/process sandboxing or production data migration.

## 7. Stakeholders

- Maintainers producing release artifacts.
- Users installing Mia from a wheel or source distribution.
- Plugin authors relying on the public API version and entry-point contract.
- Security reviewers checking package contents, hashes, and provenance.

## 8. Dependencies

- e11s01 local quality/specification gate.
- `pyproject.toml`, `uv.lock`, Hatchling, uv, `scripts/check-wheel-surface.py`, and current package surface tests.
- `mia_agent.plugin_models.CORE_PLUGIN_API_VERSION`, `PluginManifest`, `PluginHost`, and `discover_entry_points`.
- A temporary virtual environment and cached/locked dependencies; no network registry is required for tests.

## 9. Assumptions

- The source commit/ref, project version, lock-file digest, artifact filename, size, and SHA-256 are sufficient local provenance for v0.6.0; signing is outside this epic.
- The clean-install fixture may use a locally staged test Plugin distribution with a synthetic entry point and no secret values.
- The package smoke command uses `mia --help` and non-mutating Agent, Session, Template, and Plugin inspection commands.
- Artifact verification occurs before any publication command and rejects mismatches rather than repairing them.

## 10. Constraints

- Inspect sdist and wheel members before installation; reject missing required packages, retired paths, duplicate entries, unexpected executable files, and version mismatch.
- Artifact and provenance manifests contain no credentials or private user paths.
- Installation tests must not resolve imports from the repository's `src/` directory and must not modify the operator's home or Session data.
- Plugin compatibility must use the existing public API version and allowlisted entry-point group; do not broaden contribution authority.
- Do not use a registry or claim successful publication as part of this story.

## 11. Domain Model

- **Source Release:** versioned source and lock state selected for packaging.
- **Distribution Artifact:** sdist or wheel emitted by the configured build backend.
- **Artifact Manifest:** versioned record of artifact kind, version, source/ref, size, and SHA-256.
- **Package Surface:** required and forbidden paths and metadata exposed by an artifact.
- **Clean Installation:** isolated environment whose import path does not include the source checkout.
- **Installed Plugin:** synthetic or bundled Plugin discovered through the existing entry-point contract and validated by Core.

## 12. Requirements

### ADDED: Versioned artifact provenance and integrity

The release process MUST produce a versioned artifact manifest containing artifact type, project version, source/ref identity, lock/build context, file size, and cryptographic digest. Verification MUST reject missing, mismatched, or tampered artifacts before installation or release acceptance.

### ADDED: Distribution package and Plugin API surface check

The release process MUST verify that sdist and wheel metadata match the release version, the wheel contains required Mia packages and the retained TUI surface, retired package paths are absent, and the declared public Plugin API version remains compatible.

### ADDED: Clean installed-environment smoke

The release process MUST install the locally built artifact into an isolated supported environment with the source checkout unavailable on `sys.path`, then verify the CLI entry point and non-mutating Agent, Session, Template, and Plugin inspection paths. An installed test Plugin MUST be discoverable through the existing allowlisted entry-point contract without a Mia Core edit.

## 13. Non-Functional Requirements

- **Integrity:** SHA-256 and manifest metadata are checked before install or publish.
- **Reproducibility:** build inputs and artifact identity are explicit and inspectable.
- **Security:** no credential values, registry tokens, or private home paths enter artifacts, manifests, or logs.
- **Compatibility:** package names, entry points, retained TUI paths, and `CORE_PLUGIN_API_VERSION` remain aligned.
- **Isolation:** temporary build/install homes are cleaned or retained only as explicit evidence; user data is untouched.

## 14. Contracts

### Existing contracts preserved

- `pyproject.toml` remains the package/build source of truth.
- `scripts/check-wheel-surface.py` continues to reject forbidden wheel paths and symbols.
- `CORE_PLUGIN_API_VERSION`, `PluginManifest`, and `discover_entry_points` remain the supported Plugin API/discovery boundary.
- The `mia` console script remains the supported installed entry point.

### New contracts

- `scripts/check-artifact-integrity.py` (or the repository's equivalent) verifies artifact manifests, hashes, metadata, and package contents before acceptance.
- A clean-install smoke command proves package operation without source-checkout imports.
- A test-only installed Plugin fixture proves entry-point discovery and API compatibility through the public host.

## 15. Reason for Depth and Zoom-Out

This story modifies the release boundary around existing package and Plugin contracts, not the Plugin runtime itself. `pyproject.toml` owns distribution metadata and package inclusion; its callers are Hatchling/uv and install tooling, and its contract is the declared version, entry point, and package set. `check-wheel-surface.py` owns wheel path/symbol checks; its callers are tests and release gates, and its contract is fail-closed package-surface validation. `plugins.py` owns entry-point discovery; its callers are PluginManager/PluginHost and tests, and its contract is the allowlisted group with Core validation. The artifact verifier must compose these contracts without introducing a second package or extension system.

## 16. Implementation Steps

1. Add failing tests for artifact manifest shape, version/source/lock identity, SHA-256 verification, tampering, and package-member rejection → verify: `uv run --offline pytest tests/test_release_artifacts.py -k 'manifest or hash or tamper or version or member'`
2. Implement artifact manifest generation and fail-closed sdist/wheel inspection using `hashlib`, `tarfile`, and `zipfile` → verify: `uv run --offline pytest tests/test_release_artifacts.py -k 'manifest or hash or tamper or version or member'`
3. Add package-surface and Plugin API compatibility checks around the existing wheel checker and `CORE_PLUGIN_API_VERSION`/entry-point contract → verify: `uv run --offline pytest tests/test_release_artifacts.py -k 'surface or plugin or api or entry_point'`
4. Add isolated clean-install smoke coverage for the installed CLI, non-mutating inspection commands, and a synthetic installed Plugin with source imports excluded → verify: `uv run --offline pytest tests/test_release_artifacts.py -k 'install or smoke or entry_point'`
5. Run the full artifact, package-surface, clean-install, and repository quality checks without new security findings in affected paths → verify: `uv run --offline pytest tests/test_release_artifacts.py tests/test_surface_checks.py && uv build --offline && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e11s02-P0-01: Release artifacts are attributable and integrity checked

```gherkin
Given a versioned source/ref and locked dependency state
When a maintainer builds an sdist and wheel
Then each artifact receives a manifest with kind, version, source/ref, size, and SHA-256
And a missing, mismatched, or tampered artifact is rejected before installation or release acceptance
```

### Scenario SC-e11s02-P0-02: Package and Plugin surfaces match the contract

```gherkin
Given a built sdist and wheel for v0.6.0
When the release artifact checker inspects them
Then required Mia packages and the retained TUI surface are present
And retired paths/symbols and version mismatches are rejected
And the declared Plugin API version remains compatible
```

### Scenario SC-e11s02-P0-03: Clean installation works outside the source checkout

```gherkin
Given a locally built artifact and an isolated supported environment
When the artifact is installed with the source checkout unavailable on sys.path
Then the mia entry point and non-mutating inspection smoke paths run successfully
And no operator home, credential, or Session data is changed
```

### Scenario SC-e11s02-P1-04: Installed Plugin discovery remains compatible

```gherkin
Given a synthetic test-only distribution exposing the allowlisted Plugin entry-point group
When the installed Mia package inspects and activates it through the public contract
Then the Plugin is attributable and API-compatible without editing Mia Core
And no unsupported contribution or secret-bearing metadata is accepted
```

### Scenario SC-e11s02-P1-05: Tampering blocks acceptance

```gherkin
Given an artifact or provenance manifest with changed bytes, size, digest, version, or source identity
When verification runs
Then it exits non-zero before installation or publication
And it reports the mismatch without printing credentials
```

## 18. Verification Script (Step-by-Step)

1. Build sdist and wheel into a new temporary output directory.
2. Generate and inspect the artifact manifest for version, source/ref, size, and SHA-256.
3. Run wheel and sdist surface checks and confirm required/forbidden package paths.
4. Modify a copy of an artifact or manifest and confirm verification rejects it before install.
5. Create a temporary virtual environment, install the local artifact, and run `mia --help` plus non-mutating inspection commands with the source checkout excluded.
6. Install or stage the synthetic test Plugin and confirm its entry point, manifest, API version, and attribution are accepted.

## 19. Risks and Mitigations

- **Source-checkout masking:** remove repository paths from the clean smoke environment and assert imported module locations.
- **Incomplete wheel:** inspect every required/forbidden path and compare metadata before install.
- **Tampered artifact:** hash the exact bytes and verify size/digest before any install or publish step.
- **Plugin contract drift:** use the public API version and an installed entry-point fixture rather than importing a source test double.
- **Credential leakage:** use sentinel values and assert absence from manifests, logs, and package contents.

## 20. Definition of Done and Slopcheck

- Artifact manifest/integrity verifier, package/API checks, clean-install smoke, and focused tests exist.
- All tasks start `status: failing` and flip only after their commands pass.
- The artifact gate rejects tampering and source-checkout masking before acceptance.
- No registry publication occurs in this story.

### Slopcheck

- `[OK]` Python standard library — `hashlib`, `tarfile`, `zipfile`, `venv`, and subprocess isolation.
- `[OK]` Hatchling and uv — existing build and environment tooling.
- `[OK]` Pydantic and existing Plugin host — current public boundary, not a new extension framework.
- No new runtime package, signing service, cloud storage, or package manager is proposed.

### Red-Flag Check

The plan does not equate source tests with installability, trust an archive without inspecting members, run a registry publish as a test, or broaden the Plugin API to make the fixture pass.
