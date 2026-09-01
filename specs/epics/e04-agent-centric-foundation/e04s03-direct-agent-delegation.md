# e04s03 — Direct Agent-to-Agent Delegation

## 1. Identity

- **Story ID:** e04s03
- **Epic:** e04 — Agent-Centric Foundation
- **Type:** feat
- **Risk:** P0
- **Context:** orchestration, security, runtime, persistence, and tools
- **BCPs:** 8
- **Status:** failing
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, I want one Agent to delegate one bounded Task to another named Agent and receive an attributable result so that specialist collaboration works without exposing Workflow, Mode, Agent Instance, or DAG concepts.

## 3. Context

Named Agents and access boundaries establish durable identities, Agent-owned Sessions, Tool capabilities, and monotonic effective access. Mia's current Research Mode already executes a specialist and coordinator through `ModeRuntime`, but it hard-codes task names and Profile roles. This story extracts the smallest reusable coordination primitive: one synchronous, direct, one-hop Delegation mediated by Mia Core.

## 4. Problem

There is no public Task request/result contract, no recipient eligibility check, no core-mediated policy composition, and no Agent-usable delegation Tool. Reusing current Research Mode directly would preserve Mode/Profile terminology and fixed coordinator semantics. Allowing arbitrary recursive delegation now would introduce cycles, concurrency, mailbox, and cancellation complexity beyond the foundation.

## 5. Goal

Deliver a deterministic Delegation API and built-in `delegate_task` capability that validates one caller and recipient, creates a separately attributed child Run and Session, applies capability/access constraints without escalation, executes synchronously with a bounded timeout, and returns one terminal Task result whose success, failure, rejection, cancellation, or timeout is explicit.

## 6. Non-Goals

- Parallel, recursive, fan-out, DAG, team, mailbox, or background Delegation.
- Automatic recipient discovery, routing, bidding, or load balancing.
- Shared mutable Sessions or implicit transcript sharing.
- Persistent retry queues or recovery after process restart.
- Cross-machine, network, or channel transport.
- Plugin SDK or general executable Agent packaging.
- Streaming child events into the parent event stream.
- Human approval transport beyond the existing access-policy callback.

## 7. Stakeholders

- Users composing personal and specialist Agents.
- Agent designers declaring eligible delegation targets.
- Core runtime and Tool maintainers.
- Security and audit maintainers enforcing non-escalation.
- Session maintainers preserving caller/recipient attribution.
- Future orchestration features that may build on the direct primitive.

## 8. Dependencies

- e04s01 canonical Agent identity, AgentManager, Agent homes, and runtime selection.
- e04s02 Capability Scope, Access Policy, effective-access resolver, approval, and credential boundaries.
- Existing `AgentHarness`, `AgentRuntimeFactory`, `AgentEvent`, `MockProvider`, `ToolPipeline`, and Session JSONL contracts.
- Python 3.12 `asyncio.timeout` and UUID support.

## 9. Assumptions

- Delegation is synchronous: the caller waits until the recipient reaches a terminal outcome or timeout.
- A caller may delegate only to explicit Agent IDs in its eligible target list.
- Self-delegation and a second delegation hop are rejected in e04.
- The recipient receives the bounded Task prompt and attributed IDs, not the caller's full transcript.
- The recipient uses its own Agent definition, provider/model reference, Session home, Tool scope, and limits.
- Effective access is the more restrictive caller/recipient level with intersected capabilities.
- Default timeout is 60 seconds and the accepted maximum is 300 seconds.
- Child events stay in the child Session; the parent receives one serializable Task result through `delegate_task`.
- Provider exceptions and provider error chunks are terminal failures; `max_steps` is not success.

## 10. Constraints

- One direct recipient and one hop per Task.
- One active child Run per Delegation call; no parallel execution in this initiative.
- Task, Run, Session, caller Agent, and recipient Agent IDs must be non-blank and attributable.
- Task IDs and child Run IDs are unique per call.
- Task prompt is bounded and validated before persistence or provider use.
- Unknown recipient, ineligible target, self-target, recursive target, invalid timeout, or policy escalation is rejected before child execution.
- Credential values, authorization headers, parent transcript, and unrelated Session state never enter the Task payload.
- Caller cancellation propagates after the cancelled outcome is recorded; it is not converted into success.
- No new runtime dependency.

## 11. Domain Model

- **Task Request:** `task_id`, caller Agent ID, recipient Agent ID, bounded prompt, parent Run ID, parent Session ID, timeout, and delegation depth.
- **Task Outcome:** `succeeded`, `failed`, `rejected`, `cancelled`, or `timed-out`.
- **Task Result:** Task/Run/Session/caller/recipient attribution, terminal outcome, optional response content, and sanitized error.
- **Delegation Service:** core coordinator that validates, composes effective access, creates the child runtime, executes it, classifies terminal events, and persists attribution.
- **Delegate Task Tool:** Agent-facing adapter over the service; it is enabled only when the caller has eligible targets and depth is zero.
- **Child Run:** one recipient execution scoped to the Task.

## 12. Requirements

### ADDED: Validated Task contracts

Task request and result models MUST reject blank IDs, self-delegation, invalid timeout, unsupported depth, and outcome/payload inconsistencies. A succeeded result MUST have recipient response content; rejected, failed, cancelled, and timed-out results MUST carry sanitized terminal context without secrets.

### ADDED: Explicit recipient eligibility

A caller MUST list the recipient in its Capability Scope. The recipient MUST resolve to one valid Agent. Unknown, disabled, self, or undeclared targets MUST return `rejected` before provider or Tool execution.

### ADDED: Synchronous one-hop execution

Mia Core MUST create one unique child Run and recipient-owned Session, execute the bounded prompt, wait for one terminal outcome, and return one Task result. The recipient runtime MUST NOT receive a usable `delegate_task` Tool at depth one.

### ADDED: Effective access propagation

Delegation MUST use the more restrictive caller/recipient access level and intersected capability scope. Recipient configuration, invocation overrides, or full-access defaults MUST NOT broaden caller authority. Permanent integrity guards remain active.

### ADDED: Data minimization

The child prompt MUST contain only the bounded Task text and non-secret attribution required by the recipient. The caller transcript, provider secret values, unrelated Session entries, and frontend state MUST NOT be copied.

### ADDED: Agent-facing delegation capability

Eligible Agents MUST receive one built-in `delegate_task` Tool exposing recipient ID, Task text, and an optional bounded timeout. The Tool MUST call the same core service used by headless callers and return the serialized Task result.

### ADDED: Truthful terminal outcomes

- `succeeded`: recipient reaches a normal stop with response content.
- `failed`: provider exception/error, Agent error, invalid terminal event sequence, or `max_steps` without successful completion.
- `rejected`: validation, target eligibility, depth, or policy blocks execution before the child starts.
- `cancelled`: cancellation terminates the child; caller cancellation is recorded and re-raised.
- `timed-out`: bounded timeout expires and the child is cancelled.

No failed, rejected, cancelled, or timed-out Task may be reported as succeeded.

### ADDED: Attributable persistence

Recipient Session metadata MUST record Task ID, caller Agent ID, recipient Agent ID, parent Run ID, parent Session ID, child Run ID, and terminal outcome without secrets. Parent and child histories remain separate and append-only.

## 13. Non-Functional Requirements

- **Security:** target allowlists, monotonic access, data minimization, and credential exclusion are fail closed.
- **Reliability:** timeouts and cancellation terminate child work and cannot yield success.
- **Observability:** every result and child Session is attributable across Agent/Task/Run/Session IDs.
- **Determinism:** all terminal paths use scripted offline providers and bounded clocks.
- **Compatibility:** existing single-Agent prompt execution does not require the Delegation service.
- **Simplicity:** one hop, one recipient, one result; no scheduler or queue.

## 14. Contracts

### Existing contracts preserved

- `AgentHarness` remains responsible for one Agent's step/tool loop.
- `AgentRuntimeFactory` remains the shared construction seam.
- Session entries remain append-only with immutable parent links.
- Tools run through capability, access, security, audit, and cost middleware.
- Provider credentials resolve from the global credential store.

### New contracts

- `TaskRequest` and `TaskResult` are serializable, validated, and secret-free.
- `DelegationService.delegate()` is the only direct execution path for Agent-to-Agent Tasks.
- `DelegateTaskTool` is a thin adapter and contains no policy or runtime duplication.
- Task outcome classification consumes typed runtime events and never infers success from response text alone.
- Child Session attribution identifies the parent without sharing mutable history.

## 15. Reason for Depth

- **Task request/result models:** Required to make attribution and terminal semantics stable across headless calls, Tools, Sessions, tests, and future transports.
- **DelegationService:** Required because target validation, effective access, timeout/cancellation, runtime creation, terminal classification, and persistence must be enforced once below every caller.
- **DelegateTaskTool:** Required so an Agent can invoke the core primitive through the existing Tool loop; it remains a thin adapter rather than a Plugin system.

Do not add a scheduler, mailbox repository, task graph, worker pool, routing model, retry policy, or multi-hop protocol.

## 16. Implementation Steps

1. Add failing Task request/result validation and serialization tests for attribution, outcomes, self-targeting, timeout bounds, payload consistency, and secret exclusion → verify: `uv run --offline pytest tests/test_delegation.py -k 'contract or validation or outcome or self or timeout or secret' && printf 'no new security findings in affected paths\n'`
2. Implement the core synchronous Delegation service with target eligibility, unique IDs, recipient runtime construction, child Session attribution, and one-hop enforcement → verify: `uv run --offline pytest tests/test_delegation.py -k 'service or eligible or unique or child_session or one_hop' && printf 'no new security findings in affected paths\n'`
3. Add the thin built-in `delegate_task` Tool and inject it only for depth-zero Agents with eligible recipients → verify: `uv run --offline pytest tests/test_delegation.py tests/test_agent_loop.py -k 'delegate_tool or visible or depth or recipient' && printf 'no new security findings in affected paths\n'`
4. Apply effective access/capability composition and prove no delegated payload, Session, event, approval request, or Tool result contains provider secrets or parent transcript data → verify: `uv run --offline pytest tests/test_delegation.py tests/test_access_policy.py -k 'effective or restrict or capability or secret or transcript or escalation' && printf 'no new security findings in affected paths\n'`
5. Harden truthful terminal classification for normal stop, provider exception/error chunk, Agent error, max_steps, rejection, cancellation, and timeout → verify: `uv run --offline pytest tests/test_delegation.py tests/test_agent_loop.py tests/test_orchestration.py -k 'succeeded or failed or rejected or cancelled or timed_out or max_steps or provider_error' && printf 'no new security findings in affected paths\n'`
6. Run Delegation, Agent, access, Session, middleware, and existing orchestration regressions → verify: `uv run --offline pytest tests/test_delegation.py tests/test_agents.py tests/test_access_policy.py tests/test_sessions.py tests/test_middleware_pipeline.py tests/test_orchestration.py tests/test_e2e_scenarios.py && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e04s03-P0-01: Eligible Agent delegates successfully

```gherkin
Given caller Agent mia lists recipient Agent researcher as eligible
And both Agents have valid runtime configuration
When mia delegates one bounded Task
Then Mia Core creates unique Task and child Run IDs
And researcher executes in a recipient-owned Session
And the returned result is succeeded with caller, recipient, Task, Run, and Session attribution
```

### Scenario SC-e04s03-P0-02: Ineligible recipient is rejected before execution

```gherkin
Given the caller does not list recipient Agent unknown-or-disallowed
When Delegation is requested
Then the Task result is rejected
And no provider call, child Session, or Tool side effect occurs
```

### Scenario SC-e04s03-P0-03: Self and recursive Delegation are rejected

```gherkin
Given a caller targets itself or a depth-one recipient requests another Delegation
When Mia Core validates the Task
Then the Task is rejected
And no additional Run starts
```

### Scenario SC-e04s03-P0-04: Delegation cannot escalate access

```gherkin
Given caller and recipient have different access levels and Tool scopes
When the Task runs
Then the more restrictive access level is enforced
And only shared allowed capabilities are visible
And permanent security rules remain active
```

### Scenario SC-e04s03-P0-05: Delegation shares only bounded context

```gherkin
Given the caller Session contains unrelated conversation and machine credentials exist
When one Task is delegated
Then the recipient receives the Task text and attribution only
And no caller transcript, API key, OAuth token, or authorization value appears in the child prompt, Session, result, event, or log
```

### Scenario SC-e04s03-P0-06: Provider failure is not success

```gherkin
Given the recipient provider raises or emits a terminal error
When Delegation executes
Then the Task result is failed
And sanitized error context is returned
And no succeeded outcome is emitted or persisted
```

### Scenario SC-e04s03-P0-07: Max steps is not success

```gherkin
Given the recipient exhausts max_steps without a normal stop
When Delegation classifies the terminal events
Then the Task result is failed
And max_steps is retained as the reason
```

### Scenario SC-e04s03-P0-08: Timeout and cancellation are truthful

```gherkin
Given a child Run exceeds its bounded timeout or is cancelled
When Mia Core terminates it
Then the outcome is timed-out or cancelled respectively
And the child cannot continue in the background
And caller cancellation is recorded before cancellation propagates
```

### Scenario SC-e04s03-P1-09: Parent and child Sessions remain separate

```gherkin
Given a successful delegated Task
When both Session trees are loaded
Then each remains append-only with one active lineage
And the child records parent attribution
And neither history is merged or mutated into the other
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_delegation.py` and confirm all request/result, target, policy, timeout, cancellation, and attribution cases.
2. Run `uv run --offline pytest tests/test_agent_loop.py tests/test_orchestration.py -k 'provider_error or max_steps or cancel or terminal'`.
3. Run `uv run --offline pytest tests/test_access_policy.py tests/test_middleware_pipeline.py -k 'effective or restrict or security or secret'`.
4. Run `uv run --offline pytest tests/test_sessions.py tests/test_delegation.py -k 'session or parent or append or transcript'`.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Run `uv run --offline pytest`.

## 19. Risks and Mitigations

- **Privilege escalation:** Recipient policy or capabilities could exceed caller authority. Mitigation: shared monotonic resolver and intersection tests.
- **Secret/context leakage:** Full parent state could be copied for convenience. Mitigation: explicit minimal Task schema and persisted/output scans.
- **Runaway recursion:** Delegates could call delegates indefinitely. Mitigation: depth-zero Tool injection and depth-one rejection.
- **Hung child:** Provider or Tool may never finish. Mitigation: bounded `asyncio.timeout`, child cancellation, and no background task retention.
- **False success:** Current provider errors or max_steps may appear like completion. Mitigation: typed terminal classifier and negative-path tests.
- **Circular imports:** Tool, service, and factory could depend on each other. Mitigation: inject one callable into the thin Tool adapter; keep policy/runtime logic in the service.

## 20. Definition of Done and Slopcheck

- All tasks remain `failing` until their verify commands pass during implementation.
- All nine acceptance scenarios have deterministic automated coverage.
- One direct Task works through both headless service and Agent Tool paths.
- Rejection, failure, cancellation, and timeout cannot report success.
- No secret, unrelated transcript, or silent access escalation crosses the boundary.
- No unresolved P0/P1 security finding remains in affected paths.
- Plan consistency and the full offline quality gate pass.

### Slopcheck

- `[OK]` Python standard library — UUIDs, `asyncio.timeout`, cancellation, and bounded execution.
- `[OK]` Pydantic (already installed) — Task contract validation.
- `[OK]` existing AgentHarness, AgentRuntimeFactory, ToolPipeline, and Session store — execution and persistence seams.
- `[OK]` MockProvider and pytest-asyncio (already installed) — deterministic terminal paths.
- No new runtime or development package is proposed.

### Red-Flag Check

Rejected these shortcuts: recasting Research Mode as the public Delegation API; sharing mutable Sessions; copying complete transcripts or credentials; allowing arbitrary recipient names; recursive Tool injection; treating max_steps or provider error text as success; and introducing queues, DAGs, teams, or background workers for one synchronous call.
