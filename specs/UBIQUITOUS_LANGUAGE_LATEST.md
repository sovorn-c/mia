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
| **Mia Core** | Trusted runtime boundary for Agent execution, routing, policy, persistence, and events. |
| **Agent** | Durable identity combining configuration, state, capabilities, access policy, Plugins, and collaboration behavior. |
| **Skill** | Reusable instruction, knowledge, or procedure that guides an Agent. |
| **Tool** | Callable capability exposed through core policy and middleware. |
| **Plugin** | Installable executable extension contributing declared Tools, Skills, or Templates. |
| **Agent Template** | Shareable starting definition used to create an independent Agent without private state. |
| **Task** | Bounded work assigned to an Agent with one attributable outcome. |
| **Delegation** | Core-mediated assignment of a Task between eligible Agents. |
| **Run** | One prompt- or Task-scoped execution of one Agent. |
| **Session** | Append-only conversation history owned by an Agent and reusable across Runs. |
| **Access Policy** | `read-only`, `approval-required`, or `full-access`; controls mutation and confirmation. |
| **Capability Scope** | Declared Tools, Plugins, resources, and delegation targets available to an Agent. |

Having no Tools is capability configuration, not a fourth access level. Full access requires explicit consent and never disables permanent credential or integrity safeguards.

## Extension and collaboration

A Plugin may contribute Skills, Tools, integrations, hooks, and Agent Templates. It cannot bypass core access, credential secrecy, routing, Session integrity, event attribution, cancellation, or truthful outcomes.

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
- A Plugin can contribute a Template but does not become the created Agent.
- One caller Agent delegates one Task to one recipient Agent through Mia Core.
- A Run executes one Agent and may originate from direct input or a delegated Task.
- Mia Core enforces identity, access, attribution, Session integrity, and Terminal Outcomes.

## Clarifications

- **Agent scope:** Agent is durable identity and configuration; Run is temporary execution.
- **Agent isolation:** Agent is a logical state boundary; filesystem or process isolation must be implemented and claimed separately.
- **Task:** Use Task for runtime work assigned to an Agent and backlog task for planning work.
- **Session:** Use Session for durable history, not identity or active execution.
