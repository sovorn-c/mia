# Security Review — Agent Core Clean Break

- **Branch:** `e06-zero-legacy-agent-core`
- **Scope:** canonical Agent, runtime, Session, access, Plugin, Delegation, CLI, REPL, TUI, and package surfaces
- **Verdict:** PASS — no concrete HIGH or MEDIUM finding was identified in the changed paths.

## Boundary checks

- Agent and Session paths use normalized IDs and Agent-owned roots. Native definitions and state use atomic writes.
- Filesystem Tools reject absolute, traversal, and symlink-resolved paths outside the configured working directory.
- Access policy fails closed for unknown or side-effecting Tools. Read-only Agents receive only non-mutating Tools.
- Approval prompts, events, Sessions, telemetry, and Delegation results sanitize credential-shaped keys and values.
- Full access requires explicit consent and does not disable permanent credential or integrity safeguards.
- Delegation validates recipient eligibility, rejects self-targeting, bounds timeout and depth, intersects capabilities, and keeps payloads secret-free.
- Installed Plugin state and Agent Templates are validated before persistence. Plugins are bundled and explicit; no arbitrary code loading or network fetch is used.
- Notes IDs and roots are confined, symlinks are rejected, and note writes are atomic.
- Provider credentials remain in the credential store and are not copied to Agent definitions, event envelopes, or logs.
- The CLI, REPL, and TUI route through AgentRunner and do not bypass runtime policy or construct a second execution path.

## Verification

The repository-wide `scripts/check-public-surface.sh` scan guards removed names, imports, commands, and package paths without printing file contents beyond safe match locations. The full offline quality gate includes Ruff, Mypy, pytest, coverage, wheel inspection, and YAML parsing.

No new shell interpolation, unsafe deserialization, SQL/HTTP sink, authentication endpoint, dependency, or secret-bearing log was introduced by the clean-break changes.
