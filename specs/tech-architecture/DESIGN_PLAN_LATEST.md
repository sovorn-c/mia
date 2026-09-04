# Interface Design — Canonical Run and Governed Extensions

**Status:** selected for v0.6.0 release planning
**Module:** `AgentRunner`
**Callers:** CLI, REPL, TUI, Delegation, and deterministic tests

## Requirements

The Interface must accept one validated Run request, keep credentials and runtime construction private, preserve `AgentRunner → AgentRuntimeFactory → AgentHarness`, emit attributed events in order, finalize exactly once through an atomic idempotent finalizer, reach a cleanup completion-or-timeout decision before terminal delivery or interrupted-stream return for cancellation-cooperative callbacks, and reject concurrent ownership of one Agent-owned Session. Frontend Adapters must render delivered envelopes, handle `CancelledError`, or deliberately close the stream rather than infer outcomes independently.

## Design lineage

The selected Interface preserves Mia's Pi/Tau-like lightweight, explicit Agent loop. Its Tool execution boundary retains the DeepSeek Harness (DSH)-inspired onion/waterfall model: security, approval, audit, and cost controls wrap the core executor and can observe both admission and result. The historical DSH `pre-execute → execute → post-execute` pattern is prior art, not a dependency and not a reason to introduce a second runtime or a generic event bus.

This decision separates concerns: `AgentRunner` owns Run identity and terminal truth; `AgentRuntimeFactory` composes mandatory middleware; `AgentHarness` owns the Agent loop; `ToolPipeline` owns DSH-style Tool execution wrapping. Plugins and Templates may extend supported behavior only through these Core boundaries.

## Option A — one request stream

```python
class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_text: str
    agent_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    task_id: str = "root"
    model_override: str | None = None
    cwd: Path | None = None
    compaction_threshold: float | None = None
    context_window: int | None = None
    full_access_confirmed: bool | None = None


class AgentRunner:
    def run(
        self,
        request: RunRequest,
        *,
        approval_callback: ApprovalCallback | None = None,
    ) -> AsyncGenerator[AgentEventEnvelope, None]: ...
```

Usage:

```python
from contextlib import aclosing

stream = runner.run(
    RunRequest(prompt_text=prompt, agent_id=agent_id, session_id=session_id),
    approval_callback=approve,
)
async with aclosing(stream):
    async for envelope in stream:
        renderer.on_event(envelope.event)
```

A Run becomes accepted on first iteration, not when the generator object is created. Every supported caller either consumes the stream to its terminal envelope, cancels the consuming task, or awaits `aclose()` through `contextlib.aclosing`. Bare abandonment after iteration is API misuse and has no prompt finalization or cleanup-timing guarantee.

The Implementation hides identity generation, Agent resolution, same-Session admission, provider and credential resolution, research sequencing, terminal normalization, cancellation cleanup, and Session paths. Provider/factory substitution remains a constructor dependency for tests, never request data.

This is the smallest Interface and gives high Leverage across every current Adapter. Cancellation uses normal task cancellation. It does not expose lifecycle state or a second result object.

## Option B — lifecycle handle

```python
class AgentRunner:
    def create_run(self, request: RunRequest) -> AgentRun: ...

class AgentRun(Protocol):
    identity: RuntimeIdentity
    state: RunState
    outcome: RunOutcome | None
    terminal: AgentEventEnvelope | None
    def events(self) -> AsyncIterator[AgentEventEnvelope]: ...
    def cancel(self) -> bool: ...
```

A first-class handle makes cancellation, terminal inspection, and lifecycle state explicit. It also adds state transitions, single-use rules, and more public types. Current Adapters already own the task consuming the stream, so the extra Interface is not yet justified.

## Option C — push callback and terminal result

```python
class AgentRunner:
    async def run(
        self,
        prompt_text: str,
        *,
        emit: EventConsumer,
        target: RunTarget | None = None,
        options: RunOptions | None = None,
    ) -> RunResult: ...
```

The common frontend call is direct and callback backpressure is explicit. However, event delivery failure becomes coupled to Run execution, the terminal event is duplicated in `RunResult`, and pull-based composition becomes harder. It is convenient for UI Adapters but weaker as the canonical headless Interface.

## Comparison

Option A has the greatest Depth: one request and one closeable ordered stream hide the full Run lifecycle while matching every current caller. It improves Locality because terminal truth, admission, sanitization, and cancellation cleanup live in AgentRunner. Supported callers use standard-library `contextlib.aclosing`; bare abandonment is explicit API misuse.

Option B offers the most lifecycle flexibility but exposes state current callers do not require. It should be added only if an embedded caller cannot own the consuming async task or needs post-run lifecycle inspection.

Option C optimizes event rendering, but an Adapter callback becomes part of execution correctness. The canonical headless Module should not depend on presentation delivery.

## Selected Interface

Select **Option A**.

### Invariants

1. `RunRequest` is immutable, rejects unknown fields, blank prompts, unsafe IDs, invalid thresholds, and invalid context windows.
2. Missing Agent, Run, and Session identity is resolved once before runtime construction.
3. Every supported Run emits events with one immutable Runtime Identity.
4. Every Run using the consume/cancel/awaited-close contract is finalized exactly once in Core with a terminal outcome.
5. A normally consumed stream emits exactly one envelope for that finalized outcome: `TurnCompleteEvent` for success or `RunErrorEvent` for handled failure/rejection/timeout.
6. External caller cancellation before finalization atomically finalizes the Run as `cancelled`, reaches a cleanup completion-or-timeout decision for cooperative callbacks, releases Session admission, and re-raises `CancelledError`; no envelope is promised. Cancellation after finalization is deferred for this Run: Core preserves the existing outcome, reaches the cleanup decision, and returns its terminal envelope instead of reporting cancellation.
7. Awaited `aclose()` before finalization atomically finalizes `cancelled` with a stream-closed reason and reaches the same cleanup decision. Awaited closure after terminal-envelope delivery is an idempotent no-op for outcome and lifecycle state. Bare abandonment is unsupported because Python cannot guarantee asynchronous-generator finalization timing.
8. `AgentErrorEvent`, provider failure, missing terminal output, duplicate terminal output, or post-terminal output becomes a sanitized `RunErrorEvent` owned by AgentRunner.
9. No event follows a terminal envelope. Delivery interruption changes delivery mechanics, never the exactly-once finalized outcome.
10. Concurrent Runs for the same `(agent_id, session_id)` fail fast with a finalized `session_busy` error; distinct Agent-owned Sessions may run concurrently.
11. Frontend Adapters do not create Run envelopes or classify intermediate events as terminal; they render the envelope, handle `CancelledError`, and use `contextlib.aclosing` so every early exit awaits closure.
12. `prepare_runtime` and `last_runtime` are not part of the target Interface. Session inspection, branch navigation, and compaction use explicit Session operations without exposing `AgentRuntime`, provider, Tool pipeline, or filesystem paths.

### Error codes

The terminal error taxonomy is bounded to `agent_not_found`, `session_busy`, `invalid_configuration`, `provider_error`, `agent_error`, `missing_terminal`, `contract_violation`, `cancelled`, and `runtime_error`. Error text remains sanitized and secret-free.

## Explicit non-goals

No lifecycle handle, callback event bus, remote execution protocol, scheduler, background Run manager, provider registry, compatibility overload, or generic dependency container is approved for this release.

---

# Interface Design — Governed Core Extension Host

**Status:** selected for v0.6.0 release planning

**Module:** `PluginHost` behind `AgentRuntimeFactory`

**Callers:** Plugin authors, `PluginManager`, `AgentRuntimeFactory`, `AgentRunner`, CLI inspection, and deterministic tests

## Requirements

The Interface must let installed Plugins extend an Agent without editing Mia Core while keeping Core identity, credentials, access, Session integrity, Run admission, attribution, terminal truth, and Plugin trust non-replaceable through the supported Plugin API. It must preserve current Notes and Template behavior, support deterministic activation and cleanup, expose no mutable runtime internals, make trusted-code authority explicit, and add no second execution root or runtime dependency.

The installed catalog surface is deliberately bounded to declarative Agent Templates and static Skills, which remain inspectable before an Agent or Run exists. The Run activation surface is bounded to Tools, bounded additive context contributors, notification-only Run observers, and optional Tool middleware. Every executable contribution is declared, attributed, validated, and owned by one activation. Commands, UI, providers, general services, hot reload, remote catalogs, and automatic package installation remain deferred.

## Option A — narrow registration context

```python
class PluginDefinition(Protocol):
    manifest: PluginManifest

    async def activate(self, context: PluginContext) -> None: ...


class PluginContext(Protocol):
    plugin_id: str
    agent_id: str
    config: Mapping[str, JsonValue]
    data_dir: Path

    def register(self, contribution: PluginContribution) -> None: ...
    def observe(self, phase: RunObserverPhase, observer: RunObserver) -> None: ...
    async def effect(self, acquire: EffectFactory[T]) -> T: ...
```

`register` accepts only the bounded runtime contribution union: Tool, additive context contributor, or optional Tool middleware. `observe` accepts only `run_started`, `event_emitted`, and `run_finished`; observers receive immutable sanitized values, return no replacement, and cannot suppress or emit events. `effect` records an idempotent synchronous or asynchronous disposer owned by the activation.

Agent Templates and static Skills are strict manifest/resource contributions. `PluginManager` exposes them for installation inspection and Agent creation without executing Plugin code or requiring an Agent-specific activation. Enabling a Plugin controls whether its static Skills enter that Agent's capability snapshot; a Template may reference required Plugins but is not itself activated for the source Agent.

Before activation, Core validates installation, Plugin API compatibility, effective trust, provenance, Agent enablement, configuration, exact Plugin dependencies, declarations, catalog contributions, and collisions. Runtime registrations remain staged until every enabled Plugin activates and matches its manifest. Failure rolls back all acquired effects in reverse activation order. Successful activation returns one immutable `PluginActivation` whose bounded `dispose()` is owned by AgentRunner cleanup.

This option combines Pi-like author ergonomics with the DSH/Cordis ideas of dependency-ready activation, owned effects, and deterministic teardown, without exposing a generic service container.

## Option B — governed typed service graph

```python
class PluginContext(Protocol):
    services: ServiceView
    effects: EffectScope

    def provide_service(self, key: ServiceKey[T], value: T) -> None: ...
    def register_tool(self, tool: BaseTool) -> None: ...
    def register_skill(self, skill: SkillContribution) -> None: ...
    def register_context(self, contributor: ContextContributor) -> None: ...
    def register_run_observer(self, observer: RunObserver) -> None: ...
    def register_tool_middleware(self, middleware: PluginToolMiddleware) -> None: ...
```

A dependency graph holds consumers pending until required typed services exist and disposes consumers before providers. This most closely preserves DSH composition and supports cooperating Plugins well. It also introduces service identities, providers, requirements, versioning, graph diagnostics, and roughly fifteen or more durable public types before Mia has a second Plugin that needs a shared service. That compatibility and implementation cost is not justified for v0.6.0.

## Option C — compiled declarative capability package

```python
class CoreExtensionHost(Protocol):
    def compile(self, agent: Agent) -> ActivationPlan: ...
    async def activate(self, plan: ActivationPlan) -> ActivationLease: ...
```

Manifests select only statically registered Core capabilities; package code never receives a callback. This has the smallest executable attack surface and gives deterministic activation, but every new behavior still requires a Mia release. It hardens the existing Notes bundle rather than delivering the approved developer extension seam, so it does not satisfy the product direction by itself.

## Comparison

Option A provides the deepest useful Interface: three author operations hide manifest validation, dependency order, staging, attribution, rollback, cleanup, and Core enforcement. It enables independent Plugin authors without making internal services public.

Option B is the most composable but commits Mia to a general application framework and service compatibility policy before demonstrated demand. Its strongest lifecycle ideas are retained internally by Option A; its service repository is deferred until at least two real Plugins require the same replaceable capability.

Option C is safest for a closed product but preserves the current limitation that executable capability development requires changing Core. It remains useful for declarative contributions and as the trust model for code-free packages, not as the only Plugin form.

## Selected Interface

Select **Option A**, with Option C's declarative trust tier.

### Plugin forms

1. A **declarative Plugin** contains validated catalog contributions—static Skills and Agent Templates—and executes no Python callback.
2. A **trusted-code Plugin** may contain those catalog contributions plus declared runtime contributions. It is already installed in the Python environment, discovered through an allowlisted Mia entry-point group, inspected before import where possible, and explicitly trusted before Agent enablement. Mia does not download dependencies or claim to sandbox this code.
3. Core derives effective source and provenance from the bundled catalog or installed distribution metadata. A manifest cannot promote its own trust class.

### Activation lifecycle

```text
PLANNED → ACTIVATING → ACTIVE → DISPOSING → DISPOSED
                    ↘ FAILED ──────────────↗
                                      ↘ ABANDONED
```

- Planning performs no Plugin callback and validates the complete enabled set.
- Exact dependencies must already be installed, trusted, and enabled; no dependency is enabled implicitly.
- Independent Plugins use normalized Plugin ID as a deterministic tie-breaker.
- Registrations are staged and become visible only when the complete activation succeeds.
- Partial failure requests disposal of the failing and previously activated Plugins in reverse order.
- Plugin callbacks and effect disposers have an asynchronous, cancellation-cooperative contract. While callbacks yield control, Core applies a deadline, requests cancellation on timeout, attempts every remaining disposer, and bounds how long it waits before deciding cleanup is `DISPOSED` or `ABANDONED`.
- `ABANDONED` means Core regained control at or after the deadline, stopped waiting, emitted an attributed high-severity diagnostic, and blocks new activation of that Plugin until process restart. Unsandboxed code may still run; only process isolation could guarantee termination, and that is out of scope.
- A callback that blocks the event loop or suppresses cancellation violates the trusted-code contract. It can prevent timeout, diagnostics, quarantine, terminal delivery, and cleanup from progressing until control returns. Mia documents this trust assumption and requires process restart before that Plugin can activate again instead of claiming a hard in-process bound.
- On normal completion, AgentRunner determines a candidate outcome, atomically finalizes it once, invokes `run_finished` observers, reaches a cleanup completion-or-timeout decision for cooperative callbacks, records sanitized lifecycle failures, releases admission, and only then emits the matching terminal envelope. Cleanup health does not rewrite completed domain-work truth.
- On external cancellation or awaited closure before finalization, AgentRunner atomically finalizes `cancelled`, then reaches the same cooperative cleanup decision before returning control. After finalization, late cancellation is deferred until the existing terminal envelope is returned; awaited closure after that delivery preserves the outcome and performs only idempotent bookkeeping. Bare abandonment is outside the supported contract.
- Core starts no new Plugin callback through the supported host API after a terminal envelope is emitted. Previously invoked or independently spawned trusted code may continue outside effect ownership and cannot be prevented in-process.
- Enable, configure, disable, or install changes affect later Runs only; one active Run uses an immutable activation snapshot.
- Plugin data and configuration survive disablement and disposal.

### Core execution sandwich

```text
Core attribution and durable attempt audit
  → Core cancellation and execution limits
    → deterministic Plugin Tool middleware
      → final Core schema, capability, effect, security, and approval validation
        → Tool executor
      ← Plugin post-processing
    ← Core result validation, redaction, and size bounds
← Core completion audit and truthful Tool result
```

Any Plugin argument transformation is revalidated by the final Core gate. Approval describes the final normalized arguments. Plugin middleware cannot change Tool identity, effect, attribution, Agent/Run/Session identity, call Core execution more than once, swallow a Core rejection, or fabricate a successful Tool result without execution. Terminal Run normalization remains outside every Plugin hook.

### Invariants

1. `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only prompt execution path.
2. Plugins never receive credentials, providers, mutable Agent/runtime objects, Session stores, approval callbacks, or middleware lists.
3. Core assigns Plugin attribution and validates catalog and runtime registrations against manifest declarations.
4. Duplicate or undeclared Tool, Skill, Template, observer, context, or middleware contributions reject the complete plan or activation before provider execution.
5. Static Skills are strict inspectable resources; dynamic context is timed, size-bounded, secret-checked, attributed, and appended through Core without rewriting Session history.
6. Run observers are notification-only; their failure is diagnosed but cannot alter event order or terminal truth.
7. Permanent access, security, audit, execution limits, output sanitation, and terminal truth cannot be disabled, replaced, or reordered through the supported Agent or Plugin APIs.
8. Trusted Python has process authority and malicious same-process code can act outside the supported API. Governance is a compatibility and policy boundary, not a security sandbox.
9. Notes keeps its Plugin ID, Tool names/effects, Template, Agent-owned data location, configuration, attribution, and stored format during migration.
10. Plugin-free Agents retain the same effective behavior.

## Explicit non-goals

No generic service/dependency-injection container, child-Plugin mounting, Core service replacement, provider/model adapter Plugin, credential access, mutable Session/history hook, arbitrary event bus, command or frontend contribution, Tool override, hot reload, background scheduler, remote catalog, automatic package installation, semantic-version solver, unrestricted project-local code loading, or OS/process sandbox guarantee is approved for v0.6.0.
