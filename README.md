# Mia (Modular Intelligent Agent)

> **A Hybrid Python Coding Agent Harness** combining the deterministic simplicity of [Pi](https://pi.dev) & [Tau](https://twotimespi.dev) with the extensible middleware guardrails of [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness).

---

## 💡 Overview

**Mia** is a lightweight, high-performance, and modular AI coding agent harness written in modern Python (3.12+).

* **Core Engine (`mia_agent`):** Deterministic, typed agent loop (`Pydantic` + `AnyIO` + `asyncio`) with zero magic.
* **Middleware Pipeline (`mia_middleware`):** Onion-style async pipeline wrapping tool execution for security checks, user approval prompts, audit logs, and budgeting.
* **Multi-Provider LLM Streaming (`mia_ai`):** Standardized SSE streaming across Anthropic, OpenAI, and custom providers with offline mock testing.
* **Standard Coding Tools (`mia_tools`):** Battle-tested `read_file`, `write_file`, `edit_file` (single-match replacement), and async `bash`.
* **Terminal Interface (`mia_cli`):** Fast non-interactive streaming CLI (`mia -p "prompt"`) and full-screen Textual TUI (`mia`).

---

## 📁 Repository Layout

```text
mia/
├── pyproject.toml              # Build & dependency configuration
├── README.md                   # Project overview & quickstart
├── docs/
│   └── initial_plan/           # Original architecture blueprints & roadmaps
│       ├── ARCHITECTURE.md
│       ├── ROADMAP.md
│       ├── REFERENCES.md
│       └── INITIAL_README.md
├── src/
│   ├── mia_ai/                 # Multi-provider LLM streaming & adapters
│   ├── mia_agent/              # Core AgentHarness, events, and session store
│   ├── mia_middleware/         # Onion middleware pipeline & safety guardrails
│   ├── mia_tools/              # Coding tools (read, write, edit, bash)
│   └── mia_cli/                # Typer CLI, Rich live renderers, Textual TUI
└── tests/                      # Pytest automated test suites
```

---

## 🚀 Quickstart

### Installation

```bash
uv sync
```

### Running Tests & Quality Gates

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

### CLI Usage

```bash
# Print mode: Stream response directly to terminal
mia run -p "Fix the typo in README.md"

# Interactive TUI mode
mia
```

---

## 📖 Detailed Documentation

* Historical Architecture Design: [docs/initial_plan/ARCHITECTURE.md](docs/initial_plan/ARCHITECTURE.md)
* Historical Roadmap: [docs/initial_plan/ROADMAP.md](docs/initial_plan/ROADMAP.md)
* Ground Truth References: [docs/initial_plan/REFERENCES.md](docs/initial_plan/REFERENCES.md)
