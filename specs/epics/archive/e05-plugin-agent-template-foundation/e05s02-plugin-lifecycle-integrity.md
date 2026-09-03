# e05s02 — Per-Agent Plugin Lifecycle and Integrity Boundary

## 1. Identity

- **Story ID:** e05s02
- **Epic:** e05 — Plugin and Agent Template Foundation
- **Type:** feat
- **Risk:** P0
- **Context:** domain, security, persistence, runtime, events, telemetry, and CLI
- **BCPs:** 8
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As an Agent designer, I want to inspect, configure, and disable an installed Plugin for one Agent with clear failures so that executable extensions remain understandable, reversible, and unable to bypass Mia Core.

## 3. Context

e05s01 establishes the first Notes install/enable/use path. This story closes the lifecycle and integrity gaps exposed by that tracer bullet: strict Agent Plugin state, configuration, disablement, missing/incompatible diagnostics, no partial activation, two-Agent data isolation, and optional Plugin attribution through Tool events and audit records.

## 4. Problem

A happy-path Plugin loader is unsafe if malformed manifests partially activate, Plugin configuration accepts path or secret-shaped data, disabled Tools remain visible in reused runtimes, duplicate names dispatch unpredictably, or events cannot identify their Plugin source. Existing `Agent.plugins` accepts unchecked strings, while Tool audit records know Agent/Run/Task/Session but not Plugin.

## 5. Goal

Make the bundled Plugin lifecycle fail closed and observable: users can list/show installed Plugins, configure Notes for one persisted Agent, disable it without deleting notes, and receive actionable errors for invalid states. Runtime and audit outputs carry optional Plugin attribution while all existing Plugin-free contracts remain backward compatible.

## 6. Non-Goals

- Plugin uninstall, upgrade, rollback, hot reload, or dependency solving.
- Remote or arbitrary third-party Plugin code.
- Built-in Agent customization overlays.
- Plugin-defined access levels, middleware, credentials, Sessions, or delegation routing.
- Generic JSON Schema execution for Plugin configuration.
- Notes edit/delete/search/sync.
- Agent Template behavior; completed by e05s03.

## 7. Stakeholders

- Users managing Plugin behavior on named Agents.
- Core security and runtime maintainers.
- CLI and renderer maintainers consuming additive event fields.
- Future Plugin authors relying on deterministic lifecycle errors.

## 8. Dependencies

- e05s01 Notes Plugin vertical slice.
- `Agent`, Agent storage helpers, `AgentManager`, `AgentRuntimeFactory`, `AgentHarness`, event models, Tool middleware, and audit telemetry.
- e04 access, redaction, Session, Delegation, and compatibility contracts.
- Existing standard library, Pydantic, Typer, pytest, Ruff, Mypy, and coverage.

## 9. Assumptions

- A Plugin is activated only at new runtime construction; no hot reload is promised.
- Disabling a Plugin affects later Runs and does not mutate an already-running Turn.
- Notes configuration is limited to a validated display notebook name; it never supplies a filesystem path.
- Disabled Plugin configuration may remain persisted for later re-enable, but contributes no Tools while disabled.
- Existing event consumers tolerate additive optional Pydantic fields with defaults.
- Plugin code is bundled and trusted; Tool calls remain untrusted inputs.

## 10. Constraints

- `Agent.plugins` contains normalized unique installed Plugin IDs enabled for that persisted Agent.
- Agent Plugin configuration is a strict Plugin-keyed mapping validated by the owning Plugin contract.
- Secret-shaped keys, credential values, paths, unknown config keys, and invalid types are rejected before Agent persistence.
- Manifest API compatibility is checked before Agent or runtime mutation.
- Plugin install/enable/configure/disable operations validate completely before one atomic write.
- Missing, malformed, incompatible, duplicate, or undeclared contributions reject the entire Plugin set for that runtime.
- Disablement removes Plugin Tools from later Runs but never deletes Plugin data.
- Plugin Tools receive only the owning Agent's Plugin data root and validated configuration.
- Plugin attribution is optional and defaults to `None` for existing Tools and events.
- Output and error strings remain sanitized before events, audit, or Session messages.

## 11. Domain Model

- **Plugin API Version:** core contract version required by a manifest.
- **Plugin Configuration:** validated Agent-owned settings for one Plugin; Notes supports one notebook display name.
- **Plugin State:** installed globally, enabled/configured per persisted Agent, or disabled for that Agent.
- **Plugin Attribution:** optional `plugin_id` on Plugin Tools, Tool call/result events, Tool call context, and audit records.
- **Activation Plan:** fully validated set of Plugin contributions resolved before an Agent runtime is created.

## 12. Requirements

### MODIFIED: Agent Plugin state

**Before:** `Agent.plugins` is an unchecked inert list and no Plugin configuration field exists.

**After:** enabled Plugin IDs are normalized and unique; Agent-owned Plugin configuration is validated against the installed Plugin contract and serialized without secret values. Plugin state remains inert unless PluginManager validates and resolves it.

### ADDED: Plugin inspection

Users MUST be able to list installed bundled Plugins and inspect Plugin ID, version, API compatibility, description, declared Tools/effects, configuration keys, and contributed Agent Templates without executing Plugin behavior or exposing secrets.

### ADDED: Validated per-Agent configuration

Users MUST be able to configure the Notes notebook display name for one persisted Agent. Unknown Plugins, disabled Plugins, unknown keys, path values, secret-shaped keys or values, and invalid lengths/types MUST fail before persistence.

### ADDED: Non-destructive disablement

Users MUST be able to disable Notes for one Agent. Later Runs MUST omit Notes Tools. The Agent's notes and validated configuration MUST remain intact for a later explicit re-enable. Other Agents MUST remain unchanged.

### ADDED: Atomic fail-closed activation

PluginManager MUST validate installation, API compatibility, Agent enablement, configuration, contribution declarations, Tool names, effects, and duplicate collisions before returning any Tool. One invalid enabled Plugin MUST reject the activation plan rather than partially loading the rest.

### ADDED: Plugin attribution

Plugin-contributed Tools MUST carry `plugin_id` into `ToolCallContext`, `ToolCallEvent`, `ToolResultEvent`, and `AuditLogRecord`. Existing Tools MUST expose `None` or an absent display value without changing discriminator values or renderer behavior.

### MODIFIED: Tool effect map

**Before:** `AgentRuntimeFactory` builds policy effects from the fixed built-in Tool list, and unknown Tools default fail-closed as side-effecting.

**After:** the factory builds one complete effect map from validated built-in, Delegation, and enabled Plugin Tools before policy construction. Undeclared Plugin effects reject activation; unknown runtime Tools still fail closed.

### ADDED: Actionable lifecycle errors

CLI errors MUST identify the Plugin ID, Agent ID when applicable, and corrective action for missing installation, immutable built-in Agent, disabled Plugin configuration, incompatible API version, malformed state, and duplicate contribution. Errors MUST contain no Plugin configuration secrets or note content.

## 13. Non-Functional Requirements

- **Security:** no access escalation, path injection, secret persistence/rendering, duplicate dispatch, or middleware bypass.
- **Compatibility:** additive optional fields preserve existing serialized events and UI renderers.
- **Durability:** Agent writes are atomic; disabling does not delete notes or Sessions.
- **Determinism:** lifecycle tests use injectable temporary Agent and Plugin roots and no network.
- **Observability:** audit records identify Agent, Run, Task, Session, Tool, and optional Plugin.
- **Maintainability:** Notes configuration uses one owned validator; no generic schema framework or hook bus.

## 14. Contracts

### Existing contracts preserved

- Agent IDs and files remain path-safe, strict, atomic, and secret-free.
- Built-in Agents remain immutable.
- Plugin-free runtime Tool sets and events are unchanged.
- Unknown Tools remain side-effecting/fail-closed.
- `ToolCallEvent` and `ToolResultEvent` retain existing discriminators and required fields.
- Audit middleware re-raises failures after recording sanitized diagnostics.
- Direct and delegated Runs use the same factory and access boundary.

### New contracts

- Plugin IDs use one normalizer and cannot contain path separators or traversal.
- Agent Plugin configuration is accepted only through PluginManager validation and AgentManager persistence.
- A complete activation plan is resolved before any Plugin Tool is visible.
- `BaseTool.plugin_id`, Tool event `plugin_id`, and audit `plugin_id` are optional compatibility fields.
- Disabling affects later runtime construction and preserves Agent-owned Plugin data.

## 15. Reason for Depth and Zoom-Out

- **Agent Plugin configuration field:** required because validated per-Agent settings are durable domain data and cannot live in unrestricted metadata or CLI-only files.
- **Activation-plan validation inside PluginManager:** required because partial activation across runtime callers would violate fail-closed policy; no separate planner class is needed.
- **Optional Plugin attribution fields:** required because Tool names alone do not prove executable provenance, while additive defaults preserve all existing callers.

`AgentHarness` exists to emit one ordered, sanitized async Tool/event stream for factory-built runtimes. Its callers include runtime tests, orchestration envelopes, CLI renderers, and TUI adapters. The story only adds provenance derived from the matched Tool; it does not alter dispatch order, error conversion, Session append behavior, or event discriminators.

## 16. Implementation Steps

1. Add failing lifecycle tests for strict Plugin IDs, compatible versions, per-Agent configuration, two-Agent isolation, disable/re-enable preservation, full-set rejection, and actionable secret-free errors (ref: `specs/IMPACT_LATEST.md`) → verify: `uv run --offline pytest tests/test_plugins.py tests/test_notes_plugin.py -k 'lifecycle or config or version or isolation or disable or partial or error' && printf 'no new security findings in affected paths\n'`
2. Validate unique Plugin IDs and add strict Agent-owned `plugin_config`; route all config changes through PluginManager and existing atomic AgentManager persistence, rejecting built-ins, unknown keys, paths, and secret-shaped values → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agents.py -k 'plugin_id or unique or config or atomic or builtin or secret or path' && printf 'no new security findings in affected paths\n'`
3. Resolve one complete activation plan that validates every enabled Plugin, API version, declared Tool/effect, configuration, and name collision before returning contributions; build the complete effect map before access middleware → verify: `uv run --offline pytest tests/test_plugins.py tests/test_orchestration.py tests/test_access_policy.py -k 'activation or incompatible or malformed or duplicate or effect or fail_closed' && printf 'no new security findings in affected paths\n'`
4. Implement non-destructive disable/re-enable and Notes notebook-name configuration; prove later runtimes lose/regain Tools while each Agent's fixed data root and notes remain unchanged → verify: `uv run --offline pytest tests/test_notes_plugin.py tests/test_orchestration.py -k 'configure or notebook or disable or reenable or later_run or preserve or isolation' && printf 'no new security findings in affected paths\n'`
5. Add optional `plugin_id` to BaseTool provenance, Tool call/result events, Tool context, and audit records; derive it from the matched Tool and preserve Plugin-free rendering, serialization, ordering, and redaction → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agent_loop.py tests/test_access_policy.py tests/test_cli_print_mode.py tests/test_cli_repl.py -k 'plugin_id or attribution or event or audit or redact or plugin_free' && printf 'no new security findings in affected paths\n'`
6. Add thin list/show/configure/disable commands with deterministic output and secret-free corrective errors, then run all affected regressions and coverage → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest tests/test_plugins.py tests/test_notes_plugin.py tests/test_plugin_cli.py tests/test_agents.py tests/test_orchestration.py tests/test_agent_loop.py tests/test_access_policy.py tests/test_delegation.py tests/test_sessions.py tests/test_cli_print_mode.py tests/test_cli_repl.py && ./scripts/check-coverage.sh && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e05s02-P0-01: Configuration is strict and Agent-owned

```gherkin
Given persisted Agent alpha has Notes enabled
When the user configures a valid notebook display name
Then alpha stores only the validated Notes configuration
And beta and Plugin installation state remain unchanged
And no path, credential, or secret value is persisted or rendered
```

### Scenario SC-e05s02-P0-02: Invalid Plugin state rejects the whole activation

```gherkin
Given an Agent enables one valid Plugin and one missing, malformed, incompatible, duplicate, or undeclared Plugin contribution
When Mia builds a later runtime
Then Plugin activation fails before any Plugin Tool is exposed
And no valid sibling Plugin is partially activated
And no provider or Tool code runs
```

### Scenario SC-e05s02-P0-03: Disablement is non-destructive

```gherkin
Given alpha has Notes configuration and stored notes
When the user disables Notes
Then later alpha Runs expose no Notes Tools
And its configuration and notes remain stored
When the user explicitly re-enables Notes
Then the same notes are available again under policy
```

### Scenario SC-e05s02-P0-04: Agent isolation survives shared Plugin use

```gherkin
Given alpha and beta both enable Notes with different notebook names
When each creates and lists notes
Then each sees only its own configuration and notes
And neither Agent can select the other's Plugin data root
```

### Scenario SC-e05s02-P0-05: Plugin Tools are attributable

```gherkin
Given alpha invokes note_create in Run R and Session S
When Mia emits and audits the Tool invocation
Then Tool call and result events identify Plugin notes
And the audit record identifies alpha, R, S, the Tool, and Plugin notes
And arguments, errors, and output remain sanitized
```

### Scenario SC-e05s02-P1-06: Existing Tool consumers remain compatible

```gherkin
Given a Plugin-free Agent invokes read_file
When events and audit records are rendered or serialized
Then existing discriminator values and required fields are unchanged
And plugin_id is absent or null
And CLI, REPL, and TUI consumers continue successfully
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_plugins.py tests/test_notes_plugin.py`.
2. Run `uv run --offline pytest tests/test_agent_loop.py tests/test_access_policy.py -k 'plugin_id or attribution or audit or redact'`.
3. Run `uv run --offline pytest tests/test_plugin_cli.py -k 'list or show or configure or disable'`.
4. Run `uv run --offline pytest tests/test_agents.py tests/test_orchestration.py tests/test_delegation.py tests/test_sessions.py`.
5. Run `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py`.
6. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && ./scripts/check-coverage.sh`.

## 19. Risks and Mitigations

- **Partial activation:** one bad Plugin could leave another active. Mitigation: resolve a complete immutable list before returning any contribution.
- **Duplicate dispatch:** two Tools could share a name while harness runs the first. Mitigation: reject names across all built-in, Delegation, and Plugin Tools.
- **Config path injection:** a notebook value could control storage. Mitigation: it is display-only and paths remain fixed by core.
- **Secret leak:** config/errors could contain credentials. Mitigation: strict keys/values plus existing recursive redaction at output boundaries.
- **Stale runtime:** disabling could affect an active Turn unpredictably. Mitigation: lifecycle changes apply only to later factory builds.
- **Renderer break:** required event changes could fail clients. Mitigation: optional fields with defaults and full CLI/TUI regressions.

## 20. Definition of Done and Slopcheck

- All six acceptance scenarios have deterministic automated coverage.
- All Plugin lifecycle mutations validate before one atomic write.
- Disabled Notes contributes nothing while preserving data.
- Plugin provenance is present for Plugin Tools and absent/null for existing Tools.
- No access, credential, Session, attribution, or compatibility regression remains.
- Tasks stay `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Python standard library — local lifecycle files, sets, paths, and atomic replacements.
- `[OK]` Pydantic (already installed) — strict Agent/Plugin/config/event boundaries.
- `[OK]` Typer/Rich (already installed) — lifecycle adapters and diagnostics.
- `[OK]` pytest/coverage (already installed) — security and compatibility regressions.
- No generic schema engine, watcher, loader framework, or new dependency is proposed.

### Red-Flag Check

Rejected these shortcuts: putting Plugin config in unrestricted Agent metadata; allowing partial Plugin activation; trusting Plugin-declared read effects without validation; deriving Notes paths from config; deleting data on disable; adding required event fields; logging note content in diagnostics; and implementing lifecycle separately in CLI and runtime.
