# e11s01 — Reproducible Release Quality and Specification Gate

## 1. Identity

- **Story ID:** e11s01
- **Epic:** e11 — Release and Distribution Assurance
- **Type:** infra
- **Risk:** P0
- **Context:** local release gate, specification integrity, CI parity, public surface, and security-sensitive regression checks
- **BCPs:** 4
- **Status:** planned
- **Requirement delta:** ADDED

## 2. User Story

As a Mia maintainer, I want one deterministic local and CI quality gate so that a release cannot appear healthy when its specifications, code quality, coverage, public surface, or security-sensitive checks are failing.

## 3. Context

The repository already contains separate checks such as `scripts/check-coverage.sh`, `scripts/check-public-surface.sh`, and `scripts/check-wheel-surface.py`, but no single release-gate entry point or repository-wide specification-consistency validator. The accepted security exception in `specs/security/EXCEPTIONS.md` also records that the checkout lacks a dedicated scanner, so the release gate must make the existing deterministic checks explicit rather than imply coverage from an unavailable tool.

## 4. Problem

Maintainers must remember and order several commands manually. Release metadata can drift from execution status or capsule paths without a fail-closed check, and CI has no repository-defined workflow that proves it runs the same checks as local verification. A green partial command set is not sufficient evidence for v0.6.0 release approval.

## 5. Goal

Provide a single offline-capable local gate that validates release specifications and runs the existing formatting, lint, strict typing, tests, scoped coverage, public-surface, and security-sensitive regression checks in a fail-closed order. Add CI configuration that invokes the same gate on supported Python versions without publishing or requiring credentials.

## 6. Non-Goals

- Artifact construction, clean installation, Plugin API package smoke, or publication; those belong to e11s02 and e11s03.
- A new security scanner, hosted dashboard, remote telemetry, or third-party quality service.
- Changing Agent, Plugin, Session, credential, Tool, or frontend runtime behavior.
- Suppressing or relabeling a failed existing check.

## 7. Stakeholders

- Maintainers deciding whether a release is ready.
- Contributors receiving fast pull-request feedback.
- Security reviewers relying on public-surface, secret-free, and regression evidence.
- Release automation consuming one stable gate command.

## 8. Dependencies

- Delivered e07–e10 runtime, operations, accessibility, and documentation contracts.
- `specs/release-plan.yaml`, `specs/execution-status.yaml`, active/archive epic manifests, and `specs/state.yaml`.
- Existing `scripts/check-coverage.sh`, `scripts/check-public-surface.sh`, `pyproject.toml`, Ruff, mypy, pytest, uv, and PyYAML dev tooling.
- GitHub Actions as the CI execution environment inferred from the repository remote.
- No new runtime dependency.

## 9. Assumptions

- The local gate is the source command reused by CI and later release verification.
- Existing check scripts remain authoritative for their domains; the new gate orchestrates them instead of duplicating their logic.
- Specification validation treats archived capsules as historical records but validates their release-plan references and YAML syntax.
- CI may use a network-enabled runner to provision supported Python versions, but the repository checks themselves remain runnable with the locked/offline project environment where applicable.

## 10. Constraints

- Any failed command produces a non-zero gate result and stops later release acceptance.
- The gate must never print credentials, tokens, or full sensitive environment values.
- The validator must reject malformed YAML, duplicate epic/story IDs, missing capsule manifests, mismatched status/BCP/dependency data, and invalid active-capsule task references.
- CI must run quality checks only; it must not publish artifacts or mutate user data.
- Preserve the existing `solo-git` workflow and Python 3.12+ support.

## 11. Domain Model

- **Release Plan:** ordered source of release epic identity, dependencies, status, BCPs, and capsule paths.
- **Execution Status:** delivery projection containing epic/story progress and task counters.
- **Epic Capsule:** manifest, story specifications, and task ledgers for one epic.
- **Quality Gate:** ordered fail-closed command boundary whose exit status is release evidence.
- **Security-Sensitive Check:** deterministic public-surface, documentation secret-scan, or regression check that must not be skipped silently.

## 12. Requirements

### ADDED: Deterministic specification consistency validation

The repository MUST provide an offline-capable command that parses all specification YAML and verifies release-plan, execution-status, epic manifest, dependency, BCP, status, story, and capsule-path consistency. It MUST return non-zero with actionable file and key context for malformed or conflicting state.

### ADDED: Single fail-closed local release gate

The repository MUST provide one command that runs specification validation, formatting, lint, strict typing, full tests, scoped coverage, public-surface checks, and other configured security-sensitive regression checks in a documented order. Any failure MUST produce a non-zero result and MUST NOT be reported as release-ready.

### ADDED: CI parity without publication

A checked-in CI workflow MUST invoke the same repository gate for pull requests and protected branch changes on the supported Python matrix. CI MUST not publish, access release credentials, or silently continue after a required check fails.

## 13. Non-Functional Requirements

- **Determinism:** validation and gate ordering are stable and use pinned project configuration.
- **Security:** output is secret-safe; no external scanner or credential is implied when unavailable.
- **Portability:** scripts work on the supported local shell/runner environment and use existing tools.
- **Observability:** failures identify the command, artifact, or specification key that failed.
- **Compatibility:** existing scripts and thresholds remain intact unless a documented release requirement changes them.

## 14. Contracts

### Existing contracts preserved

- `scripts/check-coverage.sh` remains the owner of scoped coverage thresholds and exits non-zero below them.
- `scripts/check-public-surface.sh` remains the owner of retired public-surface detection.
- Ruff, mypy, pytest, and uv commands remain the project's configured quality tools.
- `specs/release-plan.yaml` and `specs/execution-status.yaml` retain their respective source-of-truth responsibilities.

### New contracts

- `scripts/check-spec-consistency.py` (or the repository's equivalent) returns zero only when all release metadata relationships are valid.
- `scripts/check-release-gate.sh` (or the repository's equivalent) is the one documented local/CI quality command and fails closed.
- `.github/workflows/ci.yml` invokes the gate on supported Python versions for pull requests and protected branch changes.

## 15. Reason for Depth and Zoom-Out

This story composes existing release scripts rather than introducing a second quality framework. `scripts/check-coverage.sh` exists to enforce scoped statement and business-boundary thresholds; its callers are maintainers and future CI/release workflows, and its contract is a non-zero result below threshold. `scripts/check-public-surface.sh` exists to prevent removed public identities from returning; its callers are current regression tests and release gates, and its contract is fail-closed output. The new validator and orchestrator must preserve those contracts while adding the missing cross-artifact boundary. A new external scanner or workflow framework would add depth without evidence.

## 16. Implementation Steps

1. Add failing fixture tests for YAML parsing, release/status/capsule identity, dependency and BCP drift, and active task-ledger shape → verify: `uv run --offline pytest tests/test_release_gate.py -k 'spec or yaml or status or dependency or bcp'`
2. Implement the deterministic specification-consistency command with actionable non-zero failures and archived-capsule awareness → verify: `uv run --offline pytest tests/test_release_gate.py -k 'spec or yaml or status or dependency or bcp'`
3. Compose the fail-closed local gate around specification validation, Ruff, mypy, pytest, coverage, public-surface, and configured security-sensitive checks → verify: `uv run --offline pytest tests/test_release_gate.py -k 'gate or order or failure or secret'`
4. Add the pull-request and protected-branch CI workflow that invokes the same gate on the supported Python matrix without publication permissions → verify: `uv run --offline pytest tests/test_release_gate.py -k workflow`
5. Run the complete local gate and record clean command output as the story verification baseline → verify: `bash scripts/check-release-gate.sh`

## 17. Acceptance Criteria

### Scenario SC-e11s01-P0-01: Required release checks fail closed

```gherkin
Given a repository with one required quality command configured to fail
When the maintainer runs the release gate
Then the gate exits non-zero and identifies the failed command
And it does not report a release-ready result
```

### Scenario SC-e11s01-P0-02: Specification relationships are validated

```gherkin
Given release, execution, active-capsule, archived-capsule, and task-ledger YAML files
When the maintainer runs specification validation
Then valid files and relationships pass
And malformed YAML, duplicate IDs, missing capsules, status drift, dependency drift, or BCP drift fail with actionable context
```

### Scenario SC-e11s01-P1-03: CI has local-gate parity

```gherkin
Given a pull request or protected branch change on a supported Python version
When CI starts
Then it invokes the documented local release gate
And no CI job publishes artifacts or requires release credentials
```

### Scenario SC-e11s01-P1-04: Security-sensitive checks remain explicit

```gherkin
Given retired public names or credential-shaped documentation content
When the corresponding release checks run
Then the check fails without printing the secret value
And the aggregate gate remains blocked
```

## 18. Verification Script (Step-by-Step)

1. Run the specification validator against the repository's release and execution metadata.
2. Create a temporary malformed or mismatched fixture and confirm the validator returns non-zero with the affected key.
3. Run `bash scripts/check-release-gate.sh` and confirm the output identifies each ordered check.
4. Inspect `.github/workflows/ci.yml` and confirm pull-request/protected-branch triggers, supported Python matrix, and no publication step.
5. Review failure output for absence of credentials or full environment values.

## 19. Risks and Mitigations

- **Gate drift:** CI could call a different command; make the workflow invoke the exact local gate script.
- **False consistency:** archived history could be mistaken for active work; distinguish archive paths while validating their referenced identity.
- **Secret leakage:** subprocess output could expose environment values; allow only command names and sanitized stderr through the wrapper.
- **Unavailable scanner:** do not claim a scanner exists; make deterministic existing checks and the accepted exception explicit.
- **Slow feedback:** keep fixture tests small and put full coverage/build checks in the aggregate gate.

## 20. Definition of Done and Slopcheck

- Specification validator, aggregate gate, CI workflow, and focused tests exist.
- All tasks start with `status: failing`; implementation flips them only after commands pass.
- The local gate and CI use the same required command order and fail-closed semantics.
- No runtime dependency or new security service is proposed.

### Slopcheck

- `[OK]` Python standard library and existing PyYAML dev dependency — validation and subprocess orchestration.
- `[OK]` Existing Ruff, mypy, pytest, coverage, and uv — already configured project tools.
- `[OK]` GitHub Actions workflow syntax — repository CI infrastructure, not a runtime dependency.
- No `[SUS]` or `[SLOP]` package is proposed.

### Red-Flag Check

The plan does not add a second test framework, skip coverage/public-surface checks, treat CI green as publication authorization, or claim a missing security scanner.
