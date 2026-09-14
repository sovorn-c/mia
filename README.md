# Mia (Modular Intelligent Agent)

[![CI](https://github.com/sovorn-c/mia/actions/workflows/ci.yml/badge.svg)](https://github.com/sovorn-c/mia/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

**A local-first runtime for durable, named AI Agents.**

Mia brings model access, instructions, Tools, permissions, Plugins, and conversation history together under one Agent identity. Use the built-in Mia Agent for everyday terminal work, or create focused Agents for coding, research, architecture, and other domains.

> [!IMPORTANT]
> Mia is in active pre-1.0 development. Install it from source and expect configuration and command details to evolve between releases.

## What makes Mia different?

Most agent harnesses treat identity as temporary prompt configuration. Mia treats an **Agent** as the durable unit of work.

Each Agent can own or select:

- instructions and model preferences;
- a filtered Tool allowlist;
- an explicit access policy;
- enabled Plugins and Plugin configuration;
- delegation targets;
- append-only Sessions that survive across Runs.

The result is one reusable identity with stable boundaries instead of a new pile of flags for every prompt.

## Highlights

- **Local-first operation** — Agent definitions, Sessions, Plugins, and diagnostics live under `~/.mia/`.
- **Guarded Tool execution** — Every visible Tool passes through security, approval, audit, and cost middleware.
- **Durable Session trees** — Conversation history is append-only and supports branching, resumption, and context compaction.
- **Multiple providers** — Connect Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, OpenAI-compatible endpoints, and other configured providers.
- **Focused Agents** — Start with built-in general, coding, architecture, minimal, and research Agents, or define your own.
- **Governed extensibility** — Plugins can contribute typed Tools, static Skills, and reusable Agent Templates without replacing Mia Core.
- **Agent delegation** — Assign bounded work to eligible Agents through the same governed runtime.
- **Accessible terminal output** — Use motion-safe plain text with semantic status labels for screen readers, pipes, logs, and CI.
- **Operational recovery** — Inspect diagnostics, verify local state, and create integrity-checked backups that exclude credentials.
- **Deterministic development** — Test the full Agent loop offline with the included `MockProvider`.

## The Mia model

> **Agent acts. Skill guides. Tool enables. Plugin extends. Agent delegates through Mia Core.**

| Concept | Role |
|---|---|
| **Agent** | Durable identity containing instructions, model preferences, Tools, permissions, Plugins, and Session ownership. |
| **Run** | One execution of an Agent against a prompt. |
| **Session** | Append-only conversation history that can continue across Runs. |
| **Skill** | Reusable guidance that shapes how an Agent approaches a task. |
| **Tool** | A callable capability filtered by the Agent and enforced by middleware. |
| **Plugin** | A declared extension that contributes Tools, Skills, or Agent Templates. |
| **Delegation** | A bounded task assigned to another eligible Agent through Mia Core. |

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Credentials for a supported model provider

CI runs on Python 3.12, 3.13, and 3.14. Mia currently installs from this repository; no package-registry installation is documented yet.

## Quickstart

### 1. Install from source

```bash
git clone https://github.com/sovorn-c/mia.git
cd mia
uv sync --locked
```

Confirm that the CLI is available:

```bash
uv run mia --help
```

### 2. Add provider credentials

Store an API key using the hidden interactive prompt:

```bash
uv run mia login anthropic
```

Replace `anthropic` with your provider name when needed, such as `openai`, `deepseek`, `gemini`, or `openrouter`.

Credentials are written to `~/.mia/credentials.json` with restricted file permissions. They are kept separate from Agent definitions, Sessions, diagnostics, and backups.

### 3. Start Mia

Launch the interactive terminal interface:

```bash
uv run mia
```

Enter `/model` inside Mia to choose from the available models for your configured provider. This is the simplest first-run path because provider model IDs change over time.

For headless streaming, set `MODEL_ID` to a model shown by the interactive model selector:

```bash
MODEL_ID="your-provider-model-id"
uv run mia run \
  --agent mia \
  --model "$MODEL_ID" \
  --prompt "Summarize this repository and suggest the next useful task"
```

Use `--plain` for static output without ANSI styling or animation:

```bash
uv run mia run --plain --model "$MODEL_ID" \
  --prompt "Review the current changes"
```

## Built-in Agents

Mia includes five starting points:

| Agent | Purpose | Default access |
|---|---|---|
| `mia` | General local work and reasoning | `approval-required` |
| `coding` | Software development with filesystem and shell Tools | `approval-required` |
| `architect` | Read-only architecture exploration and design review | `read-only` |
| `minimal` | Direct conversation without Tools | `approval-required` |
| `research` | Evidence-focused local research | `read-only` |

Inspect them from the CLI:

```bash
uv run mia agent list
uv run mia agent show coding
```

Select one for an interactive Run:

```bash
uv run mia --agent architect
```

## Create your own Agent

Create a durable read-only research Agent:

```bash
uv run mia agent create docs-researcher \
  --name "Documentation Researcher" \
  --access read-only \
  --tools read_file \
  --instructions "Analyze local documentation, separate evidence from assumptions, and cite file paths."
```

Make it the default for future Runs:

```bash
uv run mia agent use docs-researcher
```

Inspect or remove saved Agents with `mia agent show` and `mia agent delete`. Built-in Agents cannot be overwritten or deleted.

## Sessions and interactive work

Mia stores Session history as append-only JSONL under `~/.mia/sessions/`. A Run adds history; it does not rewrite earlier turns.

List Sessions for an Agent:

```bash
uv run mia sessions list --agent mia
```

Resume a Session in headless mode:

```bash
uv run mia run --resume SESSION_ID --model "$MODEL_ID" \
  --prompt "Continue from the previous result"
```

Resume it in the interactive interface:

```bash
uv run mia --session SESSION_ID
```

The interactive interface also provides model selection, Session-tree navigation, Tool inspection, reasoning display, and an explicit follow-up queue. Run `/help` inside Mia for the current shortcuts and commands.

## Access policies and Tool approval

Every Agent uses one explicit access policy:

| Policy | Behavior |
|---|---|
| `read-only` | Allows inspection while blocking mutating Tools and external effects. |
| `approval-required` | Runs safe reads automatically and asks before writes, edits, shell commands, or delegation. This is the default. |
| `full-access` | Runs allowed mutating Tools without per-call approval. It requires explicit opt-in. Permanent guards still apply. |

Tool availability is filtered by the Agent before execution. Visible Tools then pass through Mia's onion-style middleware pipeline for security checks, approval, audit recording, and cost control.

## Providers and models

Mia has a native Anthropic adapter plus OpenAI and OpenAI-compatible streaming adapters. Known provider configuration includes:

- Anthropic
- OpenAI
- DeepSeek
- Gemini's OpenAI-compatible endpoint
- OpenRouter
- OpenCode Go / MiMo
- custom OpenAI-compatible endpoints

Select a model per Run with `--model`, choose one from the interactive `/model` selector, or keep model preferences on a named Agent.

OpenAI Codex subscription access uses a separate OAuth flow. Start `uv run mia`, enter `/login oauth`, complete authentication, and then use `/model` to select an available model.

Provider requests leave your machine. Review the prompt, attached context, and provider's data policy before sending sensitive material.

## Plugins, Skills, and Templates

Mia Core owns Agent execution, Tool authorization, credentials, Sessions, and audit behavior. Plugins extend that runtime through declared, typed contributions.

Explore bundled Plugins and Templates:

```bash
uv run mia plugin list
uv run mia template list
uv run mia template show notes-agent
```

Install the Template's required Plugin, then create an Agent from that Template:

```bash
uv run mia plugin install notes
uv run mia template create notes-agent notes
```

> [!WARNING]
> Trusted-code Plugins run in the Mia process with the host interpreter's permissions. They are not isolated by a container, virtual machine, or operating-system sandbox. Install only Plugins you trust.

Plugin Tools still pass through Mia's Tool filtering and middleware pipeline. See the [Plugin Author Guide](docs/plugin-author-guide.md) for contracts and trust boundaries.

## Local data and recovery

Inspect every Core-owned data location and its sensitivity classification:

```bash
uv run mia data locations
```

Common locations include:

| Data | Default location | Included in backup? |
|---|---|---|
| Agent definitions | `~/.mia/agents/` | Yes |
| Session trees | `~/.mia/sessions/` | Yes |
| Plugins | `~/.mia/plugins/` | Yes |
| Diagnostics | `~/.mia/diagnostics/` | Yes |
| Provider credentials | `~/.mia/credentials.json` | **No** |

Create an integrity-checked backup and verify local state:

```bash
uv run mia data backup --output ./mia-backup.tar.gz
uv run mia data verify
```

Mia excludes provider credentials from backups. Restore validates archive checksums and paths before writing files.

## Architecture

Mia has one native execution path:

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
AgentHarness ───────────────► Provider stream
    │
    ├──► Agent-filtered Tools ─► Security ─► Approval ─► Audit ─► Cost
    │
    ├──► Append-only Session store
    │
    └──► Governed Plugin contributions
```

The main packages are:

| Package | Responsibility |
|---|---|
| `mia_agent` | Agent runtime, configuration, authentication, Sessions, Plugins, and orchestration. |
| `mia_ai` | Streaming provider contracts and adapters. |
| `mia_middleware` | Onion-style Tool middleware and policy enforcement. |
| `mia_tools` | Confined filesystem and process Tools. |
| `mia_cli` | Typer commands, interactive REPL, prompt input, and terminal rendering. |

## Security boundaries

Mia is local-first, but it is not a security sandbox.

- Agent access policies restrict which Tools can run and when approval is required.
- Filesystem Tools are confined to their configured working directory.
- Credentials are stored separately and omitted from diagnostics and backups.
- Session and Agent state can contain sensitive user content; protect `~/.mia/` accordingly.
- Provider calls can transmit prompts and selected context over the network.
- Trusted-code Plugins execute in-process and must come from a trusted source.
- `full-access` removes per-call approval for allowed mutating Tools and should be enabled deliberately.

## Documentation

- [User Guide](docs/user-guide.md) — Installation, credentials, Agents, Sessions, models, access policies, and keyboard controls.
- [Operator Guide](docs/operator-guide.md) — Diagnostics, local data, backup, restore, and recovery.
- [Plugin Author Guide](docs/plugin-author-guide.md) — Plugin contracts, provenance, trust boundaries, and lifecycle.
- [Release Guide](docs/release-guide.md) — Candidate verification, publication, and recovery procedures.
- [Documentation Index](docs/README.md) — Complete documentation map.
- [Release Notes](RELEASE_NOTES.md) — Current release-candidate scope and compatibility notes.

## Development

Clone the repository, synchronize the locked environment, and run the CLI:

```bash
uv sync --locked
uv run mia --help
```

Run the complete quality gate before submitting a change:

```bash
uv run --offline ruff format .
uv run --offline ruff check .
uv run --offline mypy src
uv run --offline pytest
uv build --offline
```

Tests use the deterministic `MockProvider` for offline Agent-loop coverage. CI runs the release gate against supported Python versions.

## Contributing

Issues and focused pull requests are welcome. Before starting a large change, open an issue so the intended behavior and trust boundaries can be agreed first.

When contributing:

1. Keep changes focused and preserve the single `AgentRunner` → `AgentRuntimeFactory` → `AgentHarness` execution path.
2. Add tests through public interfaces, including error paths and meaningful edge cases.
3. Run the complete quality gate.
4. Do not include credentials, private prompts, Session content, or other sensitive local data.

Report defects and feature requests through [GitHub Issues](https://github.com/sovorn-c/mia/issues).

## Project status

Mia's core runtime, guarded Tools, named Agents, Sessions, provider adapters, Plugins, Templates, diagnostics, backup/restore, accessible output, and release checks are implemented and tested.

The project remains pre-1.0 and source-installed. Public package publication and long-term compatibility guarantees are not yet complete.

## License

Mia is licensed under the MIT License.
