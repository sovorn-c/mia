# Mia Implementation Roadmap & Build Plan

> **Build Strategy:** Test-driven, phased development. Every phase builds upon the previous one and is validated against unit tests and local reference codebases before proceeding.

---

## 🗺️ Reference Repositories on this Machine
Before starting each phase, inspect the relevant local reference code:
* **Tau (Python Reference):** [`/Users/sovorn/dev/pi/pi-architecture/tau`](file:///Users/sovorn/dev/pi/pi-architecture/tau)
* **Pi (TypeScript Reference):** [`/Users/sovorn/dev/pi/pi-architecture/pi`](file:///Users/sovorn/dev/pi/pi-architecture/pi)
* **DeepSeek Harness (Middleware Reference):** [`/Users/sovorn/dev/pi/pi-architecture/deepseek-harness`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness)
* **Detailed File Map:** See [REFERENCES.md](REFERENCES.md).

---

## Phase 1: Foundations & Multi-Provider LLM Streaming (`mia_ai`)

### Objectives
- Set up `pyproject.toml` dependencies with `uv sync`.
- Implement unified streaming adapters for Anthropic, OpenAI, and OpenAI-compatible providers.
- Implement a **Faux / Mock Provider** to enable fast, offline, deterministic testing.

### Reference Code to Study
* [`tau/src/tau_ai/stream.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/stream.py) (Unified stream definitions)
* [`tau/src/tau_ai/anthropic.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/anthropic.py) (Anthropic SSE parser)
* [`tau/src/tau_ai/fake.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_ai/fake.py) (Scripted mock provider)

### Deliverables
- `src/mia_ai/types.py`: `StreamChunk`, `ToolCallDelta`, `TokenUsage`.
- `src/mia_ai/providers/base.py`: Abstract `LLMProvider` protocol.
- `src/mia_ai/providers/anthropic.py`: Anthropic SSE streaming parser.
- `src/mia_ai/providers/openai.py`: OpenAI SSE streaming parser.
- `src/mia_ai/providers/mock.py`: Scripted mock provider.
- `tests/test_ai_streaming.py`: Unit tests for stream chunking and tool call reconstruction.

### Quality Gate
```bash
uv run pytest tests/test_ai_streaming.py
uv run mypy src/mia_ai
```

---

## Phase 2: Core Event Engine & Headless Loop (`mia_agent`)

### Objectives
- Define the typed `AgentEvent` Pydantic models.
- Implement the `AgentHarness` loop coordinating turns, steps, tool calls, and completion detection.
- Enforce strict `max_steps_per_turn` safeguards to prevent infinite loops.

### Reference Code to Study
* [`tau/src/tau_agent/harness.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/harness.py)
* [`tau/src/tau_agent/loop.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/loop.py)
* [`tau/src/tau_agent/events.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/events.py)

### Deliverables
- `src/mia_agent/events.py`: All Pydantic event models.
- `src/mia_agent/harness.py`: `AgentHarness` implementation.
- `tests/test_agent_loop.py`: Tests with `MockProvider` testing single-turn text, multi-step tool loops, and max-step termination.

### Quality Gate
```bash
uv run pytest tests/test_agent_loop.py
uv run mypy src/mia_agent
```

---

## Phase 3: Onion Middleware Pipeline (`mia_middleware`)

### Objectives
- Implement the async `ToolPipeline` runner with `(context, next_fn)` execution semantics.
- Implement standard security, audit, and budgeting middlewares:
  - `SecurityGuardMiddleware`: Filter for destructive shell commands.
  - `CostBudgetMiddleware`: Session token tracking and hard stops.
  - `AuditLogMiddleware`: Telemetry logging.

### Reference Code to Study
* [`deepseek-harness/packages/core/tools/`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness/packages/core/tools/)
* [`deepseek-harness/docs/architecture.md`](file:///Users/sovorn/dev/pi/pi-architecture/deepseek-harness/docs/architecture.md)

### Deliverables
- `src/mia_middleware/pipeline.py`: `ToolPipeline` runner.
- `src/mia_middleware/security.py`: Built-in safety checks.
- `src/mia_middleware/telemetry.py`: Audit and cost tracking.
- `tests/test_middleware_pipeline.py`: Unit tests verifying middleware ordering, short-circuiting, and argument modification.

### Quality Gate
```bash
uv run pytest tests/test_middleware_pipeline.py
uv run mypy src/mia_middleware
```

---

## Phase 4: Standard Coding Tools (`mia_tools`)

### Objectives
- Build robust implementations of the 4 essential coding tools:
  - `read_file`: Line numbers (`1: content`), offset, limit, byte truncation.
  - `write_file`: Atomic writes with parent directory creation.
  - `edit_file`: Exact replacement matching with line normalization and unified diff generation.
  - `bash`: Async non-blocking shell execution with process-group cleanup (`os.killpg`) on cancellation.

### Reference Code to Study
* [`tau/src/tau_coding/tools.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/tools.py) (The complete Python gold-standard implementation)
* [`pi/packages/coding-agent/src/tools/`](file:///Users/sovorn/dev/pi/pi-architecture/pi/packages/coding-agent/src/tools/)

### Deliverables
- `src/mia_tools/base.py`: `BaseTool` class with `.schema()` generation.
- `src/mia_tools/fs.py`: `read_file`, `write_file`, `edit_file`.
- `src/mia_tools/bash.py`: `bash` command execution tool.
- `tests/test_tools.py`: Comprehensive test suite testing all edge cases (BOM handling, CRLF normalization, non-matching edits, command timeouts, process cleanup).

### Quality Gate
```bash
uv run pytest tests/test_tools.py
uv run mypy src/mia_tools
```

---

## Phase 5: Fast CLI & Rich Streaming Print Mode (`mia_cli`)

### Objectives
- Implement `mia` CLI command via `Typer`.
- Implement non-interactive **Print Mode** (`mia -p "prompt"`):
  - Real-time streaming of LLM tokens using `Rich`.
  - Styled panels for tool invocations and syntax-highlighted diffs for file edits.

### Reference Code to Study
* [`tau/src/tau_coding/cli.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/cli.py)
* [`tau/src/tau_coding/rendering/`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/rendering/)

### Deliverables
- `src/mia_cli/main.py`: Typer CLI entrypoint.
- `src/mia_cli/renderers/rich_stream.py`: Real-time terminal event renderer.
- `tests/test_cli_print_mode.py`: Integration smoke tests.

### Quality Gate
```bash
uv run pytest tests/test_cli_print_mode.py
uv run mypy src/mia_cli
```

---

## Phase 6: Durable Sessions & Compaction (`mia_agent.session`)

### Objectives
- Implement append-only JSONL session logging under `~/.mia/sessions/<session_id>.jsonl`.
- Support session resumption (`mia --resume <session_id>`).
- Implement context window compaction (summarizing older conversation turns when context window reaches 80% capacity).

### Reference Code to Study
* [`tau/src/tau_agent/session/jsonl.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/session/jsonl.py)
* [`tau/src/tau_agent/session/tree.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_agent/session/tree.py)

### Deliverables
- `src/mia_agent/session.py`: JSONL file persistence and history reconstruction.
- `src/mia_agent/compaction.py`: Automated context window summarization.
- `tests/test_sessions.py`: Resume, branch, and compaction tests.

### Quality Gate
```bash
uv run pytest tests/test_sessions.py
```

---

## Phase 7: Full-Screen Interactive Textual TUI (`mia_cli.tui`)

### Objectives
- Build a rich interactive terminal interface using **Textual**:
  - Multi-line user prompt editor with syntax highlighting.
  - Scrollable message history with collapsible tool execution cards.
  - Interactive approval prompts (pressing `y` / `n` for shell commands).
  - Status bar showing current model, tokens used, and cost.

### Reference Code to Study
* [`tau/src/tau_coding/tui/`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/tui/)

### Deliverables
- `src/mia_cli/tui/app.py`: Textual App implementation.
- `src/mia_cli/tui/widgets/`: Chat history, tool card, and prompt widgets.

---

## Full Repository Verification Command

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```
