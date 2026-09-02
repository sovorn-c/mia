# e06s03 — Remove Legacy Identity, Orchestration, and CLI Surfaces

## 1. Identity

- **Story ID:** e06s03
- **Epic:** e06 — Zero-Legacy Agent Core
- **Type:** refactor
- **Risk:** P0
- **Context:** Agent schema, registry, access, Sessions, runtime imports, CLI, REPL, Herd removal, and tests
- **BCPs:** 8
- **Status:** failing
- **Requirement delta:** REMOVED

## 2. User Story

As a Mia user and contributor, I want the active project to expose only Agent-centric identity and execution concepts so that old MIA architecture cannot be selected, imported, or accidentally extended.

## 3. Context

The Agent model and Plugin/Delegation foundation are now released, but the active code still carries additive migration machinery: Profile persistence/projection, ModeRuntime, Workflow models, Herd, field aliases, old access labels, CLI aliases, and compatibility export shims. e06s01 establishes the replacement runtime and e06s02 removes TUI's dependency on Herd, so this story can delete the obsolete paths instead of translating them.

## 4. Problem

The current dual model creates duplicate registries and execution roots, lets contributors import historical types, and makes old storage and commands appear supported. It also keeps Profile identity in Session metadata and access aliases in security boundaries. A clean Agent product requires deletion at the source, not deprecation wrappers.

## 5. Goal

Delete Profile, Mode, Workflow, Herd, projection, alias, fallback, and re-export code from active source. Make AgentManager native-only, Agent validation strict and canonical, Sessions Agent-owned, access labels target-only, and CLI/REPL Agent-only. Preserve useful Agent, Plugin, Delegation, Session, access, provider, filesystem, and private Research behavior without automatic legacy migration.

## 6. Non-Goals

- Deleting or migrating files in a user's home directory.
- Redesigning the retained Textual TUI; e06s02 owns its minimal adapter.
- Changing AgentHarness, provider streaming, middleware security, Plugin lifecycle, or Delegation protocol semantics.
- Adding new Skills, Plugins, providers, channels, schedulers, or collaboration features.
- Preserving old commands, imports, field aliases, access labels, or storage fallback.

## 7. Stakeholders

- Public users who need one understandable Agent identity.
- Contributors extending Agent, Skill, Tool, Plugin, and Delegation behavior.
- Security maintainers responsible for strict access and metadata boundaries.
- CLI, REPL, TUI, Session, and packaging maintainers.

## 8. Dependencies

- e06s01 canonical Agent Run contracts and Agent-only factory.
- e06s02 TUI adapter with no Herd/Profile/Mode dependency.
- `Agent`, `AgentManager`, PluginManager, DelegationService, Sessions, middleware, CLI, REPL, and tests.
- Existing Python 3.12+, Pydantic, Typer, Rich, Textual, pytest, Ruff, and Mypy dependencies.

## 9. Assumptions

- Old Profile and legacy Session files are left untouched but are no longer read.
- A malformed Agent definition remains a visible validation error; it is not projected or repaired.
- The built-in `code-mode` identity is removed because Mode is not a target identity and its `run_code` capability is not implemented.
- Research remains a built-in Agent with private sequential specialist behavior.
- `AgentManager.get_agent`, `create_agent`, `save_agent`, `delete_agent`, and `set_default` are the canonical manager API.
- Existing active Agent homes and current Session JSONL remain readable when their canonical fields validate.

## 10. Constraints

- No compatibility aliases, re-export facades, projection layers, or legacy storage fallback remain in active code.
- Agent identity fields use canonical names only: `agent_id`, `display_name`, `instructions`, and `access_policy`.
- Access normalization accepts only read-only, approval-required, and full-access.
- Full-access confirmation, secret rejection, path confinement, Plugin activation, Delegation access intersection, and middleware order remain mandatory.
- TUI and CLI call AgentRunner; no frontend constructs a second runtime.
- Existing user files are not deleted, rewritten, or automatically migrated.

## 11. Domain Model

- **Agent:** the single durable configured and addressable identity.
- **Skill:** reusable instruction or procedure; no implementation change here.
- **Tool:** core-mediated callable capability; no implementation change here.
- **Plugin:** executable extension owned by an Agent configuration; no implementation change here.
- **Task/Delegation:** bounded Agent-to-Agent collaboration; no implementation change here.
- **Run/Session:** execution and durable history owned by Agent boundaries.

## 12. Requirements

### REMOVED: Profile identity and storage

**Before:** `AgentProfile`, `ProfileManager`, `agents/legacy.py`, Profile directories, Profile-to-Agent projection, collision precedence, and legacy Session fallback are active compatibility behavior.

**After:** (removed) — AgentManager resolves built-in Agents and validated native Agent definitions only. Profile modules, projection, collision reporting, and fallback storage are deleted. Legacy user files remain untouched and unreachable.

### REMOVED: Public Mode and Workflow model

**Before:** Mode, ModeCatalog, Workflow, WorkflowStage, ModeRuntime, and orchestration re-export modules are importable and selectable by users or callers.

**After:** (removed) — Agent selection is the only public execution choice. Private Research sequencing remains inside AgentRunner without public Mode/Workflow models.

### MODIFIED: Agent schema

**Before:** Agent accepts `name`, `system_prompt`, `access`, and `permission` aliases and exposes `id`, `name`, `system_prompt`, `access_level`, `access`, `permission`, and `capabilities` compatibility properties.

**After:** Agent accepts and exposes canonical fields only. Invalid historical field names and access labels are rejected by strict validation.

### MODIFIED: Agent registry API

**Before:** AgentManager accepts ProfileManager/legacy directory arguments, resolves Profiles, reports source/collision data, and exposes migration aliases such as `resolve`, `get`, `create`, `save`, and `delete`.

**After:** AgentManager owns built-in/native Agent resolution and Agent-owned Session paths. It exposes the canonical named methods only and returns Agent values rather than legacy inspection records.

### REMOVED: Herd orchestration

**Before:** `HerdManager`, ManagedAgent state, unrestricted `invoke_subagent`/messaging Tools, and Herd event models provide a second multi-Agent runtime.

**After:** (removed) — bounded Delegation and AgentRunner are the only active collaboration/execution paths. The retained TUI uses AgentManager/AgentRunner.

### REMOVED: Legacy CLI and REPL surfaces

**Before:** `profile`, `--profile`, `/profile`, `/role`, `/persona`, `--mode`, `/mode`, and Profile/Mode selection branches are available.

**After:** (removed) — `agent`, `--agent`, `/agent`, Sessions, Plugins, Templates, and current model/auth commands are the supported surfaces. Removed flags and commands fail as unknown interfaces.

### MODIFIED: Session ownership

**Before:** Session lookup can choose a Profile-based directory and SessionInfoEntry stores a Profile field.

**After:** Session paths are always under the selected Agent home and Session metadata stores Agent/Run/Task/parent attribution only. Existing append-only behavior remains.

### MODIFIED: Access vocabulary

**Before:** access policy accepts legacy `standard`, `read_only`, `no_tools`, and `full_access` labels through a mapping and exposes `from_legacy`.

**After:** access policy accepts only the three target levels; no-tools is represented by an empty Tool scope, and legacy labels are rejected.

### REMOVED: Historical built-in identity

**Before:** `code-mode` is a built-in Agent whose name and metadata encode a former Mode and whose `run_code` Tool is not part of the current Tool catalog.

**After:** (removed) — the built-in set contains only useful Agent identities with implemented capabilities.

## 13. Non-Functional Requirements

- **Security:** strict validation and existing fail-closed access/redaction behavior are preserved while compatibility input is removed.
- **Clarity:** public source and CLI expose one identity vocabulary.
- **Durability:** Agent-owned Sessions remain append-only; legacy files are not destructively touched.
- **Compatibility:** supported Agent/Plugin/Delegation/TUI behavior remains green; intentionally removed interfaces are not compatibility promises.
- **Determinism:** negative import/CLI/config tests run offline.
- **Maintainability:** one manager, one runtime factory, one prompt runner, and one collaboration primitive remain.

## 14. Contracts

### Existing contracts preserved

- Agent ID validation, atomic persistence, built-in immutability, full-access consent, secret-free metadata, and Agent-owned Plugin state.
- AgentRunner, AgentRuntimeFactory, AgentHarness, provider streaming, access middleware, security guard, audit/cost middleware, Sessions, and Delegation.
- `mia tui` behavior established by e06s02.

### Removed contracts

- Profile JSON loading/projection and Profile Session directories.
- Mode/Workflow Python imports and CLI selection.
- Herd worker state, direct messaging, unrestricted subagent Tools, and event bus.
- Agent field/access aliases, short manager aliases, and compatibility re-export modules.

### New contracts

- Invalid historical Agent field names, permission labels, commands, and imports fail clearly.
- AgentManager never reads legacy Profile or Session roots.
- A valid Agent definition is the only persisted configuration input to runtime construction.

## 15. Reason for Depth and Zoom-Out

- **Strict Agent schema:** required because aliases at the persistence boundary keep the removed identity vocabulary alive and can bypass expected validation paths.
- **Native-only AgentManager:** required because registry and Session ownership are shared by CLI, REPL, Plugins, Delegation, and TUI; deleting fallback in one caller is insufficient.
- **Deletion of mixed modules:** required because re-export shims and dead legacy classes remain discoverable public code even when no production caller uses them.
- **No migration framework:** intentional simplification; old user files remain untouched and a future explicit importer can be scoped separately if needed.

`AgentManager` exists to resolve, persist, select, and provide Agent-owned paths. Callers include AgentRunner, AgentRuntimeFactory, DelegationService, PluginManager, CLI, REPL, TUI, and tests. Its contracts are strict Agent validation, built-in immutability, atomic native persistence, default selection, Agent-owned Sessions, Tool filtering, and no legacy filesystem side effects.

## 16. Implementation Steps

1. Add failing tests for canonical-only Agent fields, rejection of old access labels/permissions, native-only Manager construction, Agent-owned Session paths, and removal of code-mode → verify: `uv run --offline pytest tests/test_agents.py tests/test_access_policy.py -k 'canonical or reject or legacy or alias or session or code_mode'`
2. Simplify Agent validation and AgentManager to canonical fields, built-in/native resolution, Agent-owned Session paths, canonical method names, and PluginManager callers; remove projection/collision/fallback behavior → verify: `uv run --offline pytest tests/test_agents.py tests/test_plugins.py tests/test_agent_templates.py tests/test_sessions.py -k 'agent or plugin or template or session' && printf 'no new security findings in affected paths\n'`
3. Remove legacy access mappings, Profile identity from SessionInfoEntry, Profile package, Agent projection helpers, ModeRuntime, mixed orchestration facade, and Herd package after all callers are updated → verify: `! find src/mia_agent -type f \( -path '*/profiles/*' -o -path '*/herd/*' -o -name 'legacy.py' -o -name 'mode_runtime.py' -o -name 'orchestration.py' \) | grep . && uv run --offline pytest tests/test_agent_runtime.py tests/test_delegation.py tests/test_plugins.py tests/test_sessions.py`
4. Reduce main CLI, REPL, and slash command catalogue to Agent-native execution, Agent-owned Sessions, Plugin/Template commands, and existing auth/model commands; remove old flags, aliases, warnings, and Profile/Mode branches → verify: `uv run --offline pytest tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_plugin_cli.py tests/test_agent_template_cli.py -k 'agent or session or plugin or template or command or removed'`
5. Replace legacy tests with Agent-only runtime/access/Session/CLI tests, delete Profile and Herd test files, update all package imports, and assert removed modules/commands/fields are unavailable → verify: `! grep -RInE '\b(AgentProfile|ProfileManager|ModeRuntime|ModeCatalog|WorkflowStage|HerdManager|ManagedAgent|AgentState|MiaHerdApp)\b|mia_agent\.(profiles|herd)|--profile|/profile|--mode|/mode|code_mode' src tests README.md && uv run --offline pytest tests/test_agents.py tests/test_access_policy.py tests/test_agent_runtime.py tests/test_delegation.py tests/test_plugins.py tests/test_agent_templates.py tests/test_sessions.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py`
6. Run the full source quality, coverage, build, and forbidden-surface checks before advancing the story → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh && uv build --offline && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e06s03-P0-01: One Agent registry

```gherkin
Given built-in and persisted Agent definitions
When AgentManager resolves or lists them
Then it reads only built-in/native Agent data
And Session paths are under the selected Agent home
And no ProfileManager, projection, collision, or fallback path runs
```

### Scenario SC-e06s03-P0-02: Strict canonical Agent schema

```gherkin
Given input containing historical name, system_prompt, access, permission, or capability aliases
When Mia validates an Agent
Then validation rejects the input
And canonical Agent fields remain the only serialized public configuration
```

### Scenario SC-e06s03-P0-03: Legacy implementation is absent

```gherkin
Given the active source tree and built package
When a contributor searches for Profile, Mode, Workflow, Herd, projection, alias, and re-export modules
Then the removed modules and symbols are absent
And only AgentRunner, AgentRuntimeFactory, AgentHarness, and Delegation provide execution/collaboration behavior
```

### Scenario SC-e06s03-P0-04: Agent-only CLI and REPL

```gherkin
Given a user invokes Mia through the CLI or REPL
When they select an Agent, inspect Sessions, use Plugins, or create a Template Agent
Then the operation uses canonical Agent surfaces
And removed Profile/Mode flags and slash commands fail without starting a Run
```

### Scenario SC-e06s03-P0-05: Existing Agent features remain green

```gherkin
Given an Agent with Tools, Plugins, access policy, Sessions, or Delegation targets
When it runs through CLI, REPL, TUI, or AgentRunner
Then existing filtering, approval, security, attribution, persistence, and truthful outcome behavior remains intact
```

### Scenario SC-e06s03-P1-06: Legacy files are non-destructively ignored

```gherkin
Given old Profile or legacy Session files exist in a temporary user home
When Mia resolves or runs a canonical Agent
Then those files are not rewritten or deleted
And no legacy identity is projected into the active registry
```

## 18. Verification Script (Step-by-Step)

1. Run canonical Agent and access tests and confirm historical fields/labels are rejected.
2. Run runtime, Plugin, Delegation, Session, and TUI tests and confirm supported behavior remains.
3. Run CLI tests and confirm Agent/Plugin/Template commands work while removed flags/commands fail.
4. Run the forbidden-symbol scan across active source, tests, README, and retained TUI.
5. Run the full quality gate and inspect the wheel for absence of deleted packages/modules.

## 19. Risks and Mitigations

- **Unseen importer:** use Cymbal refs, repository-wide search, and full import/test gate before deleting files.
- **Data loss:** never touch user Profile/legacy Session roots; test fixture hashes before and after ignored resolution.
- **CLI breakage:** update all canonical tests and assert intentional unknown-interface failures.
- **Security regression:** retain strict metadata/access tests and run the security-sensitive focused gate.
- **Research regression:** port behavior to AgentRunner before removing Mode models.
- **TUI breakage:** complete e06s02 first and run TUI tests after deletion.

## 20. Definition of Done and Slopcheck

- No Profile, Mode, Workflow, Herd, projection, compatibility alias, fallback, or re-export implementation remains in active source.
- AgentManager, AgentRunner, AgentRuntimeFactory, Delegation, Plugins, Sessions, CLI, REPL, and TUI use canonical Agent APIs.
- Removed interfaces fail clearly; user legacy files remain untouched.
- Full tests, coverage, lint, type, build, and forbidden-surface scans pass.
- All tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Existing Python standard library, Pydantic, Typer, Rich, Textual, pytest, Ruff, and Mypy — no new dependency.
- `[OK]` Deletion and direct imports — fewer abstractions and one runtime path.

### Red-Flag Check

Rejected leaving deprecated aliases “for compatibility,” silently migrating old files, keeping a facade module with obsolete exports, replacing Herd with another worker framework, or changing AgentHarness/security behavior during identity removal.
