# e06s02 — Agent-Native Textual TUI Adapter

- **Story ID:** e06s02
- **Epic:** e06 — Agent Core Clean Break
- **Status:** passing
- **Risk:** P1

## User story

As a Mia user, I want the retained Textual frontend to list and run my named Agents through the canonical runtime without changing its existing layout.

## Contract

`MiaApp` receives `AgentManager` and `AgentRunner`, lists built-in and persisted Agents on mount, and keeps the selected Agent in the sidebar and prompt editor. Submitted prompts are validated through `AgentManager` and streamed through `AgentRunner.prompt()`.

The sidebar renders canonical Agent identity, display name, access policy, and Tool names. Ctrl+N creates a persisted coding-style Agent through `AgentManager`. Stream events are rendered by the existing panes and cards, including thought, Tool, result, completion, and Run error events.

The TUI is a shallow adapter. It does not construct `AgentHarness`, providers, Tools, middleware, or Session stores directly. Textual and `mia tui` remain supported.

## Non-goals

- Visual redesign or new interaction model.
- New Agent capabilities or a separate runtime.

## Verification

```bash
uv run --offline pytest tests/test_tui_app.py tests/test_cli_print_mode.py
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline mypy src
```

See `specs/verifications/e06s04-verify.yaml` for the final runtime and frontend evidence.
