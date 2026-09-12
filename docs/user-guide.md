# Mia User Guide

This guide covers everything you need to install, configure, operate, and customize Mia for local agent execution and terminal workflows.

## Table of Contents

- [Installation](#installation)
- [Provider Credentials](#provider-credentials)
- [Your First Run](#your-first-run)
- [Agent Management](#agent-management)
- [Sessions and Models](#sessions-and-models)
- [Access Policies and Tool Approvals](#access-policies-and-tool-approvals)
- [Interactive REPL and Keyboard Operation](#interactive-repl-and-keyboard-operation)
- [Plain Output and Motion Safety](#plain-output-and-motion-safety)
- [Related Guides](#related-guides)

---

## Installation

Mia requires Python 3.12 or newer. We recommend using `uv` for fast, reproducible dependency management:

```bash
# Clone the repository
git clone https://github.com/sovorn-c/mia.git
cd mia

# Synchronize virtual environment dependencies
uv sync
```

To verify your installation and view available commands:

```bash
uv run mia --help
```

---

## Provider Credentials

Mia uses a machine-global credential store located at `~/.mia/credentials.json`. Credentials stay isolated from Agent definitions and Session histories; Agent files only record provider references, never raw keys.

To store an API key for your chosen provider (e.g., Anthropic, OpenAI, DeepSeek):

```bash
# Interactive login prompt
uv run mia login anthropic

# Or pass the key explicitly
uv run mia login anthropic --key <your-api-key>
```

Supported providers include `anthropic`, `openai`, `deepseek`, and others configured in your provider catalog.

---

## Your First Run

Execute a single prompt through the default `mia` Agent in headless streaming mode:

```bash
uv run mia run -p "List files in the current directory and explain their purpose"
```

To run a prompt with a specific named Agent:

```bash
uv run mia run --agent mia -p "Explain how the session trees work"
```

---

## Agent Management

An **Agent** is a durable, named identity that owns its system instructions, model preferences, capability allowlists, and access policies.

### Creating an Agent

```bash
uv run mia agent create researcher \
  --name "Researcher" \
  --tools read_file,bash \
  --instructions "Analyze repository architecture and summarize technical documents."
```

### Listing Agents

```bash
uv run mia agent list
```

### Inspecting an Agent

```bash
uv run mia agent show researcher
```

### Setting the Default Agent

```bash
uv run mia agent use researcher
```

### Deleting an Agent

```bash
uv run mia agent delete researcher
```

---

## Sessions and Models

### Managing Sessions

Mia stores append-only JSONL session trees under `~/.mia/sessions/`. Every turn and branch is safely preserved.

- **List saved Sessions:**
  ```bash
  uv run mia sessions list --agent researcher
  ```
- **Inspect a Session:**
  ```bash
  uv run mia sessions show <session_id>
  ```
- **View a Session Tree:**
  ```bash
  uv run mia sessions tree <session_id>
  ```
- **Resume a Session in headless mode:**
  ```bash
  uv run mia run --resume <session_id> -p "Continue our previous analysis"
  ```
- **Resume a Session in the interactive REPL:**
  ```bash
  uv run mia --session <session_id>
  ```

### Selecting Models

You can specify a model override per command or turn:

```bash
uv run mia run --model claude-3-7-sonnet-20250219 -p "Refactor this function"
```

Inside the interactive REPL, switch models at any time with `/model <model_id>`.

---

## Access Policies and Tool Approvals

Mia mediates all Tool execution through a strict security middleware pipeline. Every Agent operates under one of three explicit access policies:

1. **`read-only`** — The Agent can read files and inspect state, but all mutating Tools and external effects are blocked.
2. **`approval-required` (Default)** — Safe read actions run automatically, but any mutating action (file writes, edits, shell execution, delegation) prompts the user for explicit approval before running.
3. **`full-access` (Explicit Opt-In)** — Mutating actions execute without per-call approval prompts. Permanent security guards (path traversal blocks, credential protection) remain strictly enforced.

When a Tool requires approval in the CLI or REPL, you will see a prompt:

```text
Agent mia requests file-write Tool write_file.
Approve this Tool call? [y/N]:
```

---

## Interactive REPL and Keyboard Operation

Start the full interactive REPL by running `mia` without a subcommand:

```bash
uv run mia
```

### Essential Keyboard Controls

| Context | Key / Command | Action |
|---|---|---|
| **REPL** | `Enter` | Submit prompt (idle only) |
| **REPL** | `Ctrl+J` or `Alt+Enter` | Insert newline for multiline prompt |
| **REPL** | `Ctrl+C` or `Esc` | Clear prompt / Cancel active turn without dropping draft |
| **REPL** | `Esc` or `/help` | Help & command discovery |
| **REPL** | `Ctrl+L` or `/model` | Switch active model selector |
| **REPL** | `Ctrl+P` or `/model next` | Cycle scoped models |
| **REPL** | `Ctrl+Q` or `/queue <text>` | Queue one explicit follow-up during a Run; `/queue` is the portable fallback |
| **REPL** | `Ctrl+O` or `/inspect` | Inspect turn audit log |
| **REPL** | `Ctrl+T` or `/thinking` | Toggle model reasoning trace |
| **REPL** | `Esc Esc` or `/tree` | Session tree navigator |
| **REPL** | `/quit`, `/exit`, or `Ctrl+D` | Exit REPL cleanly |
| **Tool Approval** | `y` in the approval focus | Approve Tool execution; draft characters cannot authorize |
| **Tool Approval** | `n` or `Esc` in the approval focus | Reject or cancel Tool execution |

`Enter` while a Run is active only preserves an ordinary draft. Use `Ctrl+Q` or `/queue <text>` for an explicit single follow-up. A queued follow-up runs only after a successful Run; cancellation or failure restores it to the draft.

---

## Plain Output and Motion Safety

For users using screen readers, piping output into files, running CI automation, or working in reduced-motion environments, Mia provides an accessible **plain presentation mode**.

### Activating Plain Mode

Plain mode can be activated in three ways:

1. **Explicit CLI flag:**
   ```bash
   uv run mia run -p "Run test suite" --plain
   ```
2. **Environment variable:**
   ```bash
   NO_COLOR=1 uv run mia run -p "Run test suite"
   ```
3. **Automatic non-TTY detection:**
   Whenever standard output is redirected or piped (e.g. `uv run mia run -p "..." > run.log`), plain mode activates automatically.

### Plain Mode Features

- **No ANSI escape sequences:** Output is strictly ASCII/UTF-8 readable text without terminal control characters.
- **Motion safety:** All animated braille spinners, cycling dot animations, and live screen redraws (`rich.live.Live`) are completely suppressed.
- **Static semantic status labels:** Progress and terminal outcomes are explicitly labeled:
  - `[tool pending] [running] <tool_name> <summary>` — Tool execution started.
  - `[tool completed] [ok] <tool_name> <summary> (<time>ms)` — Tool completed successfully.
  - `[tool error] [error] <tool_name> <summary>` — Tool failed with an error.
  - `[tool cancelled] [cancelled] <tool_name> <summary>` — Tool did not complete.
  - `[tool expanded] <call_id>` — A bounded, secret-redacted retained result is visible.
  - `[cancelled] Turn halted by user (Ctrl+C).` — Turn interrupted.
  - `[attention] Approval required: ...` — Security approval needed.
  - `[ok] Turn completed in <time>s, [<steps>] | $<cost>` — Terminal turn summary.

---

## Related Guides

- **[Operator Guide](operator-guide.md)** — Diagnostics, data locations, backup/restore, and non-destructive recovery.
- **[Plugin Author Guide](plugin-author-guide.md)** — Governed Core extension host, Plugin trust model, and contribution lifecycles.
- **[Documentation Index](README.md)** — Overview of all documentation resources.
- **[Project README](../README.md)** — Repository root and quality gate reference.
