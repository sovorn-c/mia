# Master Specification: Mia Minimalist Stream REPL & Provider Auth (`specs/mia_tui_harness.md`)

> **Author:** Solo-Developer SDLC  
> **Target UX:** Minimalist Inline Stream REPL (Claude Code / Pi / Tau style)  
> **Runtime:** Python 3.12+ (Rich, Readline/Prompt, Pydantic v2, AnyIO, Typer)  
> **Key References:** Pi (Stream Rendering & Model Scoper), Tau (Auth, Credentials & Context Compaction), DeepSeek Harness (Guards & Profiles)

---

## 1. Minimalist Design Philosophy & Architecture

Mia prioritizes **speed, clarity, and zero-flicker stability** through an inline, stream-first terminal pair-programming harness:

1. **Inline Stream vs Full-Screen Canvas:** No screen clearing or cursor-position hacking during standard prompt input. All interactions flow naturally in the scrollable terminal buffer.
2. **Minimalist Visual Identity:**
   - **Signature Accent:** Carrot Orange (`#FF7A00` / `\x1b[38;2;255;122;0m`)
   - **Obsidian Dark Canvas & Subtle Borders:** Clean Unicode box glyphs (`─`, `│`, `╭`, `╰`)
   - **Compact Single-Line Banner:** Working directory, active model, profile, and command hint.
3. **Rock-Solid Standard Input:**
   - Universal readline / prompt engine with history file (`~/.mia/history`), Up/Down arrow recall, and Tab completion for slash commands.
   - Zero fragile raw ANSI cursor jumps (`\x1b[nA`, `\x1b[s`) that glitch across different terminal emulators.

---

## 2. Pi & Tau Provider Architecture & Authentication Flow

### A. Provider Credential Management (`~/.mia/credentials.json`)
Mia maintains a clean separation between **Authentication** (credentials store) and **Model Selection**:

| Provider ID | Provider Name | Default Base URL | Default / Recommended Models |
|---|---|---|---|
| **`opencode-go`** | OpenCode Zen (OpenCode-Go) | `https://opencode.ai/zen/go/v1` | `mimo-v2.5`, `qwen2.5-coder-32b-instruct`, `deepseek-v3` |
| **`openrouter`** | OpenRouter Gateway | `https://openrouter.ai/api/v1` | `anthropic/claude-3.7-sonnet`, `deepseek/deepseek-r1`, `openai/gpt-4o` |
| **`gemini`** | Google Gemini (OpenAI Compat) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` |
| **`openai`** | OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini`, `o3-mini`, `o1` |
| **`anthropic`** | Anthropic Claude | `https://api.anthropic.com/v1` | `claude-3-7-sonnet`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku` |
| **`deepseek`** | DeepSeek Official | `https://api.deepseek.com/v1` | `deepseek-chat`, `deepseek-reasoner` |
| **`custom`** | Local / Self-Hosted (Ollama, vLLM) | `http://localhost:11434/v1` | Custom model name |

### B. Clean 2-Option Login Flow (`/login`)
```
🥕 Mia Login Wizard
────────────────────────────────────────────────────────────
1. API Key       │ Paste API key for OpenCode, OpenRouter, Gemini, OpenAI, Claude, DeepSeek, Custom
2. OpenAI Auth   │ Interactive OpenAI OAuth / Session Token login

Select method [1/2] (default: 1): 1

Available Providers:
 1. opencode-go  │ OpenCode Zen API [Recommended]
 2. openrouter   │ OpenRouter Multi-Model Gateway
 3. gemini       │ Google Gemini API Key
 4. openai       │ OpenAI API Key
 5. anthropic    │ Anthropic Claude API Key
 6. deepseek     │ DeepSeek API Key
 7. custom       │ Custom OpenAI-Compatible / Local Endpoint

Select provider [1-7] (default: 1): 1
Enter API key for opencode-go: ***********************************

Testing connection to opencode-go...
✓ Authenticated opencode-go. Saved to ~/.mia/credentials.json
→ Use /model to select your active model.
```

### C. Direct & Resilient Connection Validation Probe
- Avoid brittle `GET /models` endpoints (which 404 on Gemini and many proxies).
- Execute a minimal, lightweight probe request (`messages=[{"role":"user","content":"ping"}]`, `max_tokens=1`).
- Permissive fallback: if probe fails due to network timeout, allow user to save key anyway with a clear warning instead of hard-blocking.

---

## 3. Essential Slash Commands Suite (12 Commands)

| Command | Aliases | Purpose & Execution |
|---|---|---|
| **`/help`** | `/?` | Display compact command menu, shortcuts & active tool permissions. |
| **`/login`** | `/auth` | Authenticate AI provider via API Key or OpenAI OAuth. |
| **`/logout`** | `/signout`, `/disconnect` | Remove stored credentials for a provider or all providers. |
| **`/model`** | `/llm` | Interactive model switcher scoped to authenticated providers + custom model input. |
| **`/profile`** | `/role`, `/persona` | Switch agent persona (`coding`, `architect`, `code_mode`, `minimal`). |
| **`/diff`** | `/changes` | Run `git diff` and render Monokai syntax-highlighted code diffs. |
| **`/cost`** | `/tokens`, `/stats` | Display real-time token counts (input, output, reasoning) and USD cost. |
| **`/compact`** | `/compress` | Inspect context window limit and manually trigger structured token compaction. |
| **`/sessions`** | `/history` | List saved JSONL session history trees for current profile. |
| **`/init`** | `/bootstrap` | Scan repository architecture, check active rules, and verify `AGENTS.md`. |
| **`/undo`** | `/revert` | Revert the latest file change made by the agent in this session. |
| **`/clear`** | `/cls` | Clear terminal screen and redraw header banner. |
| **`/quit`** | `/exit` | Save session tree and exit the harness cleanly. |

---

## 4. Minimalist Stream Rendering Spec

1. **Thinking Stream (`✻ Thinking` / `💭`):**
   - Dim italic streaming block without aggressive redraws.
   - When actual response begins, smoothly transitions into standard text stream.
2. **Assistant Text Stream:**
   - Direct, smooth character streaming to console.
3. **Tool Invocations:**
   - Single-line summary during invocation: `● Read file: src/main.py`
   - Single-line completion badge: `✓ Read file: src/main.py (1.2ms)`
   - Diff rendering: For `edit_file` and `/diff`, render clean syntax-highlighted unified diffs with line numbers.
4. **Turn Summary:**
   - At end of turn: `✓ Turn completed • 1,420 tokens • $0.0032`

---

## 5. Work Breakdown Slices (`plan-work`)

### Slice 1: Rock-Solid Input & Selection System (`mia_cli.interactive_input`)
- [ ] **Task 1.1:** Replace fragile raw POSIX cursor-drawing with clean, multi-platform numeric/arrow selection menu.
- [ ] **Task 1.2:** Enhance `MiaPromptReader` with readline history, command autocomplete, and zero-flicker prompt.

### Slice 2: Resilient Provider Validation & Auth (`mia_agent.auth`)
- [ ] **Task 2.1:** Implement lightweight completion probe in `validate_api_key` (replaces brittle `GET /models`).
- [ ] **Task 2.2:** Update `ConfigManager.resolve_credentials()` with clean provider URL fallbacks and Gemini compatibility.

### Slice 3: Minimalist Pi/Tau REPL Architecture (`mia_cli.repl`)
- [ ] **Task 3.1:** Implement clean, single-line banner and uncluttered command loop.
- [ ] **Task 3.2:** Re-architect `/login`, `/logout`, and `/model` flows for smooth step-by-step navigation.
- [ ] **Task 3.3:** Polish stream renderer for thinking, tool cards, and Monokai diffs.

### Slice 4: Verification & Test Suite
- [ ] **Task 4.1:** Update REPL automated tests in `tests/test_cli_repl.py`.
- [ ] **Task 4.2:** Full quality gate pass: `ruff check`, `mypy src`, and `pytest`.
