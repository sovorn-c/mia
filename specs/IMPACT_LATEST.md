# Impact — Governed Core Extension Host

## Target

Introduce a typed, lifecycle-managed Plugin extension host after e07 establishes the constitutional Run and safeguard boundary. The change deepens the existing bundled `PluginManager` rather than adding a second execution root or adopting DeepSeek Harness as a dependency.

Primary implementation seams:

- `src/mia_agent/plugin_models.py` — manifest, API compatibility, contribution, trust, and dependency contracts.
- `src/mia_agent/plugins.py` and `src/mia_agent/plugin_catalog.py` — Plugin discovery, activation, owned registrations, disposal, and Notes migration.
- `src/mia_agent/runtime_factory.py` — compose validated immutable Run-scoped Plugin contributions inside permanent Core safeguards.
- `src/mia_agent/agent_runner.py` — expose only approved Run lifecycle observation points after e07 establishes terminal truth.
- `src/mia_middleware/pipeline.py` — preserve Core-owned final access/security validation around optional Plugin middleware.

## Requirement delta

- **ADDED:** A governed Plugin lifecycle with deterministic activation, attribution, failure, and disposal.
- **ADDED:** Inspectable strict manifest contributions for Agent Templates and static Skills, plus a small Run registration context for Tools, bounded additive context contributors, notification-only Run observers, and optional Tool middleware.
- **ADDED:** Declarative-extension and trusted-code Plugin trust classes with explicit provenance and compatibility inspection.
- **MODIFIED:** The current bundled Tool/Template Plugin contract becomes the first implementation of the broader extension host; Notes remains the proof and keeps its existing behavior.
- **MODIFIED:** The v0.6 release scope now includes the minimum extension spine while continuing to exclude Plugin commands/UI, remote catalogs, automatic package installation, hot reload, generic event/service containers, Core/provider replacement, and OS sandbox claims.
- **PRESERVED:** Agent identity, credential isolation, access policy, permanent security/audit safeguards, append-only Sessions, Run admission, terminal truth, and Plugin loading policy remain owned by Mia Core.

## Dependents

### Production callers

- `src/mia_agent/runtime_factory.py` constructs `PluginManager`, resolves Plugin Tools, filters capabilities, and creates `ToolPipeline` for direct and delegated Runs.
- `src/mia_agent/agent_runner.py` and `src/mia_agent/delegation.py` both build runtimes through `AgentRuntimeFactory`.
- `src/mia_cli/main.py` exposes Plugin and Template inspection/lifecycle commands.
- `src/mia_agent/__init__.py` exports the current Plugin contracts.
- `src/mia_agent/harness.py` executes every visible Tool through `ToolPipeline` and emits Plugin-attributed events.
- `src/mia_middleware/access.py`, `security.py`, and `telemetry.py` consume `ToolCallContext` and depend on middleware ordering.
- `src/mia_agent/agents/model.py` persists per-Agent enabled Plugins and validated Plugin configuration.

Cymbal reports 46 impact groups and 66 callers across `PluginManager`, `PluginManifest`, `AgentRuntimeFactory._build_pipeline`, `ToolPipeline`, and the planned canonical Run seam. This is a shared trust-boundary change, not an isolated catalog addition.

## Affected stories and epics

### Delivered contracts to preserve

- **e04 Agent-Centric Foundation:** Agent ownership, credentials, access, Sessions, and Delegation cannot be transferred to Plugins.
- **e05s01 Notes Plugin Vertical Slice:** install/enable/use, Agent-owned data, declared effects, and normal Tool policy remain compatible.
- **e05s02 Plugin Lifecycle Integrity:** fail-closed activation, attribution, configuration, disablement, and secret-free errors become baseline behavior.
- **e05s03 Portable Notes Agent Template:** Template privacy and independent Agent ownership remain unchanged.
- **e06s01 Canonical Agent Run Runtime:** `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only execution path.

### Planned blueprint impact

- **e07 Production Runtime Integrity:** must define the constitutional Core and safe extension ordering before the host is implemented.
- **e08 Governed Core Extension Host:** owns the lifecycle/context contract, installed-code trust seam, and Notes migration.
- **e09 Local Operations and Recovery:** must include Plugin activation/disposal failures, provenance, diagnostics, and Plugin-owned data recovery.
- **e10 Accessible Product Experience and Documentation:** must explain Plugin trust, installation, compatibility, permissions, lifecycle, author contract, and limits.
- **e11 Release and Distribution Assurance:** must verify Plugin API/version compatibility, package surface, clean installation, installed Plugin discovery, and trust-safe diagnostics.

## Test coverage

Existing coverage:

- `tests/test_plugins.py` — strict state, installation, enable/configure/disable, fail-closed contribution validation, runtime composition, access approval, audit attribution, and read-only filtering.
- `tests/test_notes_plugin.py` — Agent-owned Notes persistence and Tool behavior.
- `tests/test_plugin_cli.py` — current Plugin lifecycle commands.
- `tests/test_agent_templates.py` and `tests/test_agent_template_cli.py` — Template privacy and instantiation.
- `tests/test_agent_runtime.py`, `tests/test_agents.py`, and `tests/test_delegation.py` — shared runtime composition and Agent boundaries.
- `tests/test_middleware_pipeline.py`, `tests/test_access_policy.py`, and `tests/test_e2e_scenarios.py` — onion ordering, argument transformation, access, security, telemetry, and failure propagation.
- `tests/test_agent_loop.py`, `tests/test_cli_print_mode.py`, `tests/test_cli_repl.py`, and `tests/test_tui_app.py` — event and frontend regressions.

Required new coverage:

- Plugin activation state and deterministic dependency handling.
- Owned registration cleanup, including partial activation and async disposal failure.
- Duplicate/undeclared contribution rejection across all supported contribution types.
- Final Core policy/security validation after any Plugin Tool argument transformation.
- Mandatory audit and terminal truth that Plugin hooks cannot suppress or forge.
- Declarative versus trusted-code trust presentation and explicit activation.
- Notes behavior through the new host with no Plugin-free Agent regression.
- Plugin API compatibility and packaged clean-install smoke.

## Risk: High

The change introduces a public extension API across shared runtime, Plugin, middleware, persistence, CLI, and packaging boundaries. Incorrect ordering or excessive authority could bypass approval, lose audit evidence, corrupt Session truth, leak credentials, or make Plugin cleanup nondeterministic.

## Recommended action

Proceed through e08 after e07 using the selected narrow registration-context design in ADR 0003. Keep the executable public surface to three author operations, expose only typed capabilities rather than mutable runtime internals, and preserve a final Core validation gate that supported Plugin hooks cannot reorder or replace. Trusted same-process Python remains outside any sandbox claim. Rerun the plan audit before story slicing.
