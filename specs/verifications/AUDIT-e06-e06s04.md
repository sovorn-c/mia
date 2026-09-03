# Audit Code — e06s04

- **Branch:** `e06-zero-legacy-agent-core`
- **Story:** e06s04 — Project Surface Purge and Clean-Break Gate
- **Verdict:** PASS
- **Scope:** canonical runtime, Agent registry, CLI/REPL, Textual adapter, package checks, active specifications, and deleted repository-only artifacts.

## Checklist

### Supply chain and security

- ✓ No dependency was added; package metadata, runtime boundaries, and existing Textual packaging remain controlled.
- ✓ No credential, token, authorization header, or secret value was added to the branch.
- ✓ Manual changed-path review covered injection, authorization, path handling, deserialization, credential exposure, and process/network sinks.
- ✓ Existing security review reports no concrete HIGH or MEDIUM finding.
- ✓ Public-surface scan and wheel inspection both pass.

### Provenance and metadata

- ✓ Changed planning and verification artifacts use the active e06 story and current paths.
- ✓ Verification evidence records commands, counts, coverage, package inspection, and known infrastructure exceptions.
- ✓ No release, merge, push, or main-branch change was performed.

### Design, scope, and maintainability

- ✓ Runtime composition remains in AgentRunner and AgentRuntimeFactory; no second execution root was added.
- ✓ CLI/TUI changes remain adapters and preserve the existing shallow TUI scope.
- ✓ Removed repository-only artifacts are limited to the approved purge scope.
- ✓ Deleted dead compatibility paths rather than leaving commented-out code.
- ✓ Changed defaults in the retained TUI now point at the built-in `mia` Agent.
- ✓ No new Fowler smell was introduced. No Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Message Chains, or Middle Man was found in the changed implementation.

### Types and tests

- ✓ Ruff format and lint pass.
- ✓ Mypy passes for all source files.
- ✓ 165 tests pass, including regressions for path boundaries, cancellation, provider failure, redaction, and surface gates.
- ✓ Tests exercise public Agent, runtime, access, Session, Plugin, Delegation, CLI, and TUI boundaries.
- ✓ Coverage passes at 91% scoped first-party and 97% business boundary.

## Findings resolved during audit

1. **Must-fix — unsanitized TUI exception rendering:** the TUI fallback now routes failures through the canonical sanitized error-envelope helper.
2. **Must-fix — specialist construction failure escape:** the research path now wraps specialist runtime construction so failures produce an attributed sanitized error event.
3. **Must-fix — Session and Agent storage boundaries:** traversal, symlinked roots, and final symlink paths now fail closed.
4. **Must-fix — cancellation and provider failures:** cancellation propagates and provider errors cannot produce successful completion events.
5. **Should-fix — retained-TUI defaults and approval:** defaults use `mia`, and side-effect approvals route through the TUI modal.
6. **Should-fix — public gates and metadata:** source, filenames, wheel paths, entry points, and version values are checked consistently.

Targeted regression tests and the full verify-work gate passed after these fixes. The terminal evidence is recorded in `specs/verifications/e06s04-verify.yaml`.

## Accepted exceptions

- Optional Bigpowers helper scripts are absent from this checkout. Direct repository checks and manual evidence were used; the exception is recorded in `specs/security/EXCEPTIONS.md` and `specs/state.yaml`.
- `CONVENTIONS.md` is not present in this worktree. The project-root copy was read from the main checkout without modifying it; branch guidance remains byte-identical between `AGENTS.md` and `CLAUDE.md`.
- The retained CLI modules exceed the ideal file-size heuristic, but both were reduced by this branch and a further split is outside e06s04 scope.

## Rationalizations checked

None. No failed product gate was dismissed as pre-existing or unrelated; missing helper infrastructure is explicitly recorded as an accepted environment exception.
