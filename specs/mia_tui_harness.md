# Master Specification: Mia Production Developer Harness & Interactive CLI

A permanent, version-controlled specification for **Mia (Modular Intelligent Agent)**, following the Solo-Developer SDLC engineering standard.

---

## 1. Domain Architecture & Pi-Style Provider/Model Separation

| Concept | Responsibility | Storage & Resolution |
|---|---|---|
| **API Key Login (`/login`)** | Configure API keys for AI providers (`opencode-go`, `openrouter`, `gemini`, `openai`, `anthropic`, `deepseek`, `custom`) with live validation probe. | `~/.mia/credentials.json` |
| **OpenAI OAuth Login (`/login`)** | Interactive OAuth 2.0 PKCE / Session token browser authentication for OpenAI. | `~/.mia/credentials.json` |
| **Logout (`/logout`)** | Disconnect and clear credentials for one or all providers. | `~/.mia/credentials.json` |
| **Model Scoping (`/model`)** | Interactive model switcher scoped dynamically to authenticated providers with arrow navigation. | `~/.mia/config.json` (`default_model`) |
| **`MiaREPL`** | The interactive stream-first terminal pair-programming harness. | Primary developer interface (`mia`) |
| **`AgentHarness`** | Deterministic headless async brain executing multi-turn turns. | Execution loop in `src/mia_agent/harness.py` |

---

## 2. The 2-Option Login Flow with Pre-Flight Key Validation

```
1. Step 1: Login Method Selection
🔑 Mia Login (Use ↑/↓ arrows to navigate, Enter to select)
🥕 API Key   │ Paste API key (OpenCode, OpenRouter, Gemini, OpenAI, Claude, DeepSeek)
   Auth      │ OpenAI OAuth / Session token login

2. If API Key:
🔑 Select Provider (Use ↑/↓ arrows to navigate, Enter to select)
🥕 opencode-go │ OpenCode API Key [Recommended]
   openrouter  │ OpenRouter Multi-Model Gateway
   gemini      │ Google Gemini API Key
   openai      │ OpenAI API Key
   anthropic   │ Anthropic Claude API Key
   deepseek    │ DeepSeek API Key
   custom      │ Custom OpenAI-Compatible / Local Endpoint

Enter API key: ***********************************
Testing opencode-go credentials...
✓ Validated & Authenticated opencode-go. Saved to ~/.mia/credentials.json

3. If Auth:
Launching OpenAI OAuth...
Opening browser. If prompted, approve Mia access.
✓ Validated & Authenticated openai via Auth. Saved to ~/.mia/credentials.json
```

---

## 3. Essential Slash Commands Suite

| Command | Aliases | Purpose & Execution |
|---|---|---|
| **`/help`** | `/?` | Display interactive command menu, shortcuts & active tool permissions. |
| **`/login`** | `/auth` | Authenticate an AI provider via API Key or OpenAI OAuth. |
| **`/logout`** | `/signout`, `/disconnect` | Remove stored credentials for a provider or all providers. |
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

### Slice 1: Authentication & Credential Management
- [x] **Task 1.1:** 2-Option Login root (API Key vs OpenAI Auth).
- [x] **Task 1.2:** Live Pre-flight Key Validation Probe before saving credentials.
- [x] **Task 1.3:** OpenAI OAuth 2.0 PKCE browser authentication in `src/mia_agent/auth/openai_auth.py`.
- [x] **Task 1.4:** Interactive `/logout` / `/signout` command to wipe credentials.

### Slice 2: Scoped Model Switcher (`/model`) & Clean Banner
- [x] **Task 2.1:** Zero-assumption startup: `Model: (none - run /login)` until actually authenticated.
- [x] **Task 2.2:** `interactive_model_picker()` dynamically scanning authenticated providers.
- [x] **Task 2.3:** Carrot `🥕 ` pointer navigation for all interactive pickers.

### Slice 3: Verification & Quality Gate
- [x] **Task 3.1:** Automated test suite in `tests/test_cli_repl.py` (63/63 passing).
- [x] **Task 3.2:** 100% strict type checking (`mypy src`), formatting, and linting (`ruff`).
