# Mia (Modular Intelligent Agent)

> **A Hybrid Python Coding Agent Harness** combining the deterministic simplicity of [Pi](https://pi.dev) & [Tau](https://twotimespi.dev) with the extensible middleware power of [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness).

---

## 💡 Overview & Philosophy

**Mia** is a lightweight, high-performance, and modular AI coding agent harness written in modern Python (3.12+). 

Traditional agent architectures force a compromise:
* **Monolithic Agents (Pi / Tau style):** Blazingly fast and easy to debug, but rigid—adding enterprise guardrails, custom billing, and security sandboxes requires modifying or forking the core agent loop.
* **Microkernel Agents (DSH / Cordis style):** Extremely extensible, but heavy, with event indirection that makes single-process tracing and Python integration complex.

**Mia solves this with a Hybrid Architecture:**
* **The Core Brain:** An explicit, strongly typed, deterministic agent loop (`Pydantic` + `AnyIO` + `asyncio`) with zero magic.
* **The Nervous System:** An onion-style async **Middleware Pipeline** wrapping tool execution, LLM streams, and turn events—enabling security checks, user approval prompts, audit logs, and sandboxing without touching the core engine.
* **The Interface:** A responsive terminal CLI powered by **Typer**, **Rich**, and **Textual**.

---

## 🏛️ Layered System Architecture

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ 1. FRONTEND / TUI (`mia_cli`)                                             │
│    • CLI Arguments & Subcommands (Typer)                                  │
│    • Real-time Streaming Output (Rich Live Console)                       │
│    • Full-Screen Interactive Terminal UI (Textual)                        │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ 1. Sends user prompts
                                      │ 2. Consumes typed Async Event Stream
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 2. HEADLESS AGENT CORE (`mia_agent`)                                      │
│    • AgentHarness: Coordinates turn lifecycle & step limits               │
│    • SessionStore: Append-only JSONL event history with branching         │
│    • PromptEngine: Assembles system guidelines & Pydantic tool schemas    │
│    • Emits typed events: ChunkEvent, ToolCallEvent, ToolResultEvent       │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ Dispatches tool calls
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 3. MIDDLEWARE PIPELINE (`mia_middleware`)                                 │
│    • SecurityGate: Blocks dangerous commands (rm -rf, fork bombs)         │
│    • UserApproval: Interactive terminal confirmations for shell/edits     │
│    • LocalSnapshot: Auto-backups files before edits for instant /undo     │
│    • CostTracker: Real-time token & dollar budget enforcement             │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ Executes actual I/O
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ 4. TOOLS & AI PROVIDERS (`mia_tools` & `mia_ai`)                          │
│    • Built-in Coding Tools: read, write, edit, bash, glob, grep           │
│    • LLM Normalizer: Unified streaming for OpenAI, Anthropic, Gemini, etc.│
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Reference / Package Layout

```text
mia/
├── pyproject.toml              # Modern uv / hatchling configuration
├── README.md                   # Project overview & philosophy
├── ARCHITECTURE.md             # In-depth technical specification
├── ROADMAP.md                  # Step-by-step phased build plan
└── src/
    ├── mia_ai/                 # Multi-provider LLM streaming & adapters
    ├── mia_agent/              # Core AgentHarness, events, and session log
    ├── mia_middleware/         # Onion middleware pipeline & safety guardrails
    ├── mia_tools/              # Built-in coding tools (read, write, edit, bash)
    └── mia_cli/                # Typer CLI, Rich live renderers, Textual TUI
```

---

## 📄 Documentation Links

* Read the full technical design in [ARCHITECTURE.md](ARCHITECTURE.md)
* Follow the step-by-step implementation guide in [ROADMAP.md](ROADMAP.md)
