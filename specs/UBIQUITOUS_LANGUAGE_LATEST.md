# Ubiquitous Language

> Human-readable projection of `specs/product/GLOSSARY_LATEST.yaml`, the canonical source of truth for Mia's draft target terminology.

> **Core invariant:** Agent acts; Skill guides; Tool enables; Plugin extends; Agent delegates through Mia Core.

## One identity term: Agent

Mia uses **Agent** everywhere for its primary product object.

```text
Mia Core
  └── Agent
        ├── Identity and instructions
        ├── Model and configuration
        ├── Memory and Sessions
        ├── Skills and Tools
        ├── Plugins
        ├── Access Policy
        └── Delegation to other Agents
```

**Assistant**, **Profile**, and **Bot** are not separate product or domain entities:

- Use **Agent**, not Assistant.
- Use **Agent**, not Profile, in the target model. Profile remains current implementation terminology until migration.
- Use **Agent**, not Bot. Bot may remain ordinary channel-specific description.
- Use **Run** for one execution of an Agent; do not create an Agent Instance identity.

Examples: **Mia**, **Research Agent**, **Coding Agent**, **Finance Agent**, and **Travel Agent**.

## Canonical terms

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Mia Core** | Trusted runtime owning Agent execution and routing, provider contracts, Sessions, Tools, permissions, Plugins, events, cancellation, and truthful outcomes. | Agent, workflow engine, plugin-owned runtime |
| **Agent** | Durable, addressable intelligent entity combining identity, configuration, private state, capabilities, access policy, Plugins, and collaboration behavior. | Assistant, Profile, Bot, Agent Instance, Mode |
| **Skill** | Reusable instructions, knowledge, or procedure teaching an Agent how to perform a capability. | Tool, Plugin, mandatory Workflow, scheduled Routine |
| **Tool** | Callable capability exposed through Mia Core's validated invocation boundary. | Skill, Plugin package, unmediated function call |
| **Plugin** | Installable executable package contributing Skills, Tools, integrations, hooks, private workflows, Agent templates, or other declared capabilities. | Agent identity, core runtime owner, permission bypass |
| **Agent Template** | Shareable starting definition that becomes an independently configured Agent without carrying private user state. | Running Agent, shared credentials, Plugin runtime |
| **Task** | Bounded work assigned to an Agent with one attributable Terminal Outcome. | Backlog task, Skill, Workflow Stage |
| **Delegation** | Core-mediated assignment of a Task from one Agent to another. | Unattributed prompt injection, shared mutable Session, silent escalation |
| **Run** | One prompt- or Task-scoped execution of one Agent. | Agent identity, CLI command, Session, long-lived process |
| **Session** | Durable conversation history owned under a defined Agent boundary and reusable across Runs. | Agent, Run, active process |
| **Access Policy** | Read-only, approval-required, or full-access; governs mutation and confirmation for enabled capabilities. | Agent, sandbox, Tool allowlist, no-tools level |
| **Capability Scope** | Declared Tools, Plugins, resources, and delegation targets an Agent may use. | Access Policy, identity, system prompt |

Having no Tools is Capability Scope configuration, not another Access Policy. Full-access removes per-action confirmation only after explicit opt-in; permanent credential and integrity safeguards remain mandatory.

## Extension model

```text
Research Agent
  ├── Skill: evaluate sources
  ├── Tool: web search
  └── Plugin: citation verifier
```

A simple reusable procedure is a **Skill**. A callable action is a **Tool**. Installable executable behavior belongs to a **Plugin**.

A Plugin may contribute:

- Skills and Tools.
- External integrations.
- Hooks at declared extension points.
- Private multi-step workflows.
- Agent Templates.

Plugins may implement broad domain behavior but cannot bypass core permissions, credential secrecy, routing, Session integrity, event attribution, cancellation, or truthful outcomes.

## Agent collaboration

Agent-to-Agent **Delegation** is Mia's primary coordination primitive:

```text
Mia
  → delegates a Task to Research Agent
  → receives an attributable result
  → delegates implementation to Coding Agent
  → returns the final result
```

Mia Core owns discovery, routing, attribution, permission propagation, and Terminal Outcomes. An Agent or its Plugin decides when and how domain work should be delegated.

## Execution terms

| Term | Definition |
|------|------------|
| **Runtime Identity** | Immutable attribution identifying the Run, Agent, Session, and optional caller Agent and delegated Task. |
| **Event Envelope** | Attribution wrapper retaining one unchanged agent, Tool, Delegation, or core event. |
| **Session Tree** | Append-only directed tree of immutable Session Entries with one active path. |
| **Turn** | One input and the Agent activity needed to reach one terminal Turn outcome. |
| **Step** | One model interaction within a Turn, including requested Tool Invocations and usage. |
| **Tool Invocation** | One model-requested Tool execution carried through core policy and middleware to a terminal result. |
| **Terminal Outcome** | Final success, failure, rejection, cancellation, timeout, or skip result. |

## Non-canonical terms

| Term | Resolution |
|------|------------|
| **Assistant** | Use Agent. It may remain ordinary descriptive prose only. |
| **Profile** | Use Agent in the target model. Profile describes current implementation until migration. |
| **Bot** | Use Agent. Bot may describe a messaging-channel presentation only. |
| **Agent Instance** | Use Agent for durable identity and Run for one execution. |
| **Routine** | Use Skill for a reusable procedure; scheduling is separate. |
| **Workflow** | Private implementation logic inside an Agent, Skill, or Plugin—not a top-level product object. |
| **Mode** | Current ModeRuntime compatibility term; absent from the target product model. |

Current `ModeRuntime`, `single`, `research`, `AgentProfile`, and fixed Workflow terminology remains valid documentation of implemented e03 behavior. It must not drive new target product design, and it should change only through a separately approved migration.

## Relationships

- An **Agent** selects Skills, Tools, Plugins, Access Policy, and Capability Scope.
- One Agent may own multiple Sessions and execute multiple Runs.
- A Plugin may contribute an Agent Template but does not become the installed Agent.
- A Skill may describe a procedure; a Plugin may execute one; neither makes Workflow a public object.
- One caller Agent delegates one Task to one recipient Agent through Mia Core.
- Mia Core enforces identity, routing, permissions, attribution, Session integrity, and Terminal Outcomes.
- A Plugin cannot silently expand its Agent's Capability Scope.
- A Run executes one Agent and may originate from direct input or a delegated Task.
- A Turn belongs to one Run and may produce Tool Invocations or Delegations.

## Example dialogue

> **User:** “Ask my Research Agent to investigate this, then give the result to my Coding Agent.”
>
> **Mia:** Mia Core routes one attributable Task to each Agent and returns their results.
>
> **Developer:** “Is that a Mode or public Workflow?”
>
> **Domain expert:** No. Delegation is the core protocol. Any multi-step procedure remains private to the Agent, Skill, or Plugin.
>
> **Developer:** “Is the configured object a Profile or Agent?”
>
> **Domain expert:** Agent. Profile is only current implementation terminology pending migration.

## Flagged ambiguities

- **Agent scope:** Agent combines durable identity and configuration; Run is temporary execution.
- **Plugin freedom:** Broad behavior is allowed, but core integrity contracts remain mandatory.
- **Agent isolation:** Logical identity and state isolation does not itself imply process or filesystem sandboxing.
- **Task:** Use Task for runtime work assigned to an Agent and backlog task for planning.
- **Run:** Use Run for Agent execution and `mia run` only for the CLI command.
- **Session:** Use Session for durable history, not Agent identity or active execution.
