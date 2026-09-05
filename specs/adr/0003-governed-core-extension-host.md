---
status: accepted
---

# Use a governed registration context for Core extensions

Mia will remain Agent-centric at the product surface and add a Plugin-composable extension host behind `AgentRuntimeFactory`. Strict manifests expose declarative Agent Templates and static Skills for inspection and Agent creation without running Plugin code. Trusted-code Plugins activate for an Agent Run through a narrow `PluginContext` with three author operations: register one typed runtime contribution, observe one approved Run phase, and acquire one Core-owned reversible effect. The runtime contribution union is limited to Tools, bounded additive context contributors, notification-only Run observers, and optional Tool middleware.

Mia Core plans the complete enabled Plugin set without executing callbacks, validates installation, API compatibility, effective trust, provenance, Agent enablement, configuration, exact dependencies, declarations, catalog contributions, and collisions, then activates Plugins in deterministic dependency order. Registrations remain staged until the complete set succeeds. Every runtime registration and resource belongs to one immutable Run-scoped activation. Core requests reverse-order disposal and reaches a completion-or-timeout decision on failure, completion, awaited stream closure, or cancellation. Supported callers must consume, cancel, or await closure; bare stream abandonment is outside the contract. Catalog Templates remain inspectable independently of Run activation; enabled static Skills enter the Agent's immutable capability snapshot.

The extension host adopts Pi-like author ergonomics and the DeepSeek Harness/Cordis principles of dependency-ready activation, owned effects, rollback, and deterministic teardown. It does not adopt DSH's premise that every Core service is replaceable and does not import either system as a dependency.

## Constitutional boundary

Through the supported Plugin API, Plugins cannot replace or directly access Agent identity, credential resolution, access policy, approval decisions, permanent safeguards, Session ownership or mutation, Run admission, event attribution, cancellation ownership, Delegation routing, terminal truth, Plugin trust, or Plugin lifecycle policy. They do not receive `AgentRunner`, `AgentRuntimeFactory`, `AgentHarness`, providers, credentials, mutable Agents, Session stores, approval callbacks, Tool registries, or middleware lists.

Plugin Tool middleware executes inside permanent Core controls. Any transformed arguments pass through a final Core schema, capability, effect, security, and approval gate before the Tool executor. Core audit wraps attempts and results; Core sanitation and terminal normalization remain outside Plugin control. A Plugin cannot suppress a Core rejection, execute the Tool more than once, or fabricate successful execution.

## Trust and discovery

Mia distinguishes declarative Plugins from trusted-code Plugins. Declarative Plugins contain validated static Skills and Agent Templates and execute no callback. Trusted-code Plugins are bundled or already installed in the Python environment, discovered through an allowlisted Mia entry-point group, and explicitly trusted before Agent enablement. Mia does not download Plugin dependencies and does not claim to sandbox trusted Python code. Malicious same-process code can act outside the supported Plugin API; the constitutional boundary is an enforceable host contract, not process isolation. Effective provenance comes from the bundled catalog or installed distribution metadata, not from a Plugin's self-description.

## Consequences

- `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only prompt execution path.
- The current Notes Plugin and Agent Template migrate without changing IDs, Tool behavior, configuration, data format, or Agent-owned storage.
- Plugin activation becomes transactional and lifecycle cleanup becomes explicit, idempotent, and attributable. Core bounds its cooperative wait, not arbitrary same-process Python execution.
- Agent Templates remain inspectable and usable before Run activation; static Skills are selected into an enabled Agent's snapshot.
- Agent and Plugin changes affect later Runs only; active Runs use immutable activation snapshots.
- On normal completion, Core atomically finalizes the candidate outcome, runs final observers, and reaches a cleanup completion-or-timeout decision before emitting the matching terminal envelope; observer or cleanup failures are separate attributed diagnostics rather than retroactive changes to domain-work truth.
- Plugin callbacks and disposers must be asynchronous and cancellation-cooperative. While they yield control, Core can enforce a deadline, mark cleanup abandoned, diagnose and quarantine the Plugin, and proceed. Code that blocks the event loop can prevent those actions until it returns; trusted same-process recovery then requires process restart.
- Every Run used through the supported consume/cancel/close contract is finalized exactly once through an atomic idempotent Core finalizer. Before finalization, external caller cancellation or awaited closure atomically finalizes `cancelled` and then reaches a cooperative cleanup decision. After finalization, late cancellation is deferred until the existing terminal envelope is returned; awaited closure after terminal delivery preserves the outcome. Neither interrupted path guarantees an envelope.
- Plugin API versioning and trust presentation become release compatibility commitments.
- A general service repository is deferred until multiple real Plugins require one shared replaceable capability.
- Commands, frontend components, providers, Core service replacement, generic events, hot reload, remote catalogs, automatic package installation, background work, and OS sandbox guarantees remain out of scope for v0.6.0.
