# Master Specification: Mia Production Developer Harness & Interactive CLI

A permanent, version-controlled specification for **Mia (Modular Intelligent Agent)**, following the Solo-Developer SDLC engineering standard.

---

## 1. Domain Architecture & Pi-Style Provider/Model Separation

| Concept | Responsibility | Storage & Resolution |
|---|---|---|
| **Provider Auth (`/login`)** | Configure API keys or tokens for AI providers (`opencode-go`, `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`, `custom`). | `~/.mia/credentials.json` |
| **Model Scoping (`/model`)** | Interactive model switcher scoped dynamically to authenticated providers. | `~/.mia/config.json` (`default_model`) |
| **`MiaREPL`** | The interactive stream-first terminal pair-programming harness. | Primary developer interface (`mia`) |
| **`AgentHarness`** | Deterministic headless async brain executing multi-turn turns. | Execution loop in `src/mia_agent/harness.py` |
| **`RichStreamRenderer`** | Unified terminal renderer for thoughts, tool calls, diffs, and markdown. | Live visual streaming in `src/mia_cli/repl.py` |

---

## 2. The 2-Step Authentication & Scoped Model Switcher Workflow

```
1. Step 1: Provider Authentication (/login)
╭─ 🔑 Mia Provider Authentication ────────────────────────────────────────╮
│ Select an AI Provider to authenticate:                                  │
│  [1] opencode-go (OpenCode Zen API) [Recommended]                       │
│  [2] openrouter  (OpenRouter Multi-Model Gateway)                       │
│  [3] gemini      (Google Gemini API)                                    │
│  [4] openai      (OpenAI API / OAuth)                                   │
│  [5] anthropic   (Anthropic Claude API)                                 │
│  [6] deepseek    (DeepSeek API)                                         │
│  [7] custom      (Custom OpenAI-Compatible / Local / Ollama)            │
╰─────────────────────────────────────────────────────────────────────────╯
Select provider to authenticate [1-7]: 1
Enter API key for opencode-go: ***********************************
✓ Authenticated opencode-go. Saved to ~/.mia/credentials.json

2. Step 2: Immediate Model Scoping
Available models for opencode-go:
  [1] mimo-v2.5 (Default)
  [2] qwen2.5-coder-32b-instruct
  [3] deepseek-v3
  [4] Custom / Enter model name
Select active model [1-4 or type name] (default: 1): 1
✓ Active model set to mimo-v2.5

3. In-Session Model Switching (/model)
╭─ 🤖 Scoped Model Switcher (Pi-Style) ───────────────────────────────────╮
│ Index │ Provider    │ Model Name                                        │
├───────┼─────────────┼───────────────────────────────────────────────────┤
│ [1]   │ opencode-go │ mimo-v2.5 (Active)                                │
│ [2]   │ opencode-go │ qwen2.5-coder-32b-instruct                        │
│ [3]   │ opencode-go │ deepseek-v3                                       │
│ [4]   │ deepseek    │ deepseek-chat                                     │
│ [5]   │ deepseek    │ deepseek-reasoner                                 │
│ [6]   │ any         │ Type custom model name...                         │
╰───────┴─────────────┴───────────────────────────────────────────────────╯
Select model [1-6 or type model name]: 2
✓ Switched model to qwen2.5-coder-32b-instruct
```

---

## 3. Essential Slash Commands Suite

| Command | Aliases | Purpose & Execution |
|---|---|---|
| **`/help`** | `/?` | Display interactive command menu, shortcuts & active tool permissions. |
| **`/login`** | `/auth` | Authenticate an AI provider (`opencode-go`, `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`). |
| **`/model`** | `/llm` | Open interactive model switcher scoped to authenticated providers. |
| **`/profile`** | `/role`, `/persona` | Switch agent persona (`coding`, `architect`, `code_mode`, `minimal`). |
| **`/diff`** | `/changes` | Run `git diff` on the repository and render Monokai syntax-highlighted code diffs. |
| **`/cost`** | `/tokens`, `/stats` | Display real-time token counts (input, output, reasoning) and USD cost. |
| **`/compact`** | `/compress` | Inspect context window limit and manually trigger structured token compaction. |
| **`/sessions`** | `/history` | List saved JSONL session history trees for current profile. |
| **`/init`** | `/bootstrap` | Scan repository architecture, check active rules, and verify `AGENTS.md`. |
| **`/clear`** | `/cls` | Clear terminal screen and redraw header banner. |
| **`/undo`** | `/revert` | Revert the latest file change made by the agent in this session. |
| **`/quit`** | `/exit` | Save session tree and exit the harness cleanly. |

---

## 4. Work Breakdown Slices

### Slice 1: Pi-Style Provider Authentication (`src/mia_cli/repl.py`)
- [x] **Task 1.1:** Build provider authentication wizard for `opencode-go`, `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`, `custom`.
- [x] **Task 1.2:** Store API keys atomically via `FileCredentialStore` in `~/.mia/credentials.json`.
- [x] **Task 1.3:** First-run onboarding check: if no credentials exist, guide user through provider auth.

### Slice 2: Scoped Model Switcher (`/model`)
- [x] **Task 2.1:** Build `interactive_model_picker()` dynamically scanning authenticated providers.
- [x] **Task 2.2:** Support selecting from catalog, typing custom model name, or direct `/model <name>`.
- [x] **Task 2.3:** Save active model and base URL preferences to `~/.mia/config.json`.

### Slice 3: Verification & Quality Gate
- [x] **Task 3.1:** Automated test suite in `tests/test_cli_repl.py` covering provider auth and model scoping.
- [x] **Task 3.2:** 100% strict type checking (`mypy src`), formatting, and linting (`ruff`).
- [x] **Task 3.3:** 100% passing tests (`pytest`).
