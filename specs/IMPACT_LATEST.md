# Impact Assessment — e06 Zero-Legacy Agent Core

## Target

Remove the obsolete Profile/Mode/Workflow/Herd identity and orchestration surfaces from Mia's active source, tests, CLI, and living documentation while keeping the Textual TUI as a thin Agent frontend. The canonical path becomes CLI/REPL/TUI → AgentRunner → AgentRuntimeFactory → AgentHarness.

## Dependents (high fan-in)

- `src/mia_agent/agents/model.py`: Agent validation, built-ins, access vocabulary, persistence, Plugin configuration, and runtime callers.
- `src/mia_agent/agents/manager.py`: CLI, REPL, runtime factory, Delegation, Plugins, Sessions, and TUI registry access.
- `src/mia_agent/agents/legacy.py`: Profile projection and native/legacy collision resolution; delete after callers move.
- `src/mia_agent/profiles/`: Profile models, persistence, filtering, and legacy Session paths; delete.
- `src/mia_agent/orchestration_models.py`: mixed Mode/Workflow/Profile projection and canonical runtime contracts; split/rename, then delete legacy file.
- `src/mia_agent/orchestration_events.py`: envelope helpers; split/rename to Agent Run helpers.
- `src/mia_agent/orchestration.py`: import compatibility facade; delete and update all imports.
- `src/mia_agent/mode_runtime.py`: duplicate legacy execution root; delete.
- `src/mia_agent/runtime_factory.py`: provider, Tool, Plugin, middleware, Session, and harness composition root; make Agent-only.
- `src/mia_agent/agent_runner.py`: canonical headless prompt entry and private Research Agent sequence; retain.
- `src/mia_agent/delegation.py`: bounded Agent-to-Agent runtime caller; update contract imports only.
- `src/mia_agent/herd/`: independent registry, worker state, unrestricted subagent/messaging Tools, and event bus; delete.
- `src/mia_cli/main.py`: Profile/Mode CLI aliases, dual run paths, session routing, TUI entrypoint; simplify.
- `src/mia_cli/repl.py`: ProfileManager, ModeRuntime, dual session paths, and deprecated slash commands; simplify.
- `src/mia_cli/interactive_input.py`: slash command catalogue and help text; remove legacy commands.
- `src/mia_cli/tui/`: keep visual components, replace Herd state/backend with AgentManager and AgentRunner.
- `src/mia_agent/session/entries.py`: remove Profile identity from SessionInfoEntry while retaining Agent/Run/Task/Session attribution.
- `src/mia_middleware/access.py`: remove legacy access-label normalization and `AccessPolicy.from_legacy`.
- `pyproject.toml`: retain Textual because the TUI remains supported; no new dependency.

## Affected Stories

- e06s01: Canonical Agent Run Runtime
- e06s02: Agent-Native Textual TUI Adapter
- e06s03: Remove Legacy Identity, Orchestration, and CLI Surfaces
- e06s04: Purge Legacy Project Surfaces and Verify the Clean Break

## Test Coverage

- `tests/test_agents.py`: Agent validation, persistence, built-ins, and current compatibility projection; rewrite to strict Agent behavior.
- `tests/test_access_policy.py`: access labels and middleware enforcement; replace legacy-label assertions with canonical rejection tests.
- `tests/test_orchestration.py`: Mode/Workflow/runtime behavior; replace with `tests/test_agent_runtime.py` covering AgentRunner, Run envelopes, Research Agent, and failure/cancellation.
- `tests/test_profiles.py`: Profile model/manager behavior; delete.
- `tests/test_herd_orchestrator.py`: Herd behavior; delete.
- `tests/test_tui_app.py`: TUI currently depends on Herd; rewrite against temporary AgentManager, AgentRunner, and MockProvider.
- `tests/test_cli_print_mode.py`, `tests/test_cli_repl.py`: CLI/repl aliases and dual paths; rewrite for Agent-only commands and rejection of removed interfaces.
- `tests/test_delegation.py`, `tests/test_plugins.py`, `tests/test_agent_templates.py`, `tests/test_sessions.py`, `tests/test_e2e_scenarios.py`: shared runtime and persistence regressions; update imports and assert no legacy metadata is emitted.

## Gaps

- No current test proves the runtime contract has no `mode` or `profile` fields.
- No current test proves Textual uses AgentManager/AgentRunner rather than a second orchestration root.
- No current negative test proves removed modules, CLI flags, slash commands, and compatibility aliases are absent.
- No current test proves old Profile-shaped JSON is rejected or ignored without a legacy projection.
- No current source/package scan prevents legacy symbols from returning.
- Existing guidance files still instruct agents to use the obsolete architecture and must be rewritten together.

## Risk: High

This is a high-risk shared API and identity cut: more than ten production callers cross Agent, runtime, CLI, Session, Plugin, and TUI boundaries, and the change removes rather than translates persisted legacy behavior. The TUI is deliberately kept shallow: only its backend identity and imports change; visual redesign and new TUI capabilities are out of scope.

## Recommended action

Proceed through four dependency-ordered vertical slices. Establish and test the Agent-only runtime first, rewire the TUI before deleting Herd dependencies, then remove Profile/Mode/Herd/shims and finish with an active-source/package/specification purge. Keep real user legacy files untouched and unreachable; do not add migration code.
