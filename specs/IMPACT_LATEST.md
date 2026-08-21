# Impact Assessment — Essential Slash Command Contract Alignment

## Target

Align the advertised inline REPL slash-command contract with behavior that Mia actually supports. The selected small scope changes `src/mia_cli/repl.py::MiaREPL.handle_slash_command`, the completion metadata in `src/mia_cli/interactive_input.py`, and the public compaction seam in `src/mia_agent/harness.py`. It explicitly does not add concurrent prompt/turn execution for `/stop`.

## Zoom-Out Check

### `MiaREPL.handle_slash_command`

- **Purpose:** Parse canonical commands and aliases, mutate REPL configuration or session state, invoke local inspection actions, and tell `run_async()` whether the session should continue.
- **Callers:** `MiaREPL.run_async()`, its own unique-prefix expansion path, and `tests/test_cli_repl.py`.
- **Contracts:** aliases and unique prefixes resolve consistently; non-quit commands return `True`; `/quit` returns `False`; invalid user input is reported without escaping into the REPL loop; profile/mode/model changes rebuild the runtime only after validation; commands must not claim a state change they did not perform.

### `COMMAND_HINTS` / command metadata

- **Purpose:** Supply canonical command names and user-facing descriptions to prompt-toolkit completion and the `/help` menu.
- **Callers:** `SlashCompleter`, `MiaREPL.print_command_menu`, and CLI tests.
- **Contracts:** one canonical list drives completion, help, and prefix matching; every advertised canonical command has an implementation; aliases remain structured in `COMMAND_ALIASES`; copy describes observable behavior.

### `AgentHarness`

- **Purpose:** Execute one agent turn, maintain in-memory conversation state, append session-tree entries, run tool calls through middleware, and emit typed `AgentEvent` values without UI dependencies.
- **Callers:** `AgentRuntimeFactory`, legacy `HerdManager`, and direct agent/profile/session/middleware/E2E tests (14 indexed references across 9 groups).
- **Contracts:** event order remains stable; session writes remain append-only; automatic compaction happens before a turn only at threshold; compaction updates both in-memory context and the active session lineage; `messages` returns a copy; no terminal rendering or command parsing enters the harness.

## Dependents

- `src/mia_cli/repl.py::run_async`: serially reads a prompt, then awaits a full turn; this is why `/stop` cannot be entered during an active turn.
- `src/mia_cli/main.py`: imports `MiaREPL`; headless `mia run` also receives harnesses from `AgentRuntimeFactory`.
- `src/mia_agent/orchestration.py::AgentRuntimeFactory.build`: constructs every active runtime harness and configures its `ContextCompactor`.
- `src/mia_agent/herd/manager.py`: legacy constructor of `AgentHarness`; public compaction behavior must remain compatible.
- `tests/test_cli_repl.py`: command dispatch, aliases, mode/profile switching, resume/tree, rendering, auth, and model behavior.
- `tests/test_pty_prompt_layout.py`: prompt-toolkit completion/layout behavior.
- `tests/test_agent_loop.py`, `tests/test_sessions.py`, `tests/test_e2e_scenarios.py`, `tests/test_profiles.py`, `tests/test_middleware_pipeline.py`: direct `AgentHarness` and compaction contracts.

## Affected Stories

- `e01s03`: model/profile switching and slash-command suite.
- `e02s01`: prompt-toolkit slash completion and command metadata.
- `e02s03`: session inspection/resume/tree behavior; compaction must preserve append-only lineage.
- `e02s04`: `/stop`, `/init`, and context bootstrap claims.
- `e03s01`: explicit mode selection and shared orchestration runtime construction.
- Proposed `e03s02`: honest essential slash-command contracts and manual compaction.

## Current Findings

- `/mode` is implemented and documented but absent from `COMMAND_HINTS`, so autocomplete does not offer it.
- `/compact` always prints success but never inspects or changes context.
- `/profile does-not-exist` mutates `profile_name` and raises an uncaught `ValueError` while rebuilding the harness.
- `/diff` ignores a non-zero `git diff` exit status and reports a clean tree outside a Git repository.
- `/stop` is advertised as active-turn cancellation, but `run_async()` awaits `execute_turn()` serially and cannot accept the command during a turn.
- `/help` claims to show active tool permissions but only lists command descriptions.
- `/init` claims architecture/context inspection but only checks whether `.git`, `AGENTS.md`, and `README.md` exist.
- Existing command-suite tests mostly assert return values; they do not prove these observable outcomes.

## Test Coverage

- `tests/test_cli_repl.py`: broad command reachability, aliases, mode switching, profile switching, resume/tree, auth/model flows, and stream status.
- `tests/test_pty_prompt_layout.py`: completion-menu layout and prompt behavior.
- `tests/test_sessions.py`: compaction algorithm and session-tree persistence.
- `tests/test_agent_loop.py`: turn events and session writes.
- `tests/test_orchestration.py`: runtime factory and mode behavior.
- **Gap:** no invariant test proves completion, help, and dispatch use the same canonical command set.
- **Gap:** no command test proves manual compaction mutates context and appends a compaction checkpoint.
- **Gap:** no test proves invalid profile selection preserves the active profile/runtime.
- **Gap:** no test checks `git diff` failure reporting.
- **Gap:** no test prevents unsupported `/stop` and overstated `/init` behavior from being advertised.

## Risk: High

`repl.py` and `interactive_input.py` are high-churn shared UI modules (28 and 26 commits in the last 90 days), while the compaction change touches the shared `AgentHarness` session contract used by active orchestration, legacy Herd, and multiple test suites.

## Recommended Action

Proceed with a narrow story that derives help/completion/prefix matching from one existing metadata list, adds one UI-free `AgentHarness.compact_context()` operation with session evidence, validates profile and diff errors before mutation/success output, and removes unsupported `/stop` plus overstated `/init` claims from the advertised essential suite. Defer real `/stop` until a separate story designs concurrent prompt input and active-turn cancellation.
