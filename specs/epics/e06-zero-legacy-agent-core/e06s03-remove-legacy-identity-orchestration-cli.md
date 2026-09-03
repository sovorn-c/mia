# e06s03 — Canonical Runtime and CLI Surface

- **Story ID:** e06s03
- **Epic:** e06 — Agent Core Clean Break
- **Status:** passing
- **Risk:** P0

## User story

As a public Mia contributor, I want one Agent schema, registry, runtime, CLI, REPL, and Session path so the shipped system has one clear identity model.

## Delivered contract

- `Agent` accepts canonical fields only, validates secret-free metadata, and supports only `read-only`, `approval-required`, and `full-access`.
- `AgentManager` resolves built-in and native persisted Agents, persists atomically, and stores Sessions below each Agent home.
- `AgentRunner` and `AgentRuntimeFactory` are the only prompt composition path.
- CLI and REPL expose Agent, Session, Plugin, Template, authentication, and model operations.
- Textual uses `AgentManager` and `AgentRunner` without constructing runtime internals.
- Session metadata contains Agent, Run, Task, and Session attribution without alternate identity fields.
- Delegation, Plugins, access middleware, redaction, and failure/cancellation behavior remain intact.

## Verification

```bash
./scripts/check-public-surface.sh
uv run --offline pytest
./scripts/check-coverage.sh
uv build --offline
```

See `specs/verifications/e06s03-verify.yaml` for the completed story evidence.
