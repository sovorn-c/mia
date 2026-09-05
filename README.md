# Mia (Modular Intelligent Agent)

Mia is a lightweight local agent system centered on durable, named Agents. Each Agent has its own instructions, model references, capabilities, access policy, and Sessions. Mia starts as the default personal Agent, while coding, research, and specialist work can use named Agents.

## Core boundaries

- **Agent:** durable identity and configuration.
- **Run:** one execution of an Agent.
- **Session:** append-only conversation history owned by an Agent.
- **Tool:** callable capability enforced by the middleware pipeline.
- **Delegation:** one bounded Task assigned to an eligible Agent through Mia Core.
- **Access:** `read-only`, `approval-required`, or `full-access` (explicit opt-in).

Provider credentials stay in the machine-global credential store. Agent files and Sessions contain provider/account references, never credential values. Agent ownership is logical state separation, not an operating-system sandbox.

## Quickstart

```bash
uv sync
mia
mia agent list
mia agent create researcher --name "Researcher" --tools read_file
mia agent use researcher
mia run --agent researcher -p "Review the repository"
```

Running `mia` without an Agent selection starts the built-in `mia` Agent. Its four local coding Tools are available under `approval-required`: reads run automatically, while writes, edits, shell commands, and Delegation require approval. Permanent security guards always remain active.

## Documentation

Comprehensive local documentation is available under `docs/`:

- **[Documentation Index](docs/README.md)** — Architecture overview and navigation map.
- **[User Guide](docs/user-guide.md)** — Installation, credentials, first Run, Agent/Session/model management, access policies, keyboard controls, and accessible output.
- **[Operator Guide](docs/operator-guide.md)** — Diagnostics, data locations and sensitivity, backup/restore, recovery verification, and non-destructive troubleshooting.
- **[Plugin Author Guide](docs/plugin-author-guide.md)** — Governed Core Extension Host, Plugin provenance, static Skills/Templates, typed contributions, lifecycle, and unsandboxed execution boundaries.

## Accessibility and Plain Output

Mia supports motion-safe, static text output without ANSI escape codes for screen readers, redirected logs, and CI pipelines:

```bash
# Explicit --plain flag suppresses live animations and emits semantic status labels
uv run mia run --plain -p "Review recent changes"

# NO_COLOR environment variable automatically activates plain mode
NO_COLOR=1 uv run mia run -p "Review recent changes"
```

## Public interface

The public interface uses `--agent`, `/agent`, and `mia agent create|list|show|use|delete`. Agents own their configuration and Sessions; no alternate identity or execution vocabulary is supported.

Current implementation packages are under `src/`, with deterministic offline tests in `tests/`. Project history is preserved in Git.

## Quality gate

```bash
uv run --offline ruff format .
uv run --offline ruff check .
uv run --offline mypy src
uv run --offline pytest
uv build --offline
```
