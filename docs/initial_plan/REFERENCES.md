# Local Reference Codebases & Architecture Map

> **Ground Truth on Disk:** This machine contains three fully functional reference implementations that were analyzed to design **Mia**. Any future coding agent or engineer should inspect these exact local directories before implementing any subsystem.

---

## 📍 Local Reference Directory Index

| Codebase | Local Absolute Path | Primary Language & Focus | Key Strengths to Inspect |
| :--- | :--- | :--- | :--- |
| **Tau** | [`/Users/sovorn/dev/pi/pi-architecture/tau`](file:///Users/sovorn/dev/pi/pi-architecture/tau) | **Python 3.12+** (Async, Pydantic, Textual, Rich) | The direct Python reference. Inspect for Pythonic event loops, session JSONL tree storage, and the `edit`/`read`/`bash` tool implementations. |
| **Pi** | [`/Users/sovorn/dev/pi/pi-architecture/pi`](file:///Users/sovorn/dev/pi/pi-architecture/pi) | **TypeScript / Node / Bun** (Original Reference) | Inspect for battle-tested tool contracts, prompt engineering, and differential terminal rendering. |
| **DeepSeek Harness (DSH)** | [`/Users/sovorn/dev/pi/pi-architecture/deepseek-harness`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness) | **TypeScript + C (Native Landlock)** | Inspect for onion middleware pipelines, execution waterfall hooks (`pre-execute`/`post-execute`), and Linux Landlock sandboxing. |
| **Tau Guided Plan** | [`/Users/sovorn/dev/pi/pi-architecture/TAU_CORE_GUIDED_REBUILD_PLAN.md`](file:///Users/sovorn/dev/pi/pi-architecture/TAU_CORE_GUIDED_REBUILD_PLAN.md) | **Markdown / Design Spec** | Phase-by-phase build notes and architectural rationale. |

---

## 🗺️ Subsystem-by-Subsystem Code Reference Map

When building specific parts of Mia, refer to these exact files:

### 1. Multi-Provider LLM Streaming (`mia_ai`)
* **Tau Reference:**
  * [`tau/src/tau_ai/stream.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/stream.py) — Unified stream interface and chunk types.
  * [`tau/src/tau_ai/anthropic.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/anthropic.py) — Anthropic SSE parser (tool calls + text).
  * [`tau/src/tau_ai/openai_compatible.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/openai_compatible.py) — OpenAI streaming parser.
  * [`tau/src/tau_ai/fake.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/fake.py) — Scripted mock provider for deterministic tests.
* **Pi Reference:**
  * [`pi/packages/ai/src/stream.ts`](file:///Users/sovorn/dev/pi/pi-architecture/pi/packages/ai/src/stream.ts) — Multi-provider streaming types.

### 2. Core Agent Loop & Events (`mia_agent`)
* **Tau Reference:**
  * [`tau/src/tau_agent/harness.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/harness.py) — The headless `AgentHarness` class.
  * [`tau/src/tau_agent/loop.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/loop.py) — The step-by-step turn execution loop.
  * [`tau/src/tau_agent/events.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/events.py) — Pydantic event domain models.
* **Pi Reference:**
  * [`pi/packages/agent/src/agent.ts`](file:///Users/sovorn/dev/pi/pi-architecture/pi/packages/agent/src/agent.ts) — TypeScript agent loop and tool execution.

### 3. Middleware Pipeline & Guardrails (`mia_middleware`)
* **DeepSeek Harness Reference:**
  * [`deepseek-harness/packages/core/tools/src/`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness/packages/core/tools/src/) — The tool pipeline with `pre-execute`, `execute`, and `post-execute` hooks.
  * [`deepseek-harness/docs/architecture.md`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness/docs/architecture.md) — Waterfall execution semantics and lifecycle.
  * [`deepseek-harness/native/landlock-run/`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness/native/landlock-run/) — C-based Linux Landlock filesystem/process sandboxing.

### 4. Built-in Coding Tools (`mia_tools`)
* **Tau Reference (Best Python reference):**
  * [`tau/src/tau_coding/tools.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/tools.py) — Contains the complete, battle-tested Python implementation for:
    * `read`: Line-numbering, pagination, offset/limit handling.
    * `write`: Atomic writes with directory creation.
    * `edit`: Exact substring replacement, whitespace trimming, and fuzzy matching fallback.
    * `bash`: Async subprocess execution with streaming stdout/stderr, timeout handling, and output size caps.
* **Pi Reference:**
  * [`pi/packages/coding-agent/src/tools/`](file:///Users/sovorn/dev/pi/pi-architecture/pi/packages/coding-agent/src/tools/) — TypeScript implementations of `read.ts`, `write.ts`, `edit.ts`, `bash.ts`.

### 5. Durable Session Storage & Tree History (`mia_agent.session`)
* **Tau Reference:**
  * [`tau/src/tau_agent/session/jsonl.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/session/jsonl.py) — Append-only JSONL read/write engine.
  * [`tau/src/tau_agent/session/tree.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/session/tree.py) — Session history tree with branching and parent-pointer tracking.
  * [`tau/src/tau_coding/context_window.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/context_window.py) — Token accounting and context window compaction.

### 6. Terminal UI & Rich Streaming (`mia_cli`)
* **Tau Reference:**
  * [`tau/src/tau_coding/cli.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/cli.py) — Typer CLI entrypoint and argument parsing.
  * [`tau/src/tau_coding/rendering/`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/rendering/) — Rich-based live event renderers for streaming chunks, diffs, and tool cards.
  * [`tau/src/tau_coding/tui/`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/tui/) — Full-screen Textual interactive application.
