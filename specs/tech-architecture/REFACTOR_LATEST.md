# Architecture Deepening — v0.6.0 Production Release

**Status:** approved for release planning
**Scope:** architecture constraints only; implementation is deferred to `/bp-plan`

## Forcing function

Mia already has one canonical execution path, but production outcomes still leak across frontend Adapters or depend on Agent-controlled configuration. Its Plugin implementation is also a closed bundled Tool/Template catalog rather than the governed developer extension seam described by the product vision. A production release must make terminal truth, permanent safeguards, Session ownership, local diagnostics, and Plugin lifecycle ownership properties of Mia Core rather than conventions repeated by callers.

## Design lineage to preserve

The architecture is deliberately hybrid. Pi/Tau provide the lightweight explicit Agent-loop model and approachable extension ergonomics. DeepSeek Harness (DSH) and Cordis provide prior art for onion/waterfall Tool execution, capability seams, dependency-ready activation, owned effects, rollback, and deterministic teardown. Mia keeps these principles without importing either runtime, exposing a generic event or service container, or adopting DSH's premise that every Core service is replaceable.

The production work must strengthen the existing boundary, not flatten controls into individual Tools, expose mutable runtime internals, or turn either reference into a second public execution root. Agent remains the durable user-facing composition; Plugin becomes the governed developer extension mechanism; Mia Core remains non-replaceable through their supported APIs. Trusted same-process Python is explicitly outside any sandbox guarantee.

## Deepening candidates

### 1. AgentRunner Run Interface — selected (Depth 2/5)

- **Files:** `src/mia_agent/agent_runner.py`, `src/mia_agent/runtime_events.py`, CLI/REPL/TUI callers.
- **Problem:** frontend Adapters classify failure differently; a provider `AgentErrorEvent` can end without the documented terminal Run outcome. The long prompt parameter list and `last_runtime` state also expose runtime construction details.
- **Deletion test:** removing print mode's separate `AgentErrorEvent` check can turn a failed Run into a successful process exit. The terminal rule therefore does not live at the canonical seam.
- **Deepening outcome:** the AgentRunner Module accepts one validated Run request, finalizes every Run using the supported consume/cancel/close contract exactly once, emits one matching terminal envelope on normal consumption, and records cancellation before cleanup returns control on external cancellation or awaited stream closure. Every supported caller consumes, cancels, or awaits closure; bare abandonment is excluded.
- **Benefits:** one Interface gives every Adapter the same terminal semantics, increases Leverage across all frontends, and concentrates lifecycle fixes and tests for better Locality.

### 2. Permanent runtime safeguards (Depth 3/5)

- **Files:** `src/mia_agent/runtime_factory.py`, `src/mia_agent/agents/model.py`, middleware modules.
- **Problem:** Agent configuration can omit security, audit, or budget middleware even though Mia Core owns permanent safeguards.
- **Deletion test:** deleting a middleware name from one Agent can remove protection without changing the Run Interface.
- **Deepening outcome:** permanent access, security, audit, and supported execution-limit behavior stays unconditional inside AgentRuntimeFactory; optional Agent middleware may only add behavior.
- **Benefits:** one composition point protects direct Runs, Delegation, Plugins, and research sequencing.

### 3. Local operational telemetry (Depth 1/5)

- **Files:** `src/mia_middleware/telemetry.py`, `src/mia_agent/runtime_factory.py`.
- **Problem:** audit records are retained only in a middleware instance, access/security rejections can bypass audit, and cost enforcement is not connected to provider usage.
- **Deletion test:** deleting current audit retention has no durable production-visible effect.
- **Deepening outcome:** persist a minimal append-only, attributed, secret-free local audit record for attempted Tool calls and define honest failure behavior. Either enforce cost from real usage or remove the unsupported claim.
- **Benefits:** actionable local diagnostics without a remote telemetry platform or generic event bus.

### 4. Effective provider configuration (Depth 2/5)

- **Files:** `src/mia_agent/runtime_factory.py`, `src/mia_agent/auth/`, frontend Adapters.
- **Problem:** persisted Agent provider, account, and temperature fields are not consistently executable; frontend overrides can mask Agent-owned selection.
- **Deletion test:** removing these fields currently changes little or no runtime behavior.
- **Deepening outcome:** resolve the effective provider, model, account reference, and invocation settings once at the existing factory seam; reject unsupported values instead of ignoring them.
- **Benefits:** consistent Agent behavior and one place to test precedence and credential safety.

### 5. Active Session admission (Depth 2/5)

- **Files:** `src/mia_agent/agent_runner.py`, `src/mia_agent/session/`, TUI worker.
- **Problem:** concurrent Runs can target the same Agent-owned Session and produce timing-dependent lineage.
- **Deletion test:** removing same-Session admission allows competing restored heads and nondeterministic parentage.
- **Deepening outcome:** fail busy or serialize one active Run per Agent/Session while allowing distinct Sessions to proceed independently.
- **Benefits:** append-only history remains deterministic without a scheduler or background-run framework.

### 6. Governed Core extension host (Depth 3/5)

- **Files:** `src/mia_agent/plugin_models.py`, `src/mia_agent/plugins.py`, `src/mia_agent/plugin_catalog.py`, `src/mia_agent/runtime_factory.py`, `src/mia_agent/agent_runner.py`, and `src/mia_middleware/pipeline.py`.
- **Problem:** the current catalog hard-codes Notes and resolves only bundled Tools/Templates; it has no general Plugin activation, owned registration, cleanup, dependency, trust, or safe runtime-hook contract.
- **Deletion test:** adding executable behavior still requires editing Core, while an ad-hoc callback could bypass policy or leak lifecycle resources.
- **Deepening outcome:** add inspectable manifest Skills/Templates plus one narrow runtime Plugin registration context with transactional activation, immutable Run snapshots, Core-assigned attribution, reversible effects, explicit trust, and a final Core Tool gate that supported hooks cannot reorder.
- **Benefits:** developers can extend Agents without forking Core, while users retain predictable identity, policy, Session, and outcome guarantees.

## Architecture constraints

1. Keep `AgentRunner → AgentRuntimeFactory → AgentHarness` as the only execution path.
2. Keep AgentHarness headless and asynchronous.
3. Make terminal Run status and permanent safeguards Mia Core invariants.
4. Keep Sessions append-only and reject or serialize conflicting ownership.
5. Keep provider credentials in the credential store and telemetry secret-free.
6. Add no policy language, generic event or service container, Core replacement mechanism, remote observability backend, scheduler, provider Plugin framework, or compatibility layer. The e08 host may register only the bounded contribution types approved by ADR 0003.
7. Put optional Plugin Tool middleware inside permanent Core controls and revalidate transformed arguments before execution.
8. Test through the selected Run Interface; retain lower-level tests only for independent trust-boundary and Plugin lifecycle behavior.

## Decision

Implement the selected AgentRunner Run Interface and constitutional safeguards before the governed extension host. The other candidates and Plugin contributions must reuse that Interface and existing factory/middleware seams rather than create parallel execution roots. The selected Plugin Interface is recorded in `DESIGN_PLAN_LATEST.md` and ADR 0003.
