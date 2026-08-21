# Impact Assessment — Native Orchestration Mode Vertical Slice

## Target

Insert a native orchestration runtime between Mia's CLI adapters and `AgentHarness`, centralize harness construction, preserve `AgentProfile` as a role configuration, and add a deterministic one-shot specialist workflow. The legacy `src/mia_agent/herd/` implementation is not an architectural input.

## Zoom-Out Check

### `AgentHarness`

- **Purpose:** Execute one agent's multi-step turn, dispatch every tool through the configured `ToolPipeline`, maintain in-memory messages, persist append-only session entries, and emit typed `AgentEvent` values without UI imports.
- **Callers:** Active production callers are `src/mia_cli/main.py::_run_agent_loop` and `src/mia_cli/repl.py::MiaREPL._init_harness`; direct tests construct it throughout `tests/test_agent_loop.py`, `tests/test_e2e_scenarios.py`, `tests/test_middleware_pipeline.py`, `tests/test_profiles.py`, and `tests/test_sessions.py`. `src/mia_agent/herd/manager.py` is a legacy caller.
- **Contracts:** `prompt()` is an async `AgentEvent` stream; tool visibility follows the provided tool list; tool execution uses middleware when configured; session writes are append-only; navigation changes the active leaf without rewriting history; the module has no terminal/UI dependency.

### `AgentProfile` and `ProfileManager`

- **Purpose:** Describe one reusable agent role and discover/filter built-in or user-defined role profiles.
- **Callers:** Active callers are the headless CLI, `MiaREPL`, profile CLI commands, and profile/E2E tests. The legacy Herd manager also calls them.
- **Contracts:** A profile controls system prompt, model defaults, tool allowlist, middleware names, execution kind, permission label, step limit, and compaction settings; built-ins remain available; custom JSON profiles round-trip through Pydantic validation; profile tool filtering must not expose disallowed tools.

### `MiaREPL._init_harness` and `MiaREPL.execute_turn`

- **Purpose:** Compose the active provider/profile/tools/middleware/session into a harness, then stream one prompt to the renderer.
- **Callers:** Initialization is reached from constructor setup, authentication, logout, model/profile switching, session resume, slash commands, and turn execution; `run_async()` calls `execute_turn()`.
- **Contracts:** no configured model leaves the harness unavailable; custom providers remain injectable for deterministic tests; resume restores active-path messages and leaf identity; model/profile switches rebuild runtime state; turn events continue updating renderer, token, and cost state.

### `src/mia_cli/main.py::_run_agent_loop`

- **Purpose:** Compose and execute one headless prompt with the same provider/profile/tool/session semantics as the REPL.
- **Callers:** `mia run` is its production caller.
- **Contracts:** CLI overrides beat profile/config defaults; `--resume` restores the active branch; output remains a typed event stream rendered by `RichStreamRenderer`.

### `JsonlSessionStore` and `SessionTree`

- **Purpose:** Persist append-only typed JSONL entries and reconstruct active or historical conversation paths.
- **Callers:** `AgentHarness`, both CLI composition paths, session navigation/resume, and session tests.
- **Contracts:** chronological append-only records; discriminated Pydantic decoding; malformed records fail with line/path context; parent links form acyclic traversable paths; `LeafEntry` selects the active branch.

## Dependents (41 call sites reported for `AgentHarness`)

- `src/mia_cli/main.py`: headless runtime construction and `mia run`.
- `src/mia_cli/repl.py`: interactive construction, authentication/model/profile changes, resume/tree flows, and prompt execution.
- `src/mia_cli/renderers/rich_stream.py`: consumes the current raw `AgentEvent` protocol.
- `src/mia_agent/profiles/`: role configuration and tool filtering.
- `src/mia_agent/session/`: root and one-shot child transcript persistence.
- `tests/test_agent_loop.py`: event order, multi-step tools, safeguards, and errors.
- `tests/test_profiles.py`: role discovery, custom profile lifecycle, and tool restrictions.
- `tests/test_sessions.py`: append/read, tree branching, compaction, and resume.
- `tests/test_cli_repl.py`: REPL construction, execution, model/profile switching, and resume.
- `tests/test_cli_print_mode.py`: CLI and renderer compatibility.
- `tests/test_e2e_scenarios.py`: autonomous tool cycle, security, compaction, branching, and profile permissions.
- `src/mia_agent/herd/` and `src/mia_cli/tui/`: legacy/experimental composition path; must not become the new runtime or silently break imports.

## Affected Stories

- `e01s03`: profile switching and slash-command behavior.
- `e01s04`: streamed event rendering.
- `e02s01`: prompt-toolkit command completion and status integration.
- `e02s02`: working-state rendering and token accounting.
- `e02s03`: session resume/tree navigation.
- `e02s04`: context bootstrap and turn control.
- New e03 story: native orchestration mode vertical slice.

## Test Coverage

- `tests/test_agent_loop.py`: direct `AgentHarness` event and tool-loop contracts.
- `tests/test_profiles.py`: profile persistence and tool filtering.
- `tests/test_sessions.py`: session append-only behavior, resume, branching, and compaction.
- `tests/test_cli_repl.py`: active REPL construction and turn execution.
- `tests/test_cli_print_mode.py`: CLI surface and raw event renderer.
- `tests/test_e2e_scenarios.py`: cross-module safety and persistence scenarios.
- **Gap:** no active test proves both CLI adapters use one shared harness factory.
- **Gap:** no event contract identifies the originating mode, workflow run, task, or agent.
- **Gap:** no non-legacy test proves one-shot specialist execution, child-session lineage, or result handoff.
- **Gap:** no compatibility test proves a one-node mode preserves current REPL/headless output and session behavior.

## Risk: High

The change inserts a new shared execution layer in front of a core type with 41 reported call sites and touches session, event, profile, headless, and interactive contracts; deterministic compatibility tests must precede migration.

## Recommended action

Proceed as a new e03 epic, first writing compatibility and orchestration contract tests. Keep `AgentHarness` focused on one agent, keep `AgentProfile` focused on one role, centralize construction once, and route both existing CLI adapters through a mode runtime. Limit the first story to a one-node compatibility path plus one deterministic sequential one-shot specialist workflow; defer continuable children, restart recovery, mailboxes, task DAGs, automatic workflow selection, plugin loading, and full-screen UI.
