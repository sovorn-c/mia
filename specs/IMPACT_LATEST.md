# Impact Assessment — e03s02 In-Flight Model and Session Adjustments

## Target

Extend the active `e03s02` story without creating another epic: connected-provider model discovery and provider scoping, scoped-model cycling, prompt keybindings, and direct interactive-session resume.

## Dependents (8 groups)

- `src/mia_cli/repl.py::MiaREPL.interactive_model_picker`: called by `/model`; reads credential/config state, discovers provider models, saves the chosen default, and rebuilds the runtime.
- `src/mia_cli/repl.py::MiaREPL.handle_slash_command`: called by `run_async()`, unique-prefix expansion, and CLI tests; owns `/model`, `/thinking`, and `/quit` behavior.
- `src/mia_cli/interactive_input.py::LivePromptSession._create_keybindings`: used by sync/async prompt reads and imported by REPL/layout tests.
- `src/mia_cli/main.py::main_callback`: top-level Typer callback constructing `MiaREPL`; affected by `--session`.
- `src/mia_agent/auth/config.py`: provider environment aliases, model discovery, and model-to-provider inference.
- `src/mia_agent/auth/credentials.py`: stored API-key and OAuth provider names are the durable connected-provider source.
- `tests/test_cli_repl.py`: model discovery/scoping, keybindings, exit output, and interactive resume behavior.
- `tests/test_cli_print_mode.py`: top-level CLI option forwarding.

Cymbal import graph: `interactive_input.py` has 4 importers; `repl.py` has 3 importers. The three changed CLI files have high recent churn: `repl.py` 35 commits, `interactive_input.py` 27, `main.py` 9 in 90 days.

## Affected Stories

- `e01s03`: Pi-style model switcher and CLI model options.
- `e02s01`: prompt-toolkit keybindings and completion.
- `e02s03`: durable session resume.
- `e03s01`: runtime reconstruction after model/session selection.
- `e03s02`: active command-contract story; reopened for these related adjustments.

## Contracts and Required Behavior

- `/model` discovers models only for connected providers (stored credentials/OAuth or recognized API-key environment variables), and defaults to an all-connected-provider model list.
- When several providers are connected, users can filter the model picker by provider; unconnected providers never appear.
- `/scoped-models` controls the ordered models used by Ctrl+P; Ctrl+P cycles without opening another picker.
- Shift+Tab toggles Mia's existing thinking-trace display. Ctrl+Tab cannot be implemented distinctly in prompt_toolkit/standard terminals because it is encoded as Tab; Pi's actual default is Shift+Tab.
- `/quit`, EOF, and Ctrl+C exit output includes the active session ID and `mia --session <id>` resume command.
- Top-level `mia --session <id>` constructs the interactive REPL with that session and reloads its active path through the existing runtime factory.

## Test Coverage

- Existing: `tests/test_cli_repl.py` covers provider login, model selection, slash dispatch, session resume, and prompt keybindings.
- Existing: `tests/test_cli_print_mode.py` covers Typer CLI surface.
- Add: connected-provider enumeration across stored credentials and environment aliases; no unconnected provider discovery.
- Add: scoped-model command and Ctrl+P ordered cycling.
- Add: Shift+Tab thinking toggle dispatch.
- Add: quit/EOF resume hint and top-level `--session` forwarding.

## Risk: High

The behavior is small but touches high-churn shared REPL/input surfaces and runtime reconstruction. Model/provider mistakes can select credentials for the wrong provider; session mistakes can silently start a new conversation instead of resuming.

## Recommended Action

Proceed on the existing `e03s02-essential-slash-command-contracts` branch with three vertical TDD cycles: connected/scoped models, keybindings, then session resume output/CLI alias. Add no dependency and no new command framework.
