# e04s02 — Agent-Owned State and Access Boundary

## 1. Identity

- **Story ID:** e04s02
- **Epic:** e04 — Agent-Centric Foundation
- **Type:** feat
- **Risk:** P0
- **Context:** domain, security, persistence, authentication, and middleware
- **BCPs:** 8
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Mia user, I want each Agent's state and access level to be explicit and enforced so that specialist Agents do not mix Sessions or silently gain permission to modify my environment.

## 3. Context

The named Agent slice establishes an additive Agent home and minimal approval-required default. This story completes the ownership and trust contract before Delegation is introduced. Current `AgentProfile.permission` accepts `standard`, `read_only`, `no_tools`, and `full_access`, but only Tool allowlists affect execution; middleware does not enforce those labels or request user approval. Credentials remain machine-global and must be referenced rather than copied into Agent state.

## 4. Problem

Mia currently mixes capability selection and permission labels, lacks a frontend-independent approval gate, and stores Session ownership through Profile directory conventions and orchestration metadata. Without one effective-policy resolver and explicit state paths, direct Delegation could broaden Tools, leak secret values, or write into the wrong Agent's Session.

## 5. Goal

Define and enforce one Agent ownership model for configuration, Sessions, memory paths, Plugin references, credential references, capabilities, and access. Support exactly three levels—read-only, approval-required, and full-access—while keeping empty Tool capability valid. Ensure full-access requires explicit user opt-in and never disables permanent integrity guards.

## 6. Non-Goals

- Encrypting or replacing the machine-global credential store.
- Per-Agent API-key copies or hybrid secret precedence.
- Docker, VM, OS-user, network, or process isolation.
- Plugin loading, dependency resolution, or Plugin permission prompts.
- Persistent Delegation mailboxes or Agent teams.
- Fine-grained command parsing that classifies individual shell commands as read-only.
- Organization-managed policy or remote administration.

## 7. Stakeholders

- Users selecting safe, approval-required, or autonomous operation.
- Agent designers choosing Tools and provider/account references.
- Frontend maintainers supplying approval interactions.
- Security, Session, credential, and middleware maintainers.
- Future Delegation and Plugin authors relying on effective access decisions.

## 8. Dependencies

- e04s01 Agent and AgentManager contracts.
- `BaseTool`, core filesystem/shell Tools, `ToolPipeline`, `ToolCallContext`, and `SecurityGuardMiddleware`.
- `ConfigManager` and `FileCredentialStore`.
- `JsonlSessionStore`, Session entries, and runtime identity metadata.
- Existing middleware, Session, profile-permission, and e2e security tests.

## 9. Assumptions

- Access levels order from most restrictive to most permissive: read-only, approval-required, full-access.
- Capability Scope remains independent: an Agent can expose no Tools under any access level.
- `read_file` is non-mutating. `write_file`, `edit_file`, and `bash` are side-effecting. Unknown or Plugin Tools default to side-effecting until they explicitly declare otherwise.
- Approval callbacks return allow or deny for one Tool invocation; approval is not cached in this initiative.
- A missing callback under approval-required is equivalent to denial.
- A saved full-access default is accepted only through an explicit confirmation path.
- Permanent security middleware, path confinement, schema validation, audit, and secret redaction apply under full-access.
- Delegation will later compute the effective level as the more restrictive caller/recipient policy and intersect capability scope.

## 10. Constraints

- Exactly three access levels; no `auto`, `standard`, or `no-tools` target level.
- Existing permission values map deterministically: `read_only` → read-only; `standard` → approval-required; `full_access` → full-access; `no_tools` → approval-required with an empty Tool list.
- Tool mutation metadata defaults closed: undeclared Tools are side-effecting.
- No secret value may appear in Agent JSON, Session metadata, audit output, or approval display.
- Full-access bypasses approval prompts only; it never bypasses SecurityGuard or capability filtering.
- Approval UI remains outside `mia_agent` and `mia_middleware`; core accepts a callback contract only.
- Agent state writes remain atomic and Session history append-only.
- No new runtime dependency.

## 11. Domain Model

- **Capability Scope:** enabled Tool names, Plugin references, resource roots, and eligible delegation targets.
- **Access Policy:** one of read-only, approval-required, or full-access.
- **Tool Effect:** non-mutating or side-effecting metadata used by access enforcement; unknown defaults side-effecting.
- **Approval Request:** sanitized Tool name and arguments plus Agent, Run, Task, and Session attribution.
- **Approval Decision:** allow or deny for exactly one invocation.
- **Effective Access:** most restrictive applicable level plus intersection of available capability scopes.
- **Credential Reference:** provider/account identifier resolved through the machine-global credential store; never a secret value.

## 12. Requirements

### MODIFIED: Permission vocabulary

**Before:** `AgentProfile.permission` supports `standard`, `read_only`, `no_tools`, and `full_access`, but labels are not generally enforced by middleware.

**After:** Agent Access Policy supports exactly `read-only`, `approval-required`, and `full-access`. Legacy labels map deterministically, while no-Tools behavior is represented by an empty Capability Scope.

### ADDED: Tool-effect classification

Every visible Tool MUST identify whether it is non-mutating or side-effecting. Missing classification MUST be treated as side-effecting. `bash` MUST be classified side-effecting for this initiative regardless of command text.

### ADDED: Read-only enforcement

A read-only Agent MUST expose or execute only non-mutating Tools. Attempts to invoke side-effecting or unknown Tools MUST be rejected before core execution.

### ADDED: Approval-required enforcement

An approval-required Agent MUST run non-mutating Tools automatically and request one explicit decision before each side-effecting invocation. Denial or missing approval callback MUST reject execution and remain distinguishable from Tool failure.

### ADDED: Full-access opt-in

A full-access Agent MAY run enabled Tools without per-action approval only after an explicit user confirmation when the level is selected or persisted. Full-access MUST still obey capability scope, permanent SecurityGuard rules, argument validation, auditing, timeouts, and secret protections.

### MODIFIED: Agent-owned state

**Before:** configuration is Profile JSON, Sessions are grouped by Profile name, and no canonical ownership contract covers memory, Plugin references, or channel identity.

**After:** AgentManager resolves one Agent home containing or referencing Agent configuration, Sessions, memory location, Plugin configuration, and supported channel identity. The contract is logical ownership and MUST NOT claim process or filesystem sandboxing.

### MODIFIED: Credential resolution

**Before:** runtime construction resolves provider secrets from the machine-global store without an Agent-level reference contract.

**After:** an Agent may select provider/model/account references, but secret values remain machine-global and are injected only into provider construction. Agent persistence, approval prompts, events, Sessions, Delegation payloads, and logs MUST exclude them.

### ADDED: Effective-access composition

Core MUST provide one deterministic function for combining caller, recipient, and invocation restrictions: choose the most restrictive access level and intersect capability scopes. No component may silently increase access.

## 13. Non-Functional Requirements

- **Security:** access decisions fail closed, full-access preserves permanent guards, and secrets never enter Agent state.
- **Auditability:** allow, denial, read-only rejection, and permanent security rejection retain Agent/Run/Task/Session attribution.
- **Compatibility:** legacy permission labels load through deterministic mappings.
- **Determinism:** policy matrices are fully testable without a terminal or provider network.
- **Usability:** approval output identifies the Agent, Tool, target, and effect without exposing secrets.
- **Maintainability:** one policy resolver is shared by interactive, headless, and delegated execution.

## 14. Contracts

### Existing contracts preserved

- Tool capability filtering remains a separate first gate.
- `ToolPipeline` remains onion-style and asynchronous.
- `SecurityGuardMiddleware` remains mandatory for standard built-in Agents.
- Credential values remain owned by `FileCredentialStore` and provider construction.
- Session JSONL remains append-only and existing entries remain readable.

### New contracts

- Access level parsing and legacy mapping reject unknown values.
- Tool-effect metadata defaults to side-effecting.
- Approval callbacks receive sanitized attributed context and return one decision.
- Access rejection uses a typed policy error distinct from execution failure.
- Full-access selection requires an explicit confirmation signal at its trust boundary.
- Effective access is monotonic: composition can only preserve or reduce authority.

## 15. Reason for Depth

- **AccessPolicyMiddleware:** Required because every frontend and delegated Task must enforce the same decision below the UI and above Tool execution.
- **Tool-effect metadata:** Required because approval cannot safely infer mutation from Tool names once Plugins exist; fail-closed metadata is the minimum extensible contract.
- **Effective-access resolver:** Required because Delegation composes two Agents and an invocation override; duplicated precedence logic would create privilege-escalation paths.

Do not introduce a policy DSL, role-based access-control graph, cached approvals, secret backend abstraction, or sandbox manager in this story.

## 16. Implementation Steps

1. Add a failing access matrix covering the three levels, empty capability scope, legacy mappings, unknown Tool effects, missing approval, denial, full-access, and permanent guards → verify: `uv run --offline pytest tests/test_access_policy.py -k 'matrix or legacy or unknown or denial or full_access or permanent_guard' && printf 'no new security findings in affected paths\n'`
2. Add fail-closed Tool-effect metadata to core Tools and enforce capability plus access through one middleware policy path → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'effect or capability or read_only or approval or full_access' && printf 'no new security findings in affected paths\n'`
3. Add sanitized approval callback adapters for interactive and headless CLI use; full-access selection requires explicit confirmation and absent callbacks reject → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_cli_repl.py tests/test_cli_print_mode.py -k 'approval or confirm or deny or missing_callback or full_access' && printf 'no new security findings in affected paths\n'`
4. Complete Agent-owned configuration and Session path contracts, native-first legacy fallback, provider/account references, and secret-free persistence → verify: `uv run --offline pytest tests/test_agents.py tests/test_sessions.py tests/test_credentials.py -k 'ownership or native or legacy or credential or secret or reopen' && printf 'no new security findings in affected paths\n'`
5. Add and test monotonic effective-access composition for later Delegation without exposing a general policy language → verify: `uv run --offline pytest tests/test_access_policy.py -k 'effective or restrictive or intersect or escalation' && printf 'no new security findings in affected paths\n'`
6. Run security and compatibility regressions across middleware, runtime construction, Sessions, current Profiles, and e2e Tool use → verify: `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py tests/test_agents.py tests/test_profiles.py tests/test_sessions.py tests/test_credentials.py tests/test_orchestration.py tests/test_e2e_scenarios.py && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e04s02-P0-01: Read-only removes mutation

```gherkin
Given an Agent with read-only access and file, edit, and shell capabilities configured
When its visible Tools are resolved
Then only non-mutating Tools are exposed
And a direct attempt to invoke a side-effecting or unknown Tool is rejected before execution
```

### Scenario SC-e04s02-P0-02: Approval-required asks for side effects

```gherkin
Given an Agent with approval-required access
When it invokes read_file
Then the Tool runs without an approval request
When it invokes write_file, edit_file, bash, or an unknown Tool
Then exactly one sanitized approval request is emitted
And denial prevents core execution
```

### Scenario SC-e04s02-P0-03: Missing approval fails closed

```gherkin
Given approval-required access and no approval callback
When a side-effecting Tool is requested
Then the invocation is rejected
And no Tool side effect occurs
And the result identifies policy rejection rather than Tool failure
```

### Scenario SC-e04s02-P0-04: Full-access preserves permanent guards

```gherkin
Given the user explicitly confirms full-access
When an enabled safe write is requested
Then it runs without per-action confirmation
When a permanently blocked command or path is requested
Then SecurityGuard rejects it
And Agent configuration cannot disable that guard
```

### Scenario SC-e04s02-P0-05: Empty capabilities are not an access level

```gherkin
Given an Agent with approval-required access and no enabled Tools
When runtime construction completes
Then the Agent can still converse
And the provider receives no Tool definitions
And no fourth no-tools access value exists
```

### Scenario SC-e04s02-P0-06: Effective access never escalates

```gherkin
Given caller and recipient Agents with different access levels and capabilities
When effective access is composed
Then the more restrictive level wins
And only capabilities allowed by both remain
And no override can silently broaden the result
```

### Scenario SC-e04s02-P0-07: Secrets remain machine-global

```gherkin
Given a provider API key and an Agent provider reference
When the Agent is saved, inspected, resumed, audited, or used in an approval request
Then the provider reference remains visible where needed
And the API key does not appear in Agent files, Session entries, events, logs, or output
```

### Scenario SC-e04s02-P1-08: Logical ownership is honest

```gherkin
Given two Agents on the same operating-system account
When their state paths are inspected
Then configuration and Sessions are separated by Agent ownership
And documentation does not claim process, filesystem, network, or credential sandboxing
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_access_policy.py` and confirm every policy/effect combination.
2. Run `uv run --offline pytest tests/test_middleware_pipeline.py tests/test_e2e_scenarios.py -k 'security or policy or tool'`.
3. Run `uv run --offline pytest tests/test_agents.py tests/test_sessions.py tests/test_credentials.py -k 'ownership or credential or secret or legacy'`.
4. Run `uv run --offline pytest tests/test_cli_repl.py tests/test_cli_print_mode.py -k 'access or approval or full_access'`.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Run `uv run --offline pytest`.

## 19. Risks and Mitigations

- **Privilege escalation:** Inconsistent precedence could broaden delegated authority. Mitigation: one monotonic resolver and exhaustive policy matrix.
- **Approval bypass:** Missing callbacks or unclassified Tools could execute. Mitigation: both default to rejection/side-effecting.
- **False full-access promise:** Users may assume permanent guards are disabled. Mitigation: confirmation and help text state exact semantics.
- **Secret leakage:** Provider values could enter Agent JSON or approval output. Mitigation: reference-only schema and persistence/output scans.
- **Session collision:** Native and legacy paths may contain the same ID. Mitigation: deterministic native-first lookup and explicit collision diagnostics.
- **Frontend coupling:** Core approval code could import terminal UI. Mitigation: callback protocol only; adapters stay in CLI.

## 20. Definition of Done and Slopcheck

- All tasks remain `failing` until their commands pass during implementation.
- All eight acceptance scenarios have deterministic automated coverage.
- Three and only three target access levels are accepted.
- Full-access never bypasses permanent guards.
- Agent and approval artifacts contain no secret values.
- No unresolved P0/P1 security finding remains in affected paths.
- Plan consistency and the full offline quality gate pass.

### Slopcheck

- `[OK]` Python standard library — callback protocols, enums/literals, and monotonic comparisons.
- `[OK]` Pydantic (already installed) — access and Agent validation.
- `[OK]` existing ToolPipeline and middleware contracts — enforcement seam.
- `[OK]` pytest/pytest-asyncio (already installed) — policy matrix and async callback tests.
- No new runtime or development package is proposed.

### Red-Flag Check

Rejected these rationalizations: treating no-Tools as another approval level; trusting unknown Tools as read-only; letting full-access disable SecurityGuard; copying secrets into Agent homes for convenience; embedding terminal prompts in middleware; and building a general policy DSL before three fixed levels prove insufficient.
