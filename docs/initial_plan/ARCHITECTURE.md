# Mia Technical Architecture Specification

> **Version:** 0.1.0-draft  
> **Status:** Approved Blueprint  
> **Target Runtime:** Python 3.12+ (AnyIO, Pydantic v2, Typer, Rich, Textual)  
> **Ground Truth References:** See [REFERENCES.md](REFERENCES.md) for local source code references in `pi`, `tau`, and `deepseek-harness`.

---

## 1. Architectural Foundations & Principles

Mia is built around five core design rules:

1. **Explicit Core, Composable Edges:** The agent loop is a simple, deterministic function without global mutable state or implicit event magic. Customizations happen through typed middleware chains.
2. **Events as the Sole UI Contract:** The core agent loop emits a stream of typed `AgentEvent` models. It never imports Rich, Textual, or stdout directly.
3. **Durable & Append-Only History:** All interactions (prompts, tool calls, tool results, tokens) are saved as an append-only JSONL log under `~/.mia/sessions/`.
4. **Onion-Style Middleware Execution:** All tool calls pass through an ordered sequence of async middlewares that can inspect, modify, guard, or short-circuit execution.
5. **Rust-Powered Pydantic Tool Schemas:** Tool schemas and arguments are validated at runtime via Pydantic v2 (leveraging Rust speed).

---

## 2. Core Domain Models & Event Vocabulary (`mia_agent.events`)

All communication between the **Core Engine** and **Frontends / Middleware** occurs through immutable, typed Pydantic models:

```python
from typing import Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime


# --- Base Event ---
class BaseAgentEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- 1. Streaming Text & Thinking from LLM ---
class AssistantChunkEvent(BaseAgentEvent):
    type: Literal["assistant_chunk"] = "assistant_chunk"
    delta_text: str
    thought_delta: str | None = None


# --- 2. Tool Execution Events ---
class ToolCallEvent(BaseAgentEvent):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolResultEvent(BaseAgentEvent):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    tool_name: str
    output: Any
    is_error: bool = False
    duration_ms: float


# --- 3. Step & Turn Lifecycle Events ---
class StepStartEvent(BaseAgentEvent):
    type: Literal["step_start"] = "step_start"
    step_index: int


class StepEndEvent(BaseAgentEvent):
    type: Literal["step_end"] = "step_end"
    step_index: int
    input_tokens: int
    output_tokens: int


class TurnCompleteEvent(BaseAgentEvent):
    type: Literal["turn_complete"] = "turn_complete"
    total_steps: int
    total_cost_usd: float


# Union type for easy type-narrowing in CLI / TUI
AgentEvent = (
    AssistantChunkEvent
    | ToolCallEvent
    | ToolResultEvent
    | StepStartEvent
    | StepEndEvent
    | TurnCompleteEvent
)
```

---

## 3. The Middleware Pipeline (`mia_middleware`)

The middleware system borrows the proven **Onion Pattern** from web frameworks (ASGI / FastAPI) and DeepSeek Harness's waterfall design.

### 3.1. Middleware Contract & Pipeline Runner

```python
from typing import Callable, Awaitable, Any
from pydantic import BaseModel, Field


class ToolCallContext(BaseModel):
    session_id: str
    step_index: int
    tool_name: str
    arguments: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


# Signature: (Context, NextCallable) -> Result
ToolMiddleware = Callable[[ToolCallContext, Callable[[], Awaitable[Any]]], Awaitable[Any]]


class ToolPipeline:
    def __init__(self, middlewares: list[ToolMiddleware] | None = None):
        self.middlewares: list[ToolMiddleware] = middlewares or []

    def use(self, middleware: ToolMiddleware) -> "ToolPipeline":
        self.middlewares.append(middleware)
        return self

    async def execute(
        self, ctx: ToolCallContext, core_executor: Callable[[], Awaitable[Any]]
    ) -> Any:
        async def dispatch(index: int) -> Any:
            if index < len(self.middlewares):
                middleware = self.middlewares[index]
                return await middleware(ctx, lambda: dispatch(index + 1))
            return await core_executor()

        return await dispatch(0)
```

### 3.2. Standard Built-in Middlewares

1. **`SecurityGuardMiddleware`**: Intercepts shell commands (`bash`) and filesystem deletions to block destructive operations (`rm -rf /`, `chmod -R 777`, `mkfs`).
2. **`UserConfirmationMiddleware`**: In interactive CLI mode, pauses execution and asks the user: `Allow agent to run command [Y/n]?`.
3. **`FileBackupMiddleware`**: Takes an in-memory snapshot of any file before `edit` or `write` executes, enabling instant rollback (`/undo`).
4. **`CostAndQuotaMiddleware`**: Tracks running token counts and enforces hard dollar limits per session or turn.
5. **`AuditLoggerMiddleware`**: Emits structured JSON telemetry to log files.

---

## 4. Built-in Coding Tools Specifications (`mia_tools`)

Following the battle-tested implementations in [`tau/src/tau_coding/tools.py`](file:///Users/sovorn/dev/pi/pi-architecture/tau/src/tau_coding/tools.py) and [`pi/packages/coding-agent/src/tools/`](file:///Users/sovorn/dev/pi/pi-architecture/pi/packages/coding-agent/src/tools/):

### 4.1. `read_file` Specification
* **Arguments:** `path: str`, `offset: int = 1`, `limit: int = 2000`.
* **Output Format:** Line-numbered content (`1: line_one\n2: line_two`).
* **Edge Cases:** Binary file detection (refuse image/binary reads with warning), truncation metadata if file exceeds byte limits (default 50KB cap).

### 4.2. `write_file` Specification
* **Arguments:** `path: str`, `content: str`.
* **Behavior:** Atomic write via temporary file, automatic creation of missing parent directories, UTF-8 BOM preservation.

### 4.3. `edit_file` (Exact Replacement Algorithm)
* **Arguments:** `path: str`, `edits: list[dict[oldText, newText]]`.
* **Algorithm Requirements:**
  1. Acquire an async per-file lock (`asyncio.Lock`).
  2. Normalize line endings (`CRLF` $\rightarrow$ `LF`) while remembering original line endings.
  3. Verify that each `oldText` block appears **exactly once** (unique match) in the original file. If `oldText` matches 0 times or $>1$ times, raise a descriptive error without modifying the file.
  4. Apply all non-overlapping replacement chunks in a single pass.
  5. Restore original line endings and write back to disk.
  6. Compute unified diff string and return line-level feedback to the agent.

### 4.4. `bash` (Async Subprocess Specification)
* **Arguments:** `command: str`, `timeout: float = 60.0`.
* **Behavior:**
  * Uses `asyncio.create_subprocess_shell` with `start_new_session=True` on POSIX.
  * Streams stdout/stderr interleaved in real time.
  * On timeout or user cancellation (`Ctrl+C`), terminates the entire process group (`os.killpg`) so orphaned child processes are never left behind.
  * Tail-truncates output if exceeding 2,000 lines or 50KB, spilling full output to a temporary log file.

---

## 5. Durable Session Storage & History (`mia_agent.session`)

Sessions are persisted as append-only **JSONL (JSON Lines)** files located in `~/.mia/sessions/<session_id>.jsonl`.

### 5.1. JSONL Entry Schema
Each line in `session.jsonl` is a valid JSON record:
```json
{"id": "entry-1", "parent_id": null, "timestamp": "2026-08-21T16:00:00Z", "type": "user_input", "content": "fix bug in auth"}
{"id": "entry-2", "parent_id": "entry-1", "timestamp": "2026-08-21T16:00:01Z", "type": "assistant_message", "content": "I will inspect auth.py", "tool_calls": [{"id": "call-1", "name": "read_file", "args": {"path": "auth.py"}}]}
{"id": "entry-3", "parent_id": "entry-2", "timestamp": "2026-08-21T16:00:02Z", "type": "tool_result", "call_id": "call-1", "tool_name": "read_file", "output": "1: def login()...", "is_error": false}
```

### 5.2. History Branching & Tree Reconstruction
By preserving `parent_id` pointers, Mia supports:
* Session resumption (`mia --resume <session_id>`)
* Branching off previous turns without corrupting previous conversation trees.
* Context compaction: Summarizing old turns into a consolidated system prompt note when token usage reaches 80% of model limits.

---

## 6. Frontend / CLI Integration (`mia_cli`)

1. **Print Mode (`mia -p "prompt"`)**: Non-interactive streaming directly to terminal stdout via `Rich`.
2. **Interactive TUI Mode (`mia`)**: Full-screen terminal UI powered by `Textual`, featuring:
   * Multi-line syntax-highlighted prompt editor
   * Collapsible tool execution widgets with real-time spinners
   * Live visual diff renderer for `edit_file` results
   * Status bar with token count, running cost, and active model.
