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

## 2. Interaction Specification: The Production-Grade Standard

```
╭─ 🥕 Mia v0.2.0 (mimo-v2.5) ─────────────────────────────────────────────────────────────╮
│ Directory: /Users/sovorn/dev/harness/mia                                                │
│ Model:     mimo-v2.5  │  Profile: coding  │  Session: session_a8f12c9e                  │
│ Commands:  Type / for menu (/login, /model, /profile, /compact, /cost, /sessions, /quit)│
╰─────────────────────────────────────────────────────────────────────────────────────────╯

🥕 mia > /login

╭─ 🔑 Mia Authentication Setup ───────────────────────────────────────────────────────────╮
│ Select an AI Provider to configure:                                                    │
│  [1] opencode-go (MiMo-v2.5 / OpenCode Zen API)                                         │
│  [2] anthropic   (Claude 3.5 Sonnet / Claude 3.7 Sonnet)                               │
│  [3] openai      (GPT-4o / o1 / o3-mini)                                               │
│  [4] deepseek    (DeepSeek-V3 / DeepSeek-R1 Reasoner)                                  │
╰─────────────────────────────────────────────────────────────────────────────────────────╯
Select provider [1-4 or name] (default: 1): 1
Enter API Key for opencode-go: ***********************************

✓ Successfully stored credentials in ~/.mia/credentials.json
✓ Active model set to mimo-v2.5. Harness reloaded and ready!

🥕 mia > Inspect the test failure in tests/test_calc.py and fix the bug

💭 Thinking: Inspecting test_calc.py and the implementation in src/calc.py...
▶ Tool: read_file(path="tests/test_calc.py") ─────────────────────────────── [✓ 1.2ms]
▶ Tool: bash(command="pytest tests/test_calc.py") ────────────────────────── [✗ Failed (140.2ms)]
  FAIL tests/test_calc.py::test_multiply - AssertionError
▶ Tool: edit_file(path="src/calc.py") ────────────────────────────────────── [✓ 2.1ms]
  @@ -12,4 +12,4 @@
  - return a + b
  + return a * b
▶ Tool: bash(command="pytest tests/test_calc.py") ────────────────────────── [✓ Succeeded (120.5ms)]
  1 passed in 0.12s

✓ I have fixed the multiplication logic in src/calc.py. All tests in tests/test_calc.py are now passing.
✓ Turn completed • Total tokens: 1,420 • Cost: $0.0018

🥕 mia > 
```

---

## 3. Work Breakdown Slices

### Slice 1: Interactive Authentication & Guided Setup Wizard
- [x] **Task 1.1:** Build `interactive_login()` wizard in `src/mia_cli/repl.py` supporting `opencode-go`, `anthropic`, `openai`, and `deepseek`.
- [x] **Task 1.2:** Store API keys atomically via `FileCredentialStore` in `~/.mia/credentials.json`.
- [x] **Task 1.3:** First-run onboarding check: if no credentials exist for the selected model, prompt user with the setup wizard automatically on launch.
- [x] **Task 1.4:** Add in-session `/login [provider]` slash command.

### Slice 2: Instant Slash Command Palette
- [x] **Task 2.1:** Typing `/`, `/?`, or `/help` renders a clean, formatted Rich command table.
- [x] **Task 2.2:** Multi-provider model presets (`/model` without args lists popular models like `mimo-v2.5`, `claude-3-5-sonnet`, `gpt-4o`, `deepseek-chat`).
- [x] **Task 2.3:** Profile inspector (`/profile` without args lists profiles with tool capabilities).
- [x] **Task 2.4:** Session statistics (`/cost`) showing token breakdown, compaction count, and estimated cost.

### Slice 3: Real-Time Stream Engine & Tool Diffs
- [x] **Task 3.1:** Stream reasoning thoughts in real time with dim italic styling.
- [x] **Task 3.2:** Render tool calls with latency badges (`[✓ 1.2ms]`) and Monokai syntax-highlighted diffs.
- [x] **Task 3.3:** Turn cancellation on `Ctrl+C` without terminating the REPL session.

### Slice 4: Full Quality Gate & Verification
- [x] **Task 4.1:** Automated unit and scenario tests in `tests/test_cli_repl.py` and `tests/test_credentials.py`.
- [x] **Task 4.2:** 100% strict type checking (`mypy src`) and linting (`ruff`).
- [x] **Task 4.3:** 100% passing tests (`pytest`).
