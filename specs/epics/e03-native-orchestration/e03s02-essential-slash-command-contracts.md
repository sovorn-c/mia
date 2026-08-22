# e03s02 — Essential Slash Command Contract Alignment

## 1. Identity

- **Story ID:** e03s02
- **Epic:** e03 — Native Orchestration Runtime
- **Type:** fix
- **Risk:** P1
- **Context:** domain and infrastructure
- **BCPs:** 4
- **Status:** failing

## 2. User Story

As a Mia terminal user, I want every advertised slash command to perform the behavior its help text promises so that I can control orchestration, context, profiles, and local inspection without no-op success messages or REPL crashes.

## 3. Context

Mia exposes 18 canonical slash commands through three partially duplicated sources: `SLASH_COMMANDS`, `COMMAND_DESCRIPTIONS`, and `COMMAND_HINTS`. The orchestration slice added `/mode` to dispatch and help, but not completion. Behavioral probing also found placeholder or overstated implementations for `/compact`, `/stop`, `/init`, `/help`, and failure paths in `/profile` and `/diff`. The user selected a small honesty-first correction rather than the larger concurrent-input design required for real `/stop` support.

## 4. Problem

The current tests mostly prove that commands return from dispatch, not that they deliver their promised outcome. As a result, `/compact` reports success without changing context, invalid profiles escape as exceptions, `git diff` failures are reported as clean trees, and `/stop` is advertised even though the serial REPL cannot accept commands during an active turn. Duplicate command metadata makes drift easy to reintroduce.

## 5. Goal

Make command discovery and observable behavior truthful with the smallest compatible change: derive help and prefix matching from the existing completion metadata, implement manual compaction through a UI-free harness method, validate profile changes before mutation, surface Git failures, narrow overstated copy, and stop advertising unsupported active-turn cancellation.

## 6. Non-Goals

- Concurrent prompt input while an agent turn is streaming.
- Real `/stop` or `/abort` cancellation; this needs a separate lifecycle story.
- Background turns, task queues, or continuable agents.
- Deep repository architecture discovery or automatic ingestion for `/init`.
- A new command class, command bus, plugin API, or handler registry.
- `/undo` or file rollback.
- Changes to headless `mia run` command options.
- New runtime or development dependencies.

## 7. Stakeholders

- Interactive Mia users relying on command completion and help.
- Maintainers of the REPL, prompt-toolkit input, and orchestration runtime.
- Session owners who require append-only compaction evidence.
- Future cancellation work, which needs an honest deferred boundary rather than a no-op command.

## 8. Dependencies

- `src/mia_cli/repl.py`
- `src/mia_cli/interactive_input.py`
- `src/mia_agent/harness.py`
- `src/mia_agent/session/compactor.py`
- `src/mia_agent/session/entries.py`
- `tests/test_cli_repl.py`
- `tests/test_agent_loop.py`
- `tests/test_sessions.py`
- Existing Rich, prompt-toolkit, pytest, Ruff, Mypy, and PyYAML development tooling.

## 9. Assumptions

- The inline REPL remains serial: it reads one prompt, then awaits the complete turn.
- `COMMAND_HINTS` can remain the canonical ordered `(command, description)` list without introducing a new abstraction.
- Manual `/compact` is allowed before the automatic threshold when conversation history exists.
- Compaction remains an `AgentHarness` responsibility because only the harness owns in-memory messages and active JSONL lineage.
- Existing aliases remain compatible except `/abort`, which is removed with unsupported `/stop` advertising.

## 10. Constraints

- Python 3.12+, strict Mypy, Ruff formatting, and offline verification.
- `AgentHarness` remains UI-free and emits no terminal output.
- Session writes remain append-only; manual compaction must not rewrite message entries.
- Invalid command arguments must not partially mutate the active profile or runtime.
- Existing `/mode`, `/model`, `/resume`, `/tree`, `/inspect`, and `/thinking` behavior remains compatible.
- The fix must not add a command framework or package.

## 11. Domain Model

- **Canonical command:** one user-facing slash command present in completion, help, and unique-prefix matching.
- **Alias:** an alternate spelling resolved to a canonical command before dispatch.
- **Manual compaction:** an explicit request to replace the harness's active in-memory context with a structured summary plus retained recent messages and append a compaction checkpoint to session lineage.
- **Advertised command contract:** user-visible description plus the observable result produced by dispatch.
- **Deferred cancellation:** active-turn interruption excluded until the REPL can receive input concurrently with execution.

## 12. Requirements

### MODIFIED: Canonical slash-command metadata

**Before:** `SLASH_COMMANDS`, `COMMAND_DESCRIPTIONS`, and `COMMAND_HINTS` duplicate canonical names and descriptions; `/mode` is absent from completion.

**After:** `COMMAND_HINTS` is the single ordered source for canonical names and descriptions. The REPL derives help and unique-prefix matching from it, and `/mode` appears in completion. Structured aliases remain in `COMMAND_ALIASES`.

### MODIFIED: Manual context compaction

**Before:** `/compact` always prints `Context compaction status verified` and does not inspect or mutate context.

**After:** `/compact` invokes one public, UI-free `AgentHarness.compact_context()` operation. With history, it replaces active in-memory messages with compacted context, appends a `CompactionEntry` checkpoint and active leaf to the JSONL session, and reports estimated before/after token counts. With no history or no compactor, it reports an actionable no-op without claiming success.

### MODIFIED: Profile selection failure

**Before:** `/profile <name>` assigns `profile_name` before validation; an unknown name raises `ValueError` and can leave partially changed REPL state.

**After:** the profile is resolved before state mutation or runtime rebuild. Unknown profiles produce an actionable message listing available profiles and preserve the active profile, harness, and runtime.

### MODIFIED: Git diff failure reporting

**Before:** `/diff` ignores the subprocess return code and reports a clean working tree when `git diff` fails, including outside a Git repository.

**After:** `/diff` reports stderr and the non-zero exit as a failure. It reports a clean tree only when `git diff` exits zero with empty stdout.

### MODIFIED: Help and initialization copy

**Before:** `/help` claims active tool permissions it does not render, and `/init` claims repository architecture scanning and rule inspection while only checking for `.git`, `AGENTS.md`, and `README.md`.

**After:** command descriptions state the behavior actually rendered: `/help` shows the command/alias menu, and `/init` reports the presence of basic repository context files. Technical architecture uses the same descriptions.

### REMOVED: Unsupported `/stop` and `/abort` advertising

**Before:** completion, help, aliases, and architecture advertise `/stop` (`/abort`) as immediate active-turn cancellation, but `run_async()` serially awaits the turn and cannot receive the command while it runs.

**After:** (removed) — `/stop` and `/abort` are absent from the canonical command suite and dispatch. A separate future story must design concurrent prompt input, active task ownership, provider-stream cancellation, and tool-process cancellation before restoring them.

### ADDED: Behavioral command contract tests

Focused tests MUST assert canonical metadata consistency and observable outcomes for `/mode` completion, manual compaction/session evidence, invalid profile preservation, Git failure reporting, truthful help/init copy, and unsupported stop removal.

## 13. Non-Functional Requirements

- **Compatibility:** existing mode, model, auth, profile, session, tree, renderer, and headless tests remain green.
- **Integrity:** compaction writes only append-only `CompactionEntry` and `LeafEntry` records.
- **Failure safety:** invalid profile and Git operations do not report false success or corrupt active REPL state.
- **Maintainability:** adding a canonical command requires editing one ordered metadata list plus its handler, not three lists.
- **Performance:** command dispatch adds no model request and manual compaction remains linear in active message count.
- **Observability:** manual compaction reports before/after estimated token counts.

## 14. Contracts

### Existing contracts preserved

- `MiaREPL.handle_slash_command(command) -> bool` returns `False` only for `/quit`.
- Aliases and unique prefixes continue to resolve to canonical commands.
- `AgentHarness.prompt()` retains existing event order and automatic threshold compaction.
- `JsonlSessionStore` remains append-only and `SessionTree` remains the active-path authority.
- `ContextCompactor.compact_messages()` remains the compaction algorithm.

### Modified contracts

- Canonical completion/help/prefix names are derived from `COMMAND_HINTS`.
- `AgentHarness.compact_context()` performs forced manual compaction and returns enough structured information for adapters to report the outcome without importing UI types.
- Invalid profile selection and failed Git inspection are handled inside command dispatch.
- `/stop` and `/abort` are unknown until a future cancellation story implements their advertised semantics.

## 15. Reason for Depth

- **Public `AgentHarness.compact_context()` method:** Required because the harness alone owns mutable conversation state and active session lineage; direct REPL mutation of private fields would duplicate automatic compaction and risk inconsistent JSONL checkpoints.
- **No command-registry abstraction:** The existing `COMMAND_HINTS` list is sufficient as one source of truth; introducing command objects, decorators, or a bus would add indirection without a second execution adapter.

## 16. Implementation Steps

1. Add failing contract tests that require one canonical metadata source, `/mode` completion, truthful `/help` and `/init` descriptions, and no advertised `/stop` or `/abort` → verify: `uv run --offline pytest tests/test_cli_repl.py -k 'command_metadata or slash_completer or help_contract'`
2. Add failing harness and REPL tests, then implement forced manual compaction with before/after token evidence and append-only `CompactionEntry` lineage while preserving automatic compaction → verify: `uv run --offline pytest tests/test_agent_loop.py tests/test_sessions.py tests/test_cli_repl.py -k 'compact'`
3. Add failing command tests, then validate profiles before mutation and treat non-zero `git diff` as failure rather than a clean tree → verify: `uv run --offline pytest tests/test_cli_repl.py -k 'invalid_profile or diff_failure'`
4. Synchronize the essential command architecture and deferred cancellation boundary, then run all project gates before changing any task to passing → verify: `grep -q '17 canonical commands' specs/tech-architecture/tech-stack.md && grep -q 'Deferred active-turn cancellation' specs/tech-architecture/tech-stack.md && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest`

## 17. Acceptance Criteria

### Scenario SC-e03s02-P1-01: Command discovery cannot drift

```gherkin
Given Mia's canonical command metadata
When completion, help, and unique-prefix matching enumerate commands
Then all three expose the same 17 canonical names in the same order
And `/mode` is offered by completion
And `/stop` and `/abort` are not advertised
```

### Scenario SC-e03s02-P1-02: Manual compaction changes context durably

```gherkin
Given an active harness with conversation history and a session store
When the user runs `/compact`
Then active in-memory messages are replaced by compacted context
And estimated before and after token counts are reported
And a CompactionEntry and active LeafEntry are appended
And the prior message entries remain unchanged and readable
```

### Scenario SC-e03s02-P1-03: Empty compaction is honest

```gherkin
Given an active harness with no conversation history or no configured compactor
When the user runs `/compact`
Then Mia reports why no compaction occurred
And does not print a success claim
And appends no compaction checkpoint
```

### Scenario SC-e03s02-P1-04: Invalid profile preserves runtime state

```gherkin
Given Mia has an active valid profile and harness
When the user runs `/profile does-not-exist`
Then Mia reports the unknown profile and available choices
And the active profile, harness, and runtime remain unchanged
And no exception escapes command dispatch
```

### Scenario SC-e03s02-P1-05: Git inspection cannot report false success

```gherkin
Given Mia runs outside a Git repository or git diff otherwise exits non-zero
When the user runs `/diff`
Then Mia reports the Git failure and stderr
And does not report a clean working tree
```

### Scenario SC-e03s02-P1-06: Help text matches implemented behavior

```gherkin
Given the user opens `/help` or runs `/init`
When Mia renders their descriptions and output
Then `/help` claims only command and alias discovery
And `/init` claims only basic repository context-file checks
And architecture documentation uses the same bounded contract
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_cli_repl.py -k 'command_metadata or slash_completer or help_contract'` and confirm command discovery uses one canonical 17-command list with `/mode` and without `/stop`.
2. Create deterministic history with `MockProvider`, run `/compact`, and run `uv run --offline pytest tests/test_agent_loop.py tests/test_sessions.py tests/test_cli_repl.py -k 'compact'`; confirm in-memory reduction and append-only checkpoint evidence.
3. Run `uv run --offline pytest tests/test_cli_repl.py -k 'invalid_profile or diff_failure'`; confirm both failures remain local and do not print false success.
4. Run the full REPL tests and confirm existing auth, model, mode, resume, tree, inspect, thinking, clear, and quit behavior remains compatible.
5. Run Ruff format/check and strict Mypy.
6. Run the complete offline pytest suite.
7. Open the interactive completion menu and visually confirm `/mode` appears while unsupported `/stop` does not.

## 19. Risks and Mitigations

- **Automatic-compaction regression:** factoring a public manual method could change threshold behavior before turns. Mitigation: preserve existing automatic scenarios and add exact session-entry assertions for both paths.
- **Session lineage error:** a forced checkpoint could leave the active leaf on an old message. Mitigation: append `CompactionEntry`, update the harness entry ID, append `LeafEntry`, and reload the tree in tests.
- **Command removal surprise:** users may have seen `/stop` in help. Mitigation: document that it never worked interactively and record the explicit deferred cancellation boundary.
- **Metadata import coupling:** deriving metadata across modules could create a circular import. Mitigation: keep canonical `COMMAND_HINTS` in `interactive_input.py`, which `repl.py` already imports.
- **High-churn merge conflicts:** REPL/input files change frequently. Mitigation: keep edits local, avoid handler abstractions, and write invariant tests before implementation.

## 20. Definition of Done and Slopcheck

- All four tasks in `e03s02-tasks.yaml` start `failing` and change to `passing` only after their verify commands exit zero.
- All six acceptance scenarios have deterministic automated evidence except the final completion-menu visual smoke check.
- `specs/verifications/e03s02-verify.yaml` records final command outcomes.
- Impact, scope, release index, epic manifest, execution status, and architecture agree on the 17-command contract and deferred cancellation.
- Plan consistency reports `CRITICAL=0 HIGH=0 MED=0` before implementation.
- No unresolved P0/P1 defect or security finding remains in affected paths.

### Slopcheck

- `[OK]` Python standard library — subprocess status handling and existing collections/types.
- `[OK]` existing prompt-toolkit and Rich dependencies — command completion and rendering only.
- `[OK]` existing pytest/pytest-asyncio, Ruff, Mypy, and PyYAML development tooling.
- No new runtime or development package is proposed.

### Red-Flag Check

Caught and rejected these rationalizations: leaving `/compact` as a harmless placeholder; keeping `/stop` because it may work later; adding a command framework to solve list duplication; mutating `AgentHarness._messages` from the REPL; treating `git diff` empty stdout as success without checking its exit code; and expanding `/init` into repository indexing inside this small correction.

## 21. In-Flight Adjustments

The user reopened this active story rather than creating a new epic.

### Defects

- Environment-backed provider discovery checks only `<PROVIDER>_API_KEY`, missing configured aliases such as `GOOGLE_API_KEY`, `MIMO_API_KEY`, and `OPENCODE_API_KEY`.
- Exit output does not identify the session that was saved or provide a direct resume command.
- Top-level interactive `mia` has no `--session` option even though `MiaREPL` and the runtime factory already accept a session ID.

### Behavioral Adjustments

- `/model` MUST aggregate models from every connected provider by default and MUST NOT show unconnected providers. Connected means a stored API-key/OAuth entry or a recognized non-empty environment credential.
- When multiple providers are connected, `/model` retains an explicit all-providers or one-provider scope choice.
- `/scoped-models` MUST expose and update the ordered model cycle scope. Ctrl+P cycles the scope without opening the picker.
- Shift+Tab toggles Mia's existing thinking-trace display. Ctrl+Tab is not a distinct standard terminal key and prompt_toolkit rejects `c-tab`; Pi's actual thinking key is Shift+Tab. This slice does not claim to change provider reasoning effort.
- `/quit`, EOF, and Ctrl+C exit paths MUST show the active session ID and `mia --session <id>`.
- `mia --session <id>` MUST launch the interactive REPL with the specified durable session.

### Small Additions

- Add `/scoped-models` to canonical command metadata.
- Add Ctrl+L as the Pi-compatible model-picker shortcut while retaining `/model`.
- Keep scoped-model state session-local; persistence across Mia restarts is deferred until settings schema work is justified.

### Added Acceptance Scenarios

#### SC-e03s02-P1-07: Model discovery is connected-provider scoped

```gherkin
Given two connected providers and other known but unconnected providers
When the user opens `/model` and chooses All Providers
Then Mia discovers and lists models from both connected providers
And does not query or list any unconnected provider
```

#### SC-e03s02-P1-08: Scoped models support fast keyboard cycling

```gherkin
Given an ordered scoped-model list
When the user presses Ctrl+P repeatedly
Then Mia selects the next scoped model and wraps at the end
And Shift+Tab toggles thinking-trace visibility
```

#### SC-e03s02-P1-09: Exiting makes session recovery explicit

```gherkin
Given an active interactive session
When the user quits through `/quit`, EOF, or Ctrl+C
Then Mia prints the session ID and `mia --session <id>`
And launching that command passes the ID into the interactive REPL
```
