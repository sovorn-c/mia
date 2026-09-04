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

### Design lineage: Pi/Tau and DeepSeek Harness

Mia intentionally combines complementary reference ideas. Pi/Tau contribute the lightweight, explicit, headless Agent loop, terminal-first ergonomics, and approachable extension-author experience. DeepSeek Harness (DSH) and Cordis contribute the execution-control and lifecycle patterns: onion/waterfall Tool execution, capability seams, dependency-ready activation, owned effects, rollback, and deterministic teardown. These are architectural prior art; neither system is a Mia runtime dependency.

The existing execution-control implementation is `ToolPipeline` in `src/mia_middleware/pipeline.py`. The old DSH-style profile module was removed because `Agent` is the canonical durable identity, not because extensibility moved into Agent configuration. Plugins and Templates remain separate Core-managed extension mechanisms. ADR 0003 selects a narrow Pi-like Plugin registration context with DSH-inspired lifecycle ownership while rejecting a generic event/service container and DSH's premise that every Core service is replaceable.

For production release work, `AgentRunner.run(RunRequest)` is the selected Interface. `RunRequest` is immutable and validated, and every Run using the supported consume/cancel/close contract is finalized exactly once in Core. Normal consumption emits one matching terminal envelope. Before finalization, external cancellation or awaited closure atomically finalizes `cancelled` and then reaches a cooperative cleanup decision; after finalization, late cancellation is deferred until the existing envelope is returned and awaited closure after delivery preserves the outcome. Every supported caller consumes, cancels, or wraps the returned `AsyncGenerator` in `contextlib.aclosing`; bare abandonment is unsupported. Neither interrupted path promises an envelope. Frontend Adapters own these delivery cases and never classify intermediate events independently. Concurrent Runs for one Agent-owned Session fail fast. See `specs/adr/0002-canonical-run-request-stream.md`.

## Domain boundaries

- **Agent:** durable identity and configuration, persisted in an Agent-owned home.
- **Skill:** reusable instructions or procedure.
- **Tool:** callable capability mediated by access and middleware.
- **Plugin:** installable declarative or trusted-code extension contributing only declared capabilities through the governed Core host.
- **Task:** bounded assigned work.
- **Delegation:** bounded Agent-to-Agent Task routing through Mia Core.
- **Run:** one execution of one Agent.
- **Session:** append-only JSONL history, including branching and compaction metadata.
- **Mia Core:** the trusted boundary for identity, routing, policy, attribution, persistence, and outcomes.

## Domain invariants and state transitions

- **Agent:** remains the only durable addressable identity; one Run executes one Agent, and Agent state never contains provider credentials.
- **Run:** starts with one immutable Runtime Identity and is finalized exactly once in Core; normal consumption emits one matching terminal envelope, while external cancellation or awaited stream closure records `cancelled` and reaches a cleanup completion-or-timeout decision without an envelope guarantee. Bare abandonment is unsupported; terminal Runs do not resume.
- **Task:** one caller submits bounded work to one eligible recipient; self-targeting and recursive Delegation are rejected; exactly one terminal outcome is recorded: `succeeded`, `failed`, `rejected`, `cancelled`, or `timed-out`.
- **Session:** starts as durable Agent-owned history and changes only by appending entries; branches and compaction add entries without rewriting or deleting prior history.
- **Tool Invocation:** moves from a Tool request to one Tool result through access policy and middleware; an error result is never reported as success.
- **Access Policy:** is `read-only`, `approval-required`, or explicitly confirmed `full-access`; Delegation may restrict capability scope but never increase it.
- **Core safeguards:** access, security, audit, supported execution limits, Plugin trust/lifecycle, and terminal truth are permanent runtime behavior; supported Agent and Plugin APIs may narrow capability or add behavior but cannot remove safeguards. Trusted Python remains unsandboxed.
- **Plugin activation:** a complete Agent Plugin set is planned without callbacks, activated transactionally in deterministic dependency order, and frozen for one Run. Before terminal-envelope emission, Core reaches a cleanup completion-or-timeout decision while callbacks yield control. If Core regains control at or after the deadline, it marks cleanup abandoned, diagnoses and quarantines the Plugin. Event-loop-blocking code can prevent that decision until return; that Plugin cannot activate again until process restart. Durable Plugin data remains intact and lifecycle failures do not rewrite completed domain-work truth.
- **Operational records:** attempted Tool use and terminal Run outcomes are attributable, secret-free, and append-only; telemetry failure never changes a successful side effect into a false Tool failure.

## Agent persistence

`mia_agent.agents.model.Agent` validates path-safe IDs, canonical access values, Tool and Plugin configuration, delegation targets, and secret-free metadata. `AgentManager` resolves built-in definitions and native `agent.json` files below its configured Agent root. It persists native Agents atomically and stores Sessions below the owning Agent home.

Provider credentials remain in the credential store. Agent JSON stores provider and account references, never credential values. Filesystem and process Tools validate paths and apply configured working-directory boundaries.

## Access and middleware

The supported access values are `read-only`, `approval-required`, and `full-access`. Tool effects are classified independently. Read-only Agents receive non-mutating Tools; approval-required Agents ask before side effects; full-access requires explicit consent. Security, audit, and cost middleware remains mandatory for visible Tool calls.

The middleware boundary follows the DSH-inspired onion/waterfall pattern. Core attribution and attempt audit wrap execution limits and optional Plugin middleware; after every Plugin argument transformation, a final Core gate validates schema, capability, effect, security, and approval before the Tool executor. Core result sanitation and completion audit remain outside Plugin control. No Plugin or Agent setting may remove, replace, swallow, or reorder mandatory safeguards.

Delegation applies restrictive access and capability intersection, requires eligible recipients, bounds timeouts, rejects self-targeting, and keeps payloads secret-free. Results record success, failure, rejection, cancellation, and timeout truthfully.

AgentRuntimeFactory resolves effective Agent provider, model, account reference, and invocation settings once. Frontend Adapters pass only explicit user overrides. Unsupported persisted settings fail clearly instead of being ignored; credential values never enter Agent, Run, Session, event, or operational records.

## Plugins and Templates

The target `PluginHost`, reached only through `AgentRuntimeFactory` for Run activation, owns Plugin discovery, planning, effective trust/provenance, per-Agent enablement, transactional activation, staged runtime-contribution validation, immutable Run-scoped snapshots, and cleanup completion-or-timeout decisions. A narrow `PluginContext` lets trusted code register one approved runtime contribution, observe one approved immutable Run phase, or acquire one reversible effect. Plugins never receive providers, credentials, mutable Agents or runtimes, Session stores, approval callbacks, Tool registries, or middleware lists.

Strict manifests expose declarative Agent Templates and static Skills for installation inspection and Agent creation without executing Plugin code or requiring Run activation. The v0.6 runtime contribution set is Tools, bounded additive context contributors, notification-only Run observers, and optional Tool middleware. Trusted-code Plugins are bundled or already installed and discovered through an allowlisted Python entry-point group; explicit trust is required before Agent enablement. Mia does not install dependencies or claim process isolation, and malicious same-process code can act outside the supported host API.

Plugin Tools carry Core-assigned Plugin attribution and pass through the same permanent policy pipeline as built-in Tools. Existing Notes IDs, Tools, effects, Template, configuration, data format, and Agent-owned storage remain compatible during migration. `AgentTemplate` retains its explicit allowlist and creates an independent Agent without private credentials, memory, or Session state.

## Events and Sessions

`mia_agent.events` defines immutable Agent events for turns, steps, Tool calls, Tool results, and terminal completion. `runtime_events.py` wraps them in immutable `AgentEventEnvelope` or `RunErrorEvent` values containing Run, Task, Agent, and Session attribution. Plugin observers receive only approved immutable, sanitized notifications and cannot replace, reorder, suppress, or emit these events.

Session storage is append-only JSONL. `SessionTree` reconstructs active paths and branches; `ContextCompactor` emits compaction entries without rewriting prior entries. One active Run may own an Agent/Session lineage at a time; conflicting Runs fail fast, while distinct Sessions remain independent.

## Frontends

The CLI exposes Agent, Session, Plugin, Template, authentication, and model commands. The REPL and TUI select Agents and route prompts through `AgentRunner`. The TUI remains a shallow adapter: it renders Agent events and does not construct providers, Tools, middleware, or `AgentHarness` directly.

## Package contract

`pyproject.toml` keeps `mia_ai`, `mia_agent`, `mia_middleware`, `mia_tools`, and `mia_cli` in the wheel. Textual remains declared and `mia_cli/tui/` is explicitly checked during the release gate. The public Plugin API, bundled Notes registration, and allowlisted entry-point discovery are clean-install package contracts. Removed source packages are not included.

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
