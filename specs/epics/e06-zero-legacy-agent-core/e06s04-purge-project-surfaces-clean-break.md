# e06s04 — Project Surface Purge and Clean-Break Gate

- **Story ID:** e06s04
- **Epic:** e06 — Agent Core Clean Break
- **Type:** refactor
- **Risk:** P1
- **Status:** passing

## User story

As a public Mia contributor, I want project guidance, specifications, and package output to describe the same Agent-centric system as the code.

## Goal

Rewrite living guidance and active specifications around Agent, Skill, Tool, Plugin, Task, Delegation, Run, and Session. Remove obsolete repository-only planning and verification artifacts under the Git-history-only rule. Retain Textual and `mia tui`, and leave a repeatable source/package gate.

## Contracts

- `AGENTS.md` and `CLAUDE.md` are byte-for-byte identical and teach the canonical execution path.
- README, product language, architecture, security notes, status metadata, and release metadata reference existing current artifacts.
- User files outside the checkout are never migrated, rewritten, or deleted.
- `pyproject.toml` retains Textual and the wheel retains `mia_cli/tui/`.
- `scripts/check-public-surface.sh` fails when a retired symbol, import, command, alias, or package path returns.
- YAML parsing, formatting, lint, type checking, tests, coverage, and wheel build remain offline and reproducible.

## Scope

### In scope

- Rewrite active guidance, product language, architecture, security review, impact, planning, release, and status documents.
- Remove old planning capsules, snapshots, and obsolete verification evidence whose durable value is preserved in Git history.
- Verify package output and retained TUI behavior.

### Out of scope

- New product capabilities or deeper TUI design.
- Changes to Agent, Plugin, Delegation, Session, provider, access, or harness behavior.
- Deletion or migration of user data outside the repository.

## Verification

```bash
cmp -s AGENTS.md CLAUDE.md
./scripts/check-public-surface.sh
uv run --offline python -c "import pathlib,yaml; [yaml.safe_load(p.read_text()) for p in pathlib.Path('specs').rglob('*.yaml')]"
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline mypy src
uv run --offline pytest
./scripts/check-coverage.sh
uv build --offline
```

Wheel inspection must confirm Textual TUI files are present and removed runtime packages are absent. See `specs/verifications/e06s04-verify.yaml` for the final evidence.
