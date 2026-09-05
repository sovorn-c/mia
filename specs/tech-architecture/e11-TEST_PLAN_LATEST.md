# Test Design: e11-release-distribution-assurance

## 1. Risk Matrix & Scenarios

| Scenario ID | Behavior Description | Risk | Test Level | Target File/Module |
|---|---|---:|---|---|
| SC-e11s01-P0-01 | The release gate runs the required checks in a deterministic order and fails closed on the first failing command | P0 | Integration | `scripts/check-release-gate.sh`, `tests/test_release_gate.py` |
| SC-e11s01-P0-02 | Specification validation parses every release YAML document and rejects missing, duplicate, stale, or dependency-inconsistent epic/story/capsule entries | P0 | Unit | `scripts/check-spec-consistency.py`, `tests/test_release_gate.py` |
| SC-e11s01-P1-03 | The CI workflow invokes the same offline-capable gate on supported Python versions for pull requests and protected branch changes | P1 | Integration | `.github/workflows/ci.yml`, `tests/test_release_gate.py` |
| SC-e11s01-P1-04 | Public-surface, documentation, and security-sensitive regression checks reject retired interfaces and credential-shaped content without printing secrets | P1 | Integration | `scripts/check-public-surface.sh`, `tests/test_surface_checks.py`, `tests/test_documentation.py` |
| SC-e11s02-P0-01 | A clean source and lock state produces version-matched sdist and wheel artifacts with a deterministic artifact manifest | P0 | Integration | `scripts/check-artifact-integrity.py`, `tests/test_release_artifacts.py` |
| SC-e11s02-P0-02 | The wheel contains the required packages and retained TUI surface, excludes retired packages, and exposes the declared Plugin API version | P0 | Integration | `scripts/check-wheel-surface.py`, `tests/test_release_artifacts.py` |
| SC-e11s02-P0-03 | The built distribution installs into an isolated supported environment and launches the CLI, Agent, Session, Template, and Plugin inspection smoke paths without the source checkout | P0 | E2E | `tests/test_release_artifacts.py`, `src/mia_cli/main.py` |
| SC-e11s02-P1-04 | A test-only installed Plugin discovered through the packaged entry-point contract is compatible, attributable, and visible without editing Mia Core | P1 | E2E | `tests/test_release_artifacts.py`, `src/mia_agent/plugins.py`, `src/mia_agent/plugin_host.py` |
| SC-e11s02-P1-05 | Tampering with an artifact or provenance manifest is detected before installation or release acceptance | P1 | Unit | `scripts/check-artifact-integrity.py`, `tests/test_release_artifacts.py` |
| SC-e11s03-P0-01 | Publication is refused unless the requested version, artifact manifest, tag/ref, and explicit authorization all match | P0 | Unit | `scripts/release.py`, `tests/test_release_process.py` |
| SC-e11s03-P1-02 | Release notes and the release runbook state scope, provenance, supported package surface, trust boundaries, and known limitations without secrets or unsupported promises | P1 | E2E | `RELEASE_NOTES.md`, `docs/release-guide.md`, `tests/test_release_process.py` |
| SC-e11s03-P1-03 | A failed, withdrawn, or superseded publication leaves artifacts and evidence intact and produces an actionable, secret-safe next step | P1 | Integration | `scripts/release.py`, `tests/test_release_process.py` |
| SC-e11s03-P2-04 | Manual release workflow inputs, documentation links, version examples, and dry-run commands are internally consistent | P2 | Unit | `.github/workflows/release.yml`, `tests/test_release_process.py` |

## 2. Fixture Architecture & Isolation

- **Specification fixtures:** Copy small synthetic release-plan, execution-status, and capsule manifests into `tmp_path`; invoke the validator as a subprocess so exit codes and stderr are tested at the public script boundary.
- **Gate fixtures:** Use temporary command stubs or environment-controlled check runners to prove ordering and fail-closed behavior without weakening the real gate. The production gate must call the repository's existing Ruff, mypy, pytest, coverage, public-surface, package-surface, and build commands.
- **Artifact fixtures:** Build into a temporary output directory, inspect sdist members with `tarfile`, wheel members with `zipfile`, and calculate SHA-256 with the standard library. Do not depend on network registries.
- **Clean-install fixtures:** Create an isolated temporary virtual environment and install only the locally built artifact plus cached/locked dependencies. Invoke the installed `mia` entry point and import public Plugin API symbols with the source checkout unavailable on `sys.path`.
- **Plugin fixtures:** Build or stage a minimal test-only installed distribution exposing the existing allowlisted Plugin entry-point group. Its manifest and contribution must use synthetic IDs and no credentials; activation must be observed through the public host contract.
- **Publication fixtures:** Exercise dry-run and refusal paths with temporary artifact directories and synthetic tags/versions. Never contact PyPI or any other registry during tests.
- **Security isolation:** Use sentinel strings such as `SECRET_SENTINEL` only where assertions require them, remove them from output, and never read or mutate the operator's real `~/.mia` data.

## 3. Risk and Level Strategy

P0 scenarios stay at script, package, and installed-environment boundaries because a release gate that is locally green but cannot install or verify the shipped artifact is unsafe. P1 scenarios cover public API compatibility, provenance, publication authorization, and failure evidence. P2 checks remain fast structural validation for workflow and documentation drift. Prefer deterministic temporary directories and subprocess exit-code assertions over network calls, wall-clock timing, registry state, or host-specific paths.

## 4. NFR Verification

| NFR Type | Requirement | Verification Command |
|---|---|---|
| Specification integrity | Release, execution, capsule, dependency, BCP, status, and YAML identities are consistent and fail closed | `uv run --offline pytest tests/test_release_gate.py -k 'spec or yaml or status or dependency'` |
| Quality gate | Formatting, lint, strict typing, tests, scoped coverage, public surface, package surface, and build execute as one ordered gate | `bash scripts/check-release-gate.sh` |
| CI parity | Pull requests and protected branch changes invoke the repository gate on supported Python versions | `uv run --offline pytest tests/test_release_gate.py -k workflow` |
| Artifact integrity | Versioned sdist/wheel manifests contain required files, hashes, provenance, and no retired package paths | `uv run --offline pytest tests/test_release_artifacts.py -k 'manifest or wheel or sdist or hash or surface'` |
| Clean install | A wheel installs and launches supported CLI/package/Plugin smoke checks outside the source checkout | `uv run --offline pytest tests/test_release_artifacts.py -k 'install or smoke or entry_point'` |
| Publication safety | Publish, withdraw, and supersede paths require explicit authorization and never leak credential values | `uv run --offline pytest tests/test_release_process.py -k 'publish or withdraw or supersede or secret or authorization' && printf 'no new security findings in affected paths\n'` |
| Full release gate | All e11 scenarios and existing repository checks pass before release | `uv run --offline pytest tests/test_release_gate.py tests/test_release_artifacts.py tests/test_release_process.py && ./scripts/check-coverage.sh && uv build --offline` |

## 5. Out of Scope

- Actual publication to PyPI or another registry during tests or normal build verification.
- Additional package registries, hosted deployment, containers, remote telemetry, or a release server.
- Operating-system sandboxing of trusted Python Plugins.
- Automated dependency installation, remote Plugin catalogs, or arbitrary project-local Plugin execution.
- Replacing the existing package builder, Agent runtime, Plugin host, or Core security boundary.
- Testing every operating system, terminal emulator, screen reader, registry outage mode, or signing provider.

## 6. Test Data and Security Rules

Use synthetic versions, tags, package names, Plugin IDs, Agent IDs, and sentinel secrets. Assert that API keys, authorization headers, credential-shaped strings, private home paths, and registry tokens are absent from logs, release notes, manifests, and failure output. Publication tests must run with no credentials and prove refusal rather than attempting a network request. Artifact tests must reject traversal, unexpected package paths, mismatched versions, stale hashes, and missing provenance before any install or publication action.

## 7. Exit Criteria

All thirteen scenarios pass through public scripts, package artifacts, an isolated installed environment, and dry-run release paths. The repository gate, scoped coverage, public/wheel surface checks, strict typecheck, full tests, clean build, spec-consistency check, Plugin API compatibility check, and secret-safe publication checks pass. No required release command contacts a registry without explicit authorization, and no critical/high security finding or undocumented production exception remains.
