# e11s03 — Authorized Publication and Supersession Procedure

## 1. Identity

- **Story ID:** e11s03
- **Epic:** e11 — Release and Distribution Assurance
- **Type:** release
- **Risk:** P1
- **Context:** publication authorization, release notes, failure handling, withdrawal, supersession, and secret-safe operator procedure
- **BCPs:** 4
- **Status:** done
- **Requirement delta:** ADDED

## 2. User Story

As a Mia release maintainer, I want a documented and explicitly authorized publication procedure with safe failure and supersession handling so that artifacts are never published by accident and an incomplete release can be withdrawn or replaced without losing evidence.

## 3. Context

The repository targets a local Python distribution and currently has no release workflow, release notes, or publication/withdrawal runbook. e11s01 supplies the quality gate and e11s02 supplies artifact/provenance evidence. The release scope explicitly excludes automatic publication and requires authorization, failure handling, withdrawal, and supersession guidance.

## 4. Problem

Without a release procedure, maintainers may publish the wrong version, publish without the required quality/artifact evidence, expose registry credentials in logs, or respond to a partial publication by deleting evidence or guessing at recovery. A manual command alone does not establish an authorization boundary or a durable operator record.

## 5. Goal

Add a secret-safe release command/workflow and concise release documentation that require explicit approval, verify version/ref/artifact provenance before publication, preserve evidence on failure, and define controlled withdrawal or supersession steps. Tests must exercise dry-run and refusal paths only; they must never contact a registry.

## 6. Non-Goals

- Actual PyPI/registry publication during build or test.
- Automatic publishing on push, arbitrary registry support, hosted deployment, or release-service integration.
- Credential storage, token rotation, signing infrastructure, or package-manager behavior beyond the existing `uv publish` command.
- Deleting artifacts, tags, or evidence as an automatic recovery action.

## 7. Stakeholders

- Release maintainers who authorize publication.
- Operators handling failed or partial publication.
- Users needing version, compatibility, and supersession information.
- Security reviewers checking authorization and secret-safe logs.

## 8. Dependencies

- e11s01 aggregate quality/specification gate.
- e11s02 artifact manifest, package checks, clean-install smoke, and provenance evidence.
- `pyproject.toml` version, `uv publish`, Git tags/refs, GitHub Actions protected environments, and current release scope/docs.
- No new runtime dependency and no network publication in tests.

## 9. Assumptions

- Publication requires both an explicit operator action and an authorized environment/approval; a normal branch push or tag alone is insufficient.
- The release artifact directory and provenance manifest are immutable inputs to the publish attempt.
- A failed publication preserves local artifacts and logs a sanitized result for retry, withdrawal, or supersession decision.
- Withdrawal/supersession instructions identify the affected version and artifact without deleting valid local evidence.

## 10. Constraints

- Refuse publication when version, tag/ref, artifact hash, package surface, or required gate evidence does not match.
- Never print registry tokens, authorization headers, credential values, or full environment dumps.
- Default commands are dry-run/verification; publication requires an explicit approval signal and protected CI environment where applicable.
- No automatic deletion, overwrite, rollback of user data, or silent version correction.
- Documentation must state that trusted Python Plugins remain unsandboxed and that publication does not expand the Plugin API.

## 11. Domain Model

- **Release Candidate:** version/ref plus verified artifact set and provenance evidence.
- **Publication Authorization:** explicit operator/environment approval allowing a publish attempt.
- **Publication Attempt:** one attributable command invocation with sanitized result and preserved evidence.
- **Withdrawal:** controlled operator response for an already exposed bad artifact/version.
- **Supersession:** publishing or selecting a newer verified version while retaining evidence and documenting the replaced version.
- **Release Runbook:** durable operator instructions for verification, authorization, failure, withdrawal, and supersession.

## 12. Requirements

### ADDED: Explicit publication authorization

The release command/workflow MUST refuse to publish unless the candidate passes the e11 quality and artifact gates, the requested version/ref and provenance match, and the operator supplies explicit authorization through the documented protected-environment or equivalent approval boundary. Ordinary CI and tag events MUST not publish.

### ADDED: Secret-safe publication and failure evidence

Each publication attempt MUST return a truthful result, preserve artifacts and sanitized evidence on failure, and exclude tokens, credentials, authorization headers, and private environment values from output. A failed attempt MUST not be represented as a successful release.

### ADDED: Withdrawal and supersession runbook

The release documentation MUST define how to identify an affected version, stop or withdraw an unsafe publication where registry policy permits, preserve evidence, produce a verified superseding release, and communicate compatibility/known-limit impact without deleting historical records.

## 13. Non-Functional Requirements

- **Authorization:** no implicit or push-triggered publication.
- **Integrity:** publish only the exact verified artifact manifest and version/ref.
- **Security:** logs and release notes are secret-free and do not promise sandboxing.
- **Recoverability:** failed/partial publication leaves enough evidence for a deliberate retry, withdrawal, or supersession decision.
- **Auditability:** each attempt records version, artifact identity, gate result, authorization mode, and sanitized outcome.

## 14. Contracts

### Existing contracts preserved

- `pyproject.toml` remains the authoritative project version and package metadata.
- `uv publish` is used only as the final publication mechanism after local authorization and prior gates.
- e11s01 and e11s02 commands remain the required preconditions; this story does not duplicate or weaken them.
- Release scope, Plugin trust, and supported package/API limits remain those documented in `specs/product/SCOPE_LATEST.yaml` and `specs/tech-architecture/tech-stack.md`.

### New contracts

- `scripts/release.py` (or the repository's equivalent) supports verification/dry-run and explicitly authorized publication/refusal/failure outcomes.
- `.github/workflows/release.yml` is manual/protected and cannot publish from ordinary push or pull-request events.
- `docs/release-guide.md` and `RELEASE_NOTES.md` document v0.6.0 scope, provenance, compatibility, authorization, failure, withdrawal, and supersession.

## 15. Reason for Depth and Zoom-Out

This story adds a release-facing command and workflow around existing package metadata and verification outputs. `pyproject.toml` owns the version and package identity; its callers are the build and publish tools, and its contract is exact version metadata. e11s01 owns pre-release quality evidence and e11s02 owns artifact evidence; their callers are the release procedure and CI, and their contracts are truthful pass/fail and immutable artifact identity. The new release command must orchestrate those contracts, not recreate them or introduce a hosted release service. The protected authorization boundary is required because `uv publish` is an effectful external operation.

## 16. Implementation Steps

1. Add failing tests for version/ref/artifact mismatch, missing gate evidence, absent authorization, dry-run behavior, and secret-safe refusal → verify: `uv run --offline pytest tests/test_release_process.py -k 'authorization or mismatch or dry or refusal or secret'`
2. Implement release-candidate verification and explicit authorization checks before any `uv publish` invocation → verify: `uv run --offline pytest tests/test_release_process.py -k 'authorization or mismatch or dry or refusal or secret'`
3. Add truthful failure-result persistence plus withdrawal and supersession state/runbook handling without deleting artifacts or evidence → verify: `uv run --offline pytest tests/test_release_process.py -k 'failure or withdraw or supersede or evidence'`
4. Add manual/protected release workflow, v0.6.0 release notes, and operator guide with supported limits and secret-safe examples → verify: `uv run --offline pytest tests/test_release_process.py -k 'workflow or notes or documentation or links'`
5. Run the dry-run release procedure and complete release checks without contacting a registry or exposing credentials → verify: `uv run --offline pytest tests/test_release_process.py && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e11s03-P0-01: Publication requires authorization and exact evidence

```gherkin
Given a release candidate with quality and artifact evidence
When publication is requested without explicit authorization, with a mismatched version/ref, or with stale artifact hashes
Then publication is refused before contacting the registry
And the result identifies the missing or mismatched precondition without exposing secrets
```

### Scenario SC-e11s03-P1-02: Release documentation is complete and honest

```gherkin
Given the v0.6.0 release notes and operator runbook
When a maintainer follows them
Then they can identify scope, package/API compatibility, provenance, trust boundaries, known limits, and authorization steps
And the documentation does not promise sandboxing, automatic publication, or unsupported registries
```

### Scenario SC-e11s03-P1-03: Publication failure is recoverable

```gherkin
Given a publication attempt that fails or partially exposes a version
When the maintainer applies the documented recovery procedure
Then artifacts and sanitized evidence remain available
And the procedure distinguishes retry, withdrawal, and supersession
And no historical evidence or user data is automatically deleted
```

### Scenario SC-e11s03-P2-04: Workflow and runbook are internally consistent

```gherkin
Given manual release workflow inputs and documented commands
When offline release-process validation runs
Then versions, paths, links, dry-run commands, and authorization requirements agree
And ordinary push/pull-request workflows cannot publish
```

## 18. Verification Script (Step-by-Step)

1. Run the release command in dry-run mode with a synthetic candidate and confirm it performs all precondition checks.
2. Omit authorization, alter the version/ref, and alter an artifact hash; confirm each request is refused before any publish call.
3. Run a simulated failed publication and inspect the retained sanitized evidence and actionable next-step classification.
4. Read the release guide and notes to confirm scope, package/API compatibility, Plugin trust limits, and no-sandbox/no-auto-publish statements.
5. Inspect the manual release workflow to confirm protected/manual triggers and no publication path from pull requests or ordinary pushes.
6. Confirm tests run without registry credentials or network publication.

## 19. Risks and Mitigations

- **Accidental publication:** require both explicit command authorization and a protected environment; keep CI quality workflows non-publishing.
- **Wrong artifact:** verify exact version/ref/hash manifest immediately before publish.
- **Secret leakage:** pass only required token variables to the publish subprocess and sanitize all captured output.
- **Irrecoverable partial release:** preserve artifacts/evidence and document retry, withdrawal, and supersession separately.
- **Overpromised support:** derive notes from the approved scope and architecture; state unsandboxed trusted Python and registry limits.

## 20. Definition of Done and Slopcheck

- Dry-run/refusal/recovery tests, release command/workflow, release notes, and operator runbook exist.
- All tasks start `status: failing` and flip only after their checks pass.
- Tests never contact a registry; actual publication remains an explicitly authorized operator action.
- Failure, withdrawal, and supersession preserve evidence and do not delete user data.

### Slopcheck

- `[OK]` Python standard library — argument validation, manifest checks, sanitized subprocess handling, and local evidence.
- `[OK]` uv — existing build/publish tool; publication remains gated and is not invoked by tests.
- `[OK]` GitHub Actions protected/manual workflow — repository infrastructure with explicit permissions.
- No new registry SDK, release platform, signing service, or runtime dependency is proposed.

### Red-Flag Check

The plan does not publish during tests, equate a tag with authorization, delete evidence after failure, add registry-specific abstractions, or claim that trusted Plugin code is sandboxed.
