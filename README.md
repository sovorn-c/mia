# Mia — Local Agent Runtime

[![CI](https://github.com/sovorn-c/mia/actions/workflows/ci.yml/badge.svg)](https://github.com/sovorn-c/mia/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

> [!IMPORTANT]
> Pre-1.0, source-install only. Configuration and APIs will evolve before the first stable release.

## Why Mia?

Most agent frameworks treat identity as a prompt — a blob of text prepended to every request, discarded when the session ends. That works until you want the same Agent to reason consistently across days, own a stable set of Tools, accumulate a history it can branch and resume, and hand bounded sub-tasks off to other Agents without re-injecting the entire context each time.

Mia makes the **Agent** the durable unit, not the prompt.

Each Agent owns its instructions, model preferences, Tool allowlist, access policy, Plugins, and an append-only Session tree — all stored locally under `~/.mia/`. Swap the prompt; the identity stays.

## Architecture

```text
CLI / REPL
    │
    ▼
AgentRunner
    │
    ▼
AgentRuntimeFactory
    │
    ▼
AgentHarness ──────────────────────► Provider stream
    │
    ├──► Agent-filtered Tools ─► Security ─► Approval ─► Audit ─► Cost
    │
    ├──► Append-only Session store
    │
    └──► Governed Plugin contributions
```

Every Tool call passes through an **onion-style middleware pipeline** — security check, per-call approval, audit record, cost control — regardless of whether the Tool comes from core or a Plugin. The Agent's allowlist is applied before the pipeline sees the Tool at all.

| Package | Responsibility |
|---|---|
| `mia_agent` | Agent runtime, configuration, auth, Sessions, Plugins, orchestration |
| `mia_ai` | Async streaming contracts and provider adapters |
| `mia_middleware` | Onion-style Tool middleware and policy enforcement |
| `mia_tools` | Confined filesystem and process Tools |
| `mia_cli` | Typer commands, interactive REPL, and terminal rendering |

The harness (`src/mia_agent/harness.py`) is headless and UI-independent. The CLI, a future TUI, or a test suite all attach to the same loop.

## Core concepts

| Concept | What it is |
|---|---|
| **Agent** | A named, durable identity: instructions, model, Tools, policy, Plugins, Sessions |
| **Run** | One execution of an Agent against a prompt |
| **Session** | Append-only JSONL conversation tree — branches and resumes across Runs |
| **Tool** | A callable capability, filtered by the Agent and enforced by middleware |
| **Plugin** | A declared extension that contributes Tools, Skills, or Agent Templates |
| **Delegation** | A bounded sub-task routed to another eligible Agent through Mia Core |

## Quickstart

**Requirements:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/), API key for at least one supported provider.

```bash
# 1. Clone and install
git clone https://github.com/sovorn-c/mia.git
cd mia
uv sync --locked

# 2. Add credentials
uv run mia login anthropic   # or openai, deepseek, gemini, openrouter

# 3. Run
uv run mia
```

Inside the REPL, `/model` selects from available models for your provider. `/help` lists all shortcuts.

**Headless / scripted:**

```bash
uv run mia run --agent mia --model "$MODEL_ID" \
  --prompt "Summarize this repository and suggest the next task"

# Static output (no ANSI, safe for pipes and CI)
uv run mia run --plain --model "$MODEL_ID" --prompt "Review the current changes"
```

## Built-in Agents

| Agent | Purpose | Access policy |
|---|---|---|
| `mia` | General local work and reasoning | `approval-required` |
| `coding` | Software development with filesystem and shell Tools | `approval-required` |
| `architect` | Read-only architecture exploration | `read-only` |
| `minimal` | Direct conversation, no Tools | `approval-required` |
| `research` | Evidence-focused local research | `read-only` |

```bash
uv run mia agent list
uv run mia agent show coding
uv run mia --agent architect
```

## Access policies

| Policy | Behaviour |
|---|---|
| `read-only` | Inspection only — mutating Tools and external effects are blocked |
| `approval-required` | Safe reads run automatically; writes, shell commands, and delegation require approval *(default)* |
| `full-access` | Allowed mutating Tools run without per-call approval — requires explicit opt-in |

## Custom Agents

```bash
uv run mia agent create docs-researcher \
  --name "Documentation Researcher" \
  --access read-only \
  --tools read_file \
  --instructions "Analyze local documentation, separate evidence from assumptions, cite file paths."

uv run mia agent use docs-researcher   # make it the default
```

`mia agent show` and `mia agent delete` manage saved Agents. Built-in Agents cannot be overwritten or deleted.

## Sessions

History lives in `~/.mia/sessions/` as append-only JSONL. Runs add turns; they never rewrite earlier history.

```bash
uv run mia sessions list --agent mia

# Resume headless
uv run mia run --resume SESSION_ID --model "$MODEL_ID" --prompt "Continue"

# Resume interactive
uv run mia --session SESSION_ID
```

## Providers

Native Anthropic adapter; OpenAI and OpenAI-compatible streaming for everything else.

Supported out of the box: **Anthropic, OpenAI, DeepSeek, Gemini (OpenAI-compatible endpoint), OpenRouter, custom OpenAI-compatible endpoints.**

OpenAI Codex OAuth: start `uv run mia`, enter `/login oauth`, then pick a model with `/model`.

> Provider requests leave your machine. Review the prompt, attached context, and your provider's data policy before sending sensitive material.

## Plugins

Plugins contribute typed Tools, static Skills, and Agent Templates through declared entry points. They run in-process and are not sandboxed — install only Plugins you trust.

```bash
uv run mia plugin list
uv run mia template list
uv run mia plugin install notes
uv run mia template create notes-agent notes
```

Plugin Tools still pass through the full middleware pipeline. See [Plugin Author Guide](docs/plugin-author-guide.md).

## Local data and backup

```bash
uv run mia data locations   # every data path with sensitivity classification
uv run mia data backup --output ./mia-backup.tar.gz
uv run mia data verify
```

Credentials (`~/.mia/credentials.json`) are excluded from backups. Restore validates checksums before writing.

## Security boundaries

Mia is local-first but not a security sandbox:

- Agent access policies restrict which Tools run and when approval fires.
- Filesystem Tools are confined to their configured working directory.
- Credentials are stored separately and omitted from diagnostics and backups.
- Trusted-code Plugins execute in-process with the host interpreter's permissions.
- `full-access` removes per-call approval for allowed Tools and must be enabled deliberately.

## Development

```bash
uv sync --locked
uv run mia --help

# Quality gate (run before any commit)
uv run --offline ruff format .
uv run --offline ruff check .
uv run --offline mypy src
uv run --offline pytest
uv build --offline
```

Tests use the deterministic `MockProvider` for offline Agent-loop coverage. CI runs the full gate across Python 3.12, 3.13, and 3.14.

## Contributing

Issues and focused pull requests are welcome. For large changes, open an issue first to agree on intended behaviour and trust boundaries.

1. Preserve the single `AgentRunner → AgentRuntimeFactory → AgentHarness` execution path.
2. Test through public interfaces, including error paths and edge cases.
3. Run the quality gate.
4. Do not include credentials, private prompts, Session content, or other sensitive local data.

[GitHub Issues](https://github.com/sovorn-c/mia/issues)

## Documentation

- [User Guide](docs/user-guide.md)
- [Operator Guide](docs/operator-guide.md)
- [Plugin Author Guide](docs/plugin-author-guide.md)
- [Release Notes](RELEASE_NOTES.md)

## License

MIT
