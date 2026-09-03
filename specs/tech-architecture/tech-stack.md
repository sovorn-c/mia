# Mia Technical Architecture

## Stack

- Python 3.12+
- Pydantic 2 for boundary models and persistence
- AnyIO and async generators for provider and Agent execution
- Typer and Rich for the CLI
- prompt-toolkit for the REPL
- Textual for the retained shallow TUI
- pytest, pytest-asyncio, Ruff, Mypy, and Coverage for quality gates
- Hatchling and `uv build --offline` for packaging

## Runtime

```text
CLI/REPL/TUI
    ↓
AgentRunner
    ↓
AgentRuntimeFactory
    ↓
AgentHarness
    ↓
Provider ── Middleware ── Tools ── Agent-owned Session
```

`AgentRunner` is the canonical headless prompt entry point. It creates a fresh Run and Session identity, resolves the selected Agent, and yields attributed events. `AgentRuntimeFactory` composes the provider, visible Tools, access middleware, security guards, persistence, and context restoration. `AgentHarness` executes one asynchronous Agent loop and has no terminal UI dependency.

The Research Agent keeps its existing private specialist-then-synthesis sequence inside the runner. It does not add another public runtime object or composition root.

## Domain boundaries

- **Agent:** durable identity and configuration, persisted in an Agent-owned home.
- **Skill:** reusable instructions or procedure.
- **Tool:** callable capability mediated by access and middleware.
- **Plugin:** installable extension contributing declared Tools and Templates.
- **Task:** bounded assigned work.
- **Delegation:** bounded Agent-to-Agent Task routing through Mia Core.
- **Run:** one execution of one Agent.
- **Session:** append-only JSONL history, including branching and compaction metadata.
- **Mia Core:** the trusted boundary for identity, routing, policy, attribution, persistence, and outcomes.

## Agent persistence

`mia_agent.agents.model.Agent` validates path-safe IDs, canonical access values, Tool and Plugin configuration, delegation targets, and secret-free metadata. `AgentManager` resolves built-in definitions and native `agent.json` files below its configured Agent root. It persists native Agents atomically and stores Sessions below the owning Agent home.

Provider credentials remain in the credential store. Agent JSON stores provider and account references, never credential values. Filesystem and process Tools validate paths and apply configured working-directory boundaries.

## Access and middleware

The supported access values are `read-only`, `approval-required`, and `full-access`. Tool effects are classified independently. Read-only Agents receive non-mutating Tools; approval-required Agents ask before side effects; full-access requires explicit consent. Security, audit, and cost middleware remains mandatory for visible Tool calls.

Delegation applies restrictive access and capability intersection, requires eligible recipients, bounds timeouts, rejects self-targeting, and keeps payloads secret-free. Results record success, failure, rejection, cancellation, and timeout truthfully.

## Plugins and Templates

`PluginManager` owns the bundled catalog, installed state, per-Agent enablement, configuration, and Tool composition. Plugin Tools carry their Plugin ID and pass through the same policy pipeline as built-in Tools. `AgentTemplate` uses an explicit allowlist and creates an independent Agent without private credentials, memory, or Session state.

## Events and Sessions

`mia_agent.events` defines immutable Agent events for turns, steps, Tool calls, Tool results, and terminal completion. `runtime_events.py` wraps them in immutable `AgentEventEnvelope` or `RunErrorEvent` values containing Run, Task, Agent, and Session attribution.

Session storage is append-only JSONL. `SessionTree` reconstructs active paths and branches; `ContextCompactor` emits compaction entries without rewriting prior entries.

## Frontends

The CLI exposes Agent, Session, Plugin, Template, authentication, and model commands. The REPL and TUI select Agents and route prompts through `AgentRunner`. The TUI remains a shallow adapter: it renders Agent events and does not construct providers, Tools, middleware, or `AgentHarness` directly.

## Package contract

`pyproject.toml` keeps `mia_ai`, `mia_agent`, `mia_middleware`, `mia_tools`, and `mia_cli` in the wheel. Textual remains declared and `mia_cli/tui/` is explicitly checked during the release gate. Removed source packages are not included.

## Quality and security

Run the complete offline gate:

```bash
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline mypy src
uv run --offline pytest
./scripts/check-coverage.sh
uv build --offline
```

The public-surface script scans source, tests, docs, and specs for removed names, imports, commands, and package paths. It must run before the package gate. No check prints credential values.
