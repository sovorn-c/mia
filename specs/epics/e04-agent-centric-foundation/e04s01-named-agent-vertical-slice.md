# e04s01 — Named Agent Vertical Slice

## 1. Identity

- **Story ID:** e04s01
- **Epic:** e04 — Agent-Centric Foundation
- **Type:** feat
- **Risk:** P0
- **Context:** domain, persistence, security, and CLI
- **BCPs:** 8
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want Mia to start as a useful default Agent and let me create, inspect, select, and reopen named Agents so that I can organize personal and specialist work without learning Profile or Mode concepts.

## 3. Context

The approved product language defines Agent as Mia's only durable intelligent identity. The implementation currently exposes `AgentProfile`, `ProfileManager`, `--profile`, `/profile`, and Mode selection. Custom Profile JSON and Sessions already contain valuable user data, so the first tracer bullet must introduce the Agent path without destructive migration. The default Mia Agent must remain useful and safe: it enables current file and shell Tools under approval-required access.

## 4. Problem

Running `mia` currently defaults to the coding Profile, and there is no canonical Agent registry or Agent home. Profile configuration, Session directory selection, runtime identity, CLI selection, and tool access are connected through Profile names. A direct rename would break imports and persisted paths; adding a second unrelated Agent system would create two competing identities.

## 5. Goal

Deliver one end-to-end Agent journey: start default Mia, create a named Agent, persist it in an additive Agent home, list and inspect it, make it the selected default, execute or reopen a Session through the shared headless runtime, and continue reading legacy Profile data through one compatibility boundary.

## 6. Non-Goals

- Agent-to-Agent Delegation; delivered by e04s03.
- Complete state/access ownership hardening; delivered by e04s02.
- General Plugin loading or executable Agent packages.
- Automatic relocation or deletion of existing Profile or Session files.
- Process, filesystem, network, or operating-system sandboxing.
- Removal of legacy Profile/Mode commands; handled by e04s04.
- Interactive graphical Agent builders.

## 7. Stakeholders

- New users expecting `mia` to work without Agent setup.
- Existing users with custom Profiles and saved Sessions.
- Agent designers creating specialist configurations.
- Maintainers of runtime construction, CLI commands, security middleware, and persistence.

## 8. Dependencies

- Approved `specs/product/VISION_LATEST.yaml` and `SCOPE_LATEST.yaml`.
- Existing `AgentProfile`, `ProfileManager`, `AgentRuntimeFactory`, `MiaREPL`, Typer CLI, Session tree, and credential contracts.
- Existing Pydantic, Typer, prompt_toolkit, Rich, pytest, Ruff, and Mypy dependencies.
- e01–e03 behavior as compatibility evidence, not target architecture.

## 9. Assumptions

- Native Agents are stored additively under one Agent-specific home; existing files are never moved implicitly.
- Agent IDs are normalized path-safe identifiers; display names are separate text.
- Built-in Agent IDs are reserved and cannot be overwritten by user files.
- Native Agent definitions take precedence over legacy custom Profiles with the same non-reserved ID; collisions are reported.
- Provider secrets remain in the machine-global credential store and are not serialized into Agent definitions.
- The default Mia Agent enables `read_file`, `write_file`, `edit_file`, and `bash` with approval-required access.
- Missing approval callbacks reject side effects rather than silently running them.

## 10. Constraints

- Python 3.12+, strict Mypy, Ruff, deterministic offline tests.
- No new runtime package.
- `AgentHarness` remains one-Agent and UI-independent.
- All Tools continue through capability filtering and the middleware pipeline.
- Permanent `SecurityGuardMiddleware` rules remain active under every access level.
- Existing Profile JSON and Session JSONL remain readable.
- Agent IDs cannot escape their configured storage root.
- Writes of Agent configuration are atomic and never overwrite unrelated legacy files.
- Current `AgentEvent` payloads and streaming order remain compatible.

## 11. Domain Model

- **Agent:** durable identity and configuration with `agent_id`, display name, instructions, model/provider references, Tool capability list, Plugin references, Access Policy, limits, and metadata.
- **Agent Manager:** registry responsible for built-ins, native Agent homes, legacy Profile compatibility, path-safe CRUD, default selection, and Session location.
- **Agent Home:** logical storage root for one native Agent's definition and private state; it is not a sandbox.
- **Run:** one execution of an Agent.
- **Access Policy:** `read-only`, `approval-required`, or `full-access`.
- **Legacy Profile Adapter:** temporary compatibility projection from existing `AgentProfile` data into Agent without creating another target entity.

## 12. Requirements

### MODIFIED: Canonical configured identity

**Before:** `AgentProfile` and `ProfileManager` are the public configuration identity, and the default selection is `coding`.

**After:** Agent and AgentManager are the canonical public identity and registry, and the default selection is the built-in Agent `mia`. Existing Profile classes and imports remain temporary compatibility aliases only.

### ADDED: Default Mia Agent

Running `mia` without an Agent option or saved default MUST select Agent `mia`. It MUST provide a general personal-Agent prompt, the four current filesystem/shell Tools, and approval-required access.

### ADDED: Path-safe named Agent lifecycle

Users MUST be able to create, list, inspect, select as default, persist, reopen, and delete non-built-in Agents. IDs MUST be normalized, non-blank, unique, and unable to traverse outside Agent storage. Built-ins MUST reject overwrite and delete operations.

### ADDED: Additive Agent home

New Agent configuration and Sessions MUST be written under that Agent's home. Writes MUST be atomic. Creating or saving an Agent MUST NOT move, rewrite, or delete legacy Profile or Session data.

### MODIFIED: Legacy configuration loading

**Before:** custom definitions are loaded only from `~/.mia/profiles/*.json` as `AgentProfile`.

**After:** native Agents are loaded from Agent homes; legacy Profile JSON remains discoverable through a deterministic compatibility projection when no conflicting native Agent exists. Explicitly saving that projection creates native Agent data without deleting the source.

### MODIFIED: Runtime construction

**Before:** `AgentRuntimeFactory` receives `RuntimeIdentity.profile`, resolves through `ProfileManager`, and stores Sessions under a Profile directory.

**After:** runtime construction resolves one Agent ID, uses its native or compatibility definition, writes new Sessions under Agent ownership, and preserves provider, Tool, middleware, compaction, and Session replay contracts.

### MODIFIED: Preferred command surface

**Before:** users select `--profile` or `/profile`, and `profile list` is the management command.

**After:** `--agent`, `/agent`, and `mia agent create|list|show|use|delete` are canonical. Legacy commands remain functional compatibility aliases until e04s04 finalizes their warnings and documentation.

### ADDED: Default approval gate

The default Mia Agent MUST run `read_file` without confirmation and MUST request approval before `write_file`, `edit_file`, or `bash`. If the caller cannot provide approval, the action MUST be rejected. Approval MUST NOT disable permanent security rules.

## 13. Non-Functional Requirements

- **Compatibility:** Existing custom Profile and Session fixtures load unchanged.
- **Security:** Agent IDs are path-safe; Agent files contain no provider secrets; side effects fail closed.
- **Durability:** Agent definition writes are atomic and Session history remains append-only.
- **Determinism:** temporary directories and `MockProvider` prove Agent lifecycle offline.
- **Performance:** listing Agents performs bounded local filesystem reads and no network calls.
- **Maintainability:** one canonical Agent model owns target fields; compatibility code maps legacy data into it.

## 14. Contracts

### Existing contracts preserved

- `AgentHarness.prompt()` remains a headless `AsyncIterator[AgentEvent]`.
- Provider credentials resolve through `ConfigManager` and `FileCredentialStore`.
- Existing Profile JSON remains valid input during migration.
- `JsonlSessionStore` remains append-only.
- Tools execute through `ToolPipeline` and permanent security middleware.

### New contracts

- `Agent` is the canonical validated definition.
- `AgentManager` owns native Agent CRUD, default Mia, legacy projection, default selection, and Session lookup.
- `AgentManager` rejects unsafe IDs, reserved-ID mutation, invalid access levels, malformed files, and native/legacy collisions with actionable errors.
- Agent serialization excludes credential values.
- Approval-required side effects require a frontend-supplied approval callback and fail closed when absent.

## 15. Reason for Depth

- **Agent model and AgentManager:** Required because durable identity, native storage, compatibility precedence, Session ownership, and safe CRUD form one shared invariant that cannot remain scattered across CLI callers.
- **Legacy Profile adapter:** Required because user data must remain readable while Agent becomes canonical; direct destructive migration is not acceptable.
- **Access-policy middleware:** Required because default Mia exposes mutating Tools and approval must be enforced below every CLI rather than implemented separately in each frontend.

Keep model and manager modules aligned with the existing small profile package. Do not add repositories, factories, event buses, or Plugin abstractions for this story.

## 16. Implementation Steps

1. Add failing Agent model/registry tests covering safe identity, default Mia, reserved IDs, native precedence, legacy projection, atomic persistence, and secret-free serialization → verify: `uv run --offline pytest tests/test_agents.py -k 'model or default_mia or reserved or legacy or persist or secret' && printf 'no new security findings in affected paths\n'`
2. Introduce canonical Agent and AgentManager modules, move current built-ins into Agent definitions, and retain thin Profile compatibility aliases without duplicating source-of-truth data → verify: `uv run --offline pytest tests/test_agents.py tests/test_profiles.py -k 'builtin or compatib or create or list or show or use or delete' && printf 'no new security findings in affected paths\n'`
3. Route runtime construction and Session lookup through AgentManager while preserving provider, Tool, middleware, compaction, and append-only replay behavior → verify: `uv run --offline pytest tests/test_agents.py tests/test_orchestration.py tests/test_sessions.py -k 'agent or factory or resume or session' && printf 'no new security findings in affected paths\n'`
4. Add the minimal approval-required middleware contract and frontend callback seam needed by default Mia; read-only actions run, side effects ask, absent approval rejects, and SecurityGuard remains mandatory → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'approval or read_only or missing_callback or security' && printf 'no new security findings in affected paths\n'`
5. Add canonical `agent` CLI/REPL selection and lifecycle commands with `mia` as the no-configuration default → verify: `uv run --offline pytest tests/test_agents.py tests/test_cli_repl.py tests/test_cli_print_mode.py -k 'agent or default_mia'`
6. Run targeted compatibility and security regressions before handing the slice to full verification → verify: `uv run --offline pytest tests/test_profiles.py tests/test_orchestration.py tests/test_sessions.py tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e04s01-P0-01: Mia starts as the default Agent

```gherkin
Given no saved default Agent exists
When the user runs mia without --agent
Then Agent mia is selected
And its identity is displayed as Mia
And read_file, write_file, edit_file, and bash are enabled
And its Access Policy is approval-required
```

### Scenario SC-e04s01-P0-02: Named Agent lifecycle is durable

```gherkin
Given an isolated Mia home
When the user creates Agent researcher and makes it the default
Then agent list and agent show report researcher
And a new process selects researcher by default
And reopening its Session restores the same active conversation path
```

### Scenario SC-e04s01-P0-03: Agent IDs cannot escape storage

```gherkin
Given an Agent ID containing a path separator, parent traversal, or blank text
When AgentManager validates creation or lookup
Then it rejects the ID before filesystem access
And no file outside the Agent root is created, read, or deleted
```

### Scenario SC-e04s01-P0-04: Legacy Profiles remain readable

```gherkin
Given a valid custom Profile and saved legacy Session
And no native Agent has the same ID
When AgentManager lists and opens that identity
Then it presents one compatible Agent
And the legacy Session can be resumed
And no legacy file is moved, rewritten, or deleted
```

### Scenario SC-e04s01-P0-05: Native collision is deterministic

```gherkin
Given a native Agent and legacy Profile share an ID
When AgentManager resolves the ID
Then the native Agent wins
And the collision is reported in inspection output
And built-in IDs cannot be overwritten by either source
```

### Scenario SC-e04s01-P0-06: Approval-required default fails closed

```gherkin
Given the Mia Agent uses approval-required access
When read_file is requested
Then it runs without confirmation
When write_file, edit_file, or bash is requested
Then Mia requests approval
And denial or a missing approval callback prevents execution
And permanent security rules still apply after approval
```

### Scenario SC-e04s01-P1-07: Agent files contain no secrets

```gherkin
Given provider credentials exist in the machine credential store
When an Agent is saved or inspected
Then only provider or account references may appear
And API keys, OAuth tokens, and authorization values do not appear in Agent files or output
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_agents.py` and confirm default, CRUD, persistence, collisions, path safety, compatibility, and secret tests pass.
2. Run `uv run --offline pytest tests/test_access_policy.py -k 'approval or default_mia'` and confirm default Tool decisions fail closed.
3. Run `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -k agent` and confirm canonical Agent commands and default selection.
4. Run `uv run --offline pytest tests/test_profiles.py tests/test_orchestration.py tests/test_sessions.py` and confirm legacy configuration and Session behavior.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Run `uv run --offline pytest`.

## 19. Risks and Mitigations

- **Session orphaning:** New paths could hide legacy Sessions. Mitigation: native-first lookup with explicit legacy fallback and collision tests; no automatic moves.
- **Identity collision:** Built-ins, native Agents, and legacy Profiles may share names. Mitigation: reserved built-ins and deterministic precedence with visible diagnostics.
- **Path traversal:** Agent ID controls directories. Mitigation: strict normalized ID validation before every path operation.
- **Credential leakage:** Agent persistence could copy resolved secrets. Mitigation: schema contains references only and serialization tests scan persisted output.
- **Approval bypass:** A frontend could omit approval handling. Mitigation: missing callback rejects side effects; enforcement lives in middleware.
- **Dual taxonomy:** Compatibility aliases could remain primary. Mitigation: canonical commands and imports use Agent; aliases are thin and tested as temporary.

## 20. Definition of Done and Slopcheck

- All tasks in `e04s01-tasks.yaml` remain `failing` until their verify commands pass during implementation.
- All seven acceptance scenarios have deterministic automated coverage.
- Native Agent and legacy compatibility paths preserve user data.
- No provider secret is persisted or rendered through Agent files.
- No unresolved P0/P1 defect or security finding remains in affected paths.
- Plan consistency and the full project quality gate pass before completion.

### Slopcheck

- `[OK]` Python standard library — atomic paths, JSON compatibility, IDs, and local persistence.
- `[OK]` Pydantic (already installed) — Agent and policy validation.
- `[OK]` Typer, Rich, and prompt_toolkit (already installed) — canonical CLI/REPL surface.
- `[OK]` pytest/pytest-asyncio (already installed) — deterministic contract tests.
- No new runtime or development package is proposed.

### Red-Flag Check

Rejected these shortcuts: destructive eager migration; making Profile and Agent parallel source-of-truth models; storing copied provider secrets per Agent; allowing mutating Tools before approval enforcement; and moving the new runtime into legacy Herd because it already has multi-agent names.
