# Mia v0.6.0 Release Candidate Notes

## Overview

Mia v0.6.0 establishes the verified production release-candidate baseline for Mia, a lightweight, modular local Agent core. Implementation and candidate verification are complete; formal publication and release closure remain pending. This release consolidates core Agent runtime capabilities, deterministic testing harness, onion-style middleware pipeline, session history trees, and complete distribution assurance.

## Key Highlights

### 1. Unified Agent Runtime & Execution Pipeline
- **Headless Agent Harness (`src/mia_agent/harness.py`)**: Asynchronous, deterministic, typed event loop supporting one durable Agent identity per execution turn.
- **Nervous System Middleware (`src/mia_middleware/pipeline.py`)**: Onion-style Tool middleware providing security boundaries, auditing, and cost controls across all Tool calls.
- **Provider Contracts (`src/mia_ai/`)**: Async streaming contracts across providers, including deterministic `MockProvider` for offline test suites.
- **Append-Only Sessions (`src/mia_agent/session/`)**: Durable JSONL session trees preserving complete trajectory history without rewriting.

### 2. Release & Distribution Assurance (Epic e11)
- **Specification & Quality Gate**:
  - Fail-closed specification validator (`scripts/check-spec-consistency.py`) enforcing schema validity and planning consistency across all epics.
  - Unified 7-stage quality gate (`scripts/check-release-gate.sh`) verifying formatting, linting, type-checking, complete test suites, coverage thresholds, and public API surface.
  - Parity CI workflow (`.github/workflows/ci.yml`) validating matrix tests across Python 3.12, 3.13, and 3.14.
- **Artifact Integrity & Packaging**:
  - SHA-256 artifact manifest generation and verification (`scripts/check-artifact-integrity.py`).
  - Strict package surface inspection banning legacy profiling, mode catalogs, or herd runtime remnants.
  - Clean-installation smoke test running in an isolated execution environment without repository source checkouts on `sys.path`.
- **Authorized Publication & Recovery Procedure**:
  - Fail-closed release orchestrator (`scripts/release.py`) requiring explicit operator authorization (`--authorized` or `MIA_RELEASE_AUTHORIZED=1`).
  - Dry-run verification mode by default.
  - Secret-safe redaction preventing credential or token leakage in logs and stdout/stderr.
  - Durable failure evidence retention (`dist/release-attempt.json`) with structured recovery states (`RETRY`, `WITHDRAW`, `SUPERSEDE`).
  - Protected manual GitHub Actions workflow (`.github/workflows/release.yml`) triggered only via `workflow_dispatch`.

## Compatibility & Trust Boundaries

- **Core Plugin API**: Supported interface version is locked to `CORE_PLUGIN_API_VERSION = 1` via `src/mia_agent/plugin_models.py`. Discovered entry points reside under entry point group `mia.plugins`.
- **Unsandboxed Trusted Plugins**: Note that third-party Python plugins run in-process with the host interpreter permissions and are unsandboxed. Mia relies on the operator to install only trusted plugins.
- **System Requirements**: Requires Python 3.12+ (tested on 3.12, 3.13, 3.14). Built and distributed with `uv`.

## Publication & Operator Runbook

For operator instructions on verifying candidates, authorizing releases, handling failures, and executing withdrawals or supersessions, consult [`docs/release-guide.md`](docs/release-guide.md).
