# Ubiquitous Language

Projection of `specs/product/GLOSSARY_LATEST.yaml`.

> **Core invariant:** Agent acts; Skill guides; Tool enables; Plugin extends; Agent delegates through Mia Core.

## Agent

Mia uses **Agent** for its only durable, configured, addressable intelligent identity.

```text
Mia Core
  └── Agent
        ├── instructions and model
        ├── Skills and Tools
        ├── Plugins and access policy
        ├── private state and Sessions
        └── bounded Delegation to other Agents
```

A **Run** is one execution of an Agent. A **Session** is durable append-only history. A **Task** is bounded work. **Delegation** routes a Task between Agents through Mia Core.

## Core terms

| Term | Definition |
| --- | --- |
| **Mia Core** | Trusted runtime boundary for Agent execution, routing, policy, persistence, events, and Plugin lifecycle. |
| **Agent** | Durable identity combining configuration, state, capabilities, access policy, Plugins, and collaboration behavior. |
| **Skill** | Reusable instruction, knowledge, or procedure that guides an Agent. |
| **Tool** | Callable capability exposed through core policy and middleware. |
| **Plugin** | Installable declarative or trusted-code extension contributing approved declared capabilities through the governed Core host. |
| **Plugin Activation** | Immutable Run-scoped snapshot of one Agent's planned and transactionally activated runtime Plugin contributions and owned effects. |
| **Plugin Contribution** | Core-approved Tool, Agent Template, static Skill, bounded additive context contributor, notification-only Run observer, or optional Tool middleware registered by one Plugin. |
| **Plugin Trust** | Core-assigned effective authority based on provenance; declarative Plugins execute no callback and trusted-code Plugins require explicit trust. |
| **Agent Template** | Shareable starting definition used to create an independent Agent without private state. |
| **Task** | Bounded work assigned to an Agent with one attributable outcome. |
| **Delegation** | Core-mediated assignment of a Task between eligible Agents. |
| **Run** | One prompt- or Task-scoped execution of one Agent. |
| **Session** | Append-only conversation history owned by an Agent and reusable across Runs. |
| **Access Policy** | `read-only`, `approval-required`, or `full-access`; controls mutation and confirmation. |
| **Capability Scope** | Declared Tools, Plugins, resources, and delegation targets available to an Agent. |

## Aliases to avoid

| Canonical term | Avoid using |
| --- | --- |
| **Agent** | Profile, Mode, identity, assistant — when referring to a durable configured identity. |
| **Run** | Session, task — when referring to one execution. |
| **Session** | Run, transcript — when referring to durable append-only history. |
| **Task** | Backlog item, request — when referring to bounded runtime work assigned to an Agent. |
| **Delegation** | Swarm, unrestricted orchestration — when referring to one bounded core-mediated assignment. |
| **Tool** | Skill, prompt — when referring to a callable capability. |
| **Plugin** | Unmanaged extension — when referring to an installable extension governed by Mia Core. |

Having no Tools is capability configuration, not a fourth access level. Full access requires explicit consent and never disables permanent credential or integrity safeguards.

## Extension and collaboration

A Plugin may contribute only approved declared types. Agent Templates and static Skills are inspectable manifest resources that require no Run activation. Tools, bounded additive context, notification-only Run observers, and optional Tool middleware belong to one transactional Run activation. Mia Core assigns trust and attribution, freezes runtime contributions for one Run, and owns cleanup. The supported Plugin API cannot replace Core access, approval, credential secrecy, routing, Session integrity, event attribution, cancellation, or truthful outcomes; trusted Python remains able to act outside that API with normal process authority.

```text
Mia → delegates a Task to Research Agent → receives an attributable result
    → delegates implementation to Coding Agent → returns the final result
```

Mia Core owns discovery, routing, attribution, restrictive access propagation, and terminal outcomes. An Agent or Plugin decides when domain work should be delegated.

## Execution terms

| Term | Definition |
| --- | --- |
| **Runtime Identity** | Immutable attribution for Run, Agent, Session, and optional Task lineage. |
| **Event Envelope** | Immutable attribution wrapper around an Agent or core event. |
| **Session Tree** | Append-only tree of immutable Session Entries with one active path. |
| **Turn** | One input and the Agent activity needed for one terminal result. |
| **Step** | One model interaction within a Turn, including Tool Invocations and usage. |
| **Tool Invocation** | One Tool request carried through core policy and middleware to a terminal result. |
| **Terminal Outcome** | Final success, failure, rejection, cancellation, timeout, or skip result. |

## Relationships

- An Agent selects Skills, Tools, Plugins, Access Policy, and Capability Scope.
- One Agent may own multiple Sessions and execute multiple Runs.
- A Plugin Activation belongs to one Agent Run and does not become the Agent.
- A Plugin can contribute a Template but does not become the created Agent.
- One caller Agent delegates one Task to one recipient Agent through Mia Core.
- A Run executes one Agent and may originate from direct input or a delegated Task.
- Mia Core enforces identity, access, attribution, Session integrity, and Terminal Outcomes.

## Example dialogue

> **Dev:** "Is a named Agent the same thing as a Run?"
>
> **Domain expert:** "No. An Agent is durable; a Run is one execution of that Agent."
>
> **Dev:** "Where does the conversation history live?"
>
> **Domain expert:** "In an Agent-owned Session, which persists by appending entries across Runs."
>
> **Dev:** "Can that Agent ask another Agent to do work?"
>
> **Domain expert:** "Yes. It delegates one bounded Task through Mia Core, with restrictive access and one attributable Terminal Outcome."
>
> **Dev:** "Is a Plugin allowed to bypass the approval policy?"
>
> **Domain expert:** "No. Core revalidates final Tool arguments after Plugin middleware, then owns approval and execution."
>
> **Dev:** "Does trusting Plugin code make it sandboxed?"
>
> **Domain expert:** "No. Trusted Python has process authority. Mia governs its supported contribution path but makes no sandbox claim."

## Clarifications

- **Agent scope:** Agent is durable identity and configuration; Run is temporary execution.
- **Agent isolation:** Agent is a logical state boundary; filesystem or process isolation must be implemented and claimed separately.
- **Task:** Use Task for runtime work assigned to an Agent and backlog task for planning work.
- **Session:** Use Session for durable history, not identity or active execution.
- **Plugin trust:** Effective trust is assigned by Mia Core from provenance and user approval, never self-declared by a Plugin.
- **Plugin scope:** Plugin means a governed extension, not a general Core replacement or unrestricted event/service framework.
