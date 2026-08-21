# Master Specification: Mia Production Developer Harness & Interactive CLI

A permanent, version-controlled specification for **Mia (Modular Intelligent Agent)**, following the Solo-Developer SDLC engineering standard.

---

## 1. Domain Architecture & Ubiquitous Language

| Term | Canonical Definition | Role in Mia |
|---|---|---|
| **`MiaREPL`** | The interactive stream-first terminal pair-programming harness. | Primary developer interface (`mia`) |
| **`FileCredentialStore`** | Persistent JSON store under `~/.mia/credentials.json`. | Multi-provider API key storage |
| **`AuthSetupWizard`** | Guided interactive prompt to select provider and save API keys. | In-session `/login` and first-run onboarding |
| **`AgentHarness`** | Deterministic headless async brain executing multi-turn turns. | Execution loop in `src/mia_agent/harness.py` |
| **`RichStreamRenderer`** | Unified terminal renderer for thoughts, tool calls, diffs, and markdown. | Live visual streaming in `src/mia_cli/repl.py` |
| **`ToolPipeline`** | Onion middleware wrapping tool execution with security and telemetry. | Guardrails in `src/mia_middleware/pipeline.py` |

---

## 2. Essential Slash Commands Suite (The Production Standard)

A production-grade coding agent harness requires a comprehensive, instant slash command palette:

| Command | Aliases | Purpose & Execution |
|---|---|---|
| **`/help`** | `/?` | Display the interactive command table, shortcuts, and active tool permissions. |
| **`/login`** | `/auth` | Open the guided interactive setup wizard to configure/switch provider API keys. |
| **`/model`** | `/llm` | Switch active model (`mimo-v2.5`, `gpt-4o`, `deepseek-chat`, `claude-3-5-sonnet`) or view presets. |
| **`/profile`** | `/role`, `/persona` | Switch agent profile (`coding`, `architect`, `code_mode`, `minimal`). |
| **`/diff`** | `/changes` | Run `git diff` on the repository and render Monokai syntax-highlighted code diffs. |
| **`/cost`** | `/tokens`, `/stats` | Display real-time token counts (input, output, reasoning), context utilization %, and USD cost. |
| **`/compact`** | `/compress` | Inspect context window limit and manually trigger structured token compaction. |
| **`/sessions`** | `/history` | List saved JSONL session history trees for current profile. |
| **`/init`** | `/bootstrap` | Scan repository architecture, check active rules, and verify `AGENTS.md`. |
| **`/clear`** | `/cls` | Clear terminal screen and redraw header banner. |
| **`/undo`** | `/revert` | Revert the latest file change made by the agent in this session. |
| **`/quit`** | `/exit` | Save session tree and exit the harness cleanly. |

---

## 3. Interaction Flow & Autocomplete Behavior

```
╭─ 🥕 Mia v0.2.0 (mimo-v2.5) ─────────────────────────────────────────────────────────────╮
│ Directory: /Users/sovorn/dev/harness/mia                                                │
│ Model:     mimo-v2.5  │  Profile: coding  │  Session: session_92f1b4a1                  │
│ Commands:  Type / for menu (/login, /model, /profile, /diff, /cost, /compact, /quit)    │
╰─────────────────────────────────────────────────────────────────────────────────────────╯

🥕 mia > /

╭─ 🥕 Mia Essential Commands ─────────────────────────────────────────────────────────────╮
│ Command              │ Usage & Description                                              │
├──────────────────────┼──────────────────────────────────────────────────────────────────┤
│ /help, /?            │ Show this command menu                                           │
│ /login, /auth        │ Interactive setup wizard to add/update API keys                  │
│ /model [name]        │ View or switch active model (current: mimo-v2.5)                 │
│ /profile [name]      │ View or switch profile (current: coding)                         │
│ /diff, /changes      │ View git diff of session modifications with Monokai syntax       │
│ /cost, /stats        │ Show session tokens (input/output) and estimated USD cost        │
│ /compact, /compress  │ Trigger context compaction summary                               │
│ /sessions, /history  │ List saved JSONL session trees                                   │
│ /init                │ Verify repository AGENTS.md & context                            │
│ /clear, /cls         │ Clear terminal screen                                            │
│ /undo                │ Revert latest file change made during session                    │
│ /quit, /exit         │ Exit Mia session                                                 │
╰──────────────────────┴──────────────────────────────────────────────────────────────────╯
Tip: Type any partial command (e.g. /d, /m, /c) or press Tab to autocomplete.

🥕 mia > 
```

---

## 4. Work Breakdown Slices

### Slice 1: 12-Command Essential Slash Suite (`src/mia_cli/repl.py`)
- [x] **Task 1.1:** Implement `/help`, `/login`, `/model`, `/profile`, `/diff`, `/cost`, `/compact`, `/sessions`, `/init`, `/clear`, `/undo`, `/quit`.
- [x] **Task 1.2:** Add multi-alias support (`/auth`, `/changes`, `/stats`, `/compress`, `/history`, `/cls`, `/exit`, `/?`).
- [x] **Task 1.3:** Build fuzzy prefix matcher: typing `/d` suggests `/diff`, typing `/c` suggests `/cost`, `/compact`, `/clear`.

### Slice 2: Live Shell & Git Integrations (`/diff`, `/undo`, `/init`)
- [x] **Task 2.1:** `/diff` executes `git diff` and formats output via Rich `Syntax(..., "diff", theme="monokai")`.
- [x] **Task 2.2:** `/init` scans directory for `AGENTS.md` / `README.md` and displays context health status.
- [x] **Task 2.3:** `/undo` inspects recent `edit_file` / `write_file` tool events and offers instant rollback.

### Slice 3: Verification & Quality Gate
- [x] **Task 3.1:** Automated test suite in `tests/test_cli_repl.py` covering all 12 commands and aliases.
- [x] **Task 3.2:** 100% strict type checking (`mypy src`), formatting, and linting (`ruff`).
- [x] **Task 3.3:** 100% passing tests (`pytest`).
