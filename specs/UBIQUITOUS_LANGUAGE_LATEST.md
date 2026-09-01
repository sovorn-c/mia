# Ubiquitous Language

> Human-readable projection of `specs/product/GLOSSARY_LATEST.yaml`, the canonical source of truth.

> **Core invariant:** Mode composes; Profile configures; Workflow coordinates; Agent executes; Plugin extends.

## Composition

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Mode** | User-selected orchestration composition binding one coordinator Profile to one validated Workflow and its enabled policies. | Persona, agent preset, Profile |
| **Profile** | Reusable declarative configuration for one agent role, including prompt, model defaults, tools, permissions, middleware, and limits. | Mode, Workflow, Agent Instance, persona |
| **Workflow** | Validated ordered definition of Workflow Stages executed by an Orchestration Run. | Profile, prompt template, Run, task DAG |
| **Workflow Stage** | Named Workflow position declaring one Profile and either Specialist or Coordinator responsibility. | Workflow Task, Agent Instance, Turn, Step |
| **Plugin** | Installable extension contributing capabilities without owning orchestration. | Mode Runtime, Agent Instance, workflow owner |
| **Mode Runtime** | Headless domain service resolving a Mode, executing its Workflow, and emitting attributable orchestration events. | HerdManager, terminal UI, Agent Instance, Orchestration Run |

## Orchestration execution

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Orchestration Run** | One execution of a resolved Mode and Workflow for one submitted prompt. | CLI run, Session, Turn, agent run |
| **Workflow Task** | Run-specific execution of one Workflow Stage by one Agent Instance. | Workflow Stage, backlog task, Turn, Step, subagent |
| **Agent Instance** | One logical AgentHarness executor with one Runtime Identity, Profile, context, and Session. | Agent, Profile, Mode, Workflow, ManagedAgent |
| **Runtime Identity** | Immutable attribution tuple joining Mode, Run, Task, Agent, Profile, Session, and optional parent Session identifiers. | Agent state, Session metadata, Event Envelope |
| **Orchestration Event Envelope** | Attribution wrapper retaining one unchanged agent event or orchestration error with Runtime Identity fields. | Agent event, herd event, message envelope |

## Execution roles

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Coordinator** | Required final Workflow role producing the Orchestration Run's user-facing result. | Lead agent, root agent, Mode Runtime |
| **Specialist** | Optional non-final Workflow role producing task-local input for the Coordinator. | Coordinator, teammate, worker pool |
| **One-shot Specialist** | Task-local Specialist Agent Instance returning one result without accepting later prompts. | Continuable Child, persistent teammate, durable worker |
| **Continuable Child** | Deferred child agent identity accepting later prompts and supporting reconstruction after process restart. | One-shot Specialist, Workflow Task |

## Durable conversation

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Session** | Durable conversation history shared by sequential Agent Instances in one conversation lineage. | Orchestration Run, Turn, transcript file, Workflow Task |
| **Session Tree** | Append-only directed tree of Session Entries with one active root-to-leaf path. | Session, conversation list, run tree |
| **Session Branch** | One root-to-leaf Session Tree path used to reconstruct active context. | Git branch, Session, child Session |
| **Session Entry** | Immutable node containing a message, compaction, Session metadata, leaf pointer, or namespaced extension. | Event, chat message, checkpoint |
| **Compaction Checkpoint** | Session Entry containing a summary replacing earlier entries during active-path replay. | Session snapshot, deleted history, summary message |

## Agent execution

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Turn** | One user prompt and the agent activity required to reach one terminal Turn outcome. | Orchestration Run, Workflow Task, message, request |
| **Step** | One model interaction within a Turn, including requested Tool Invocations and token usage. | Workflow Stage, Workflow Task, Turn, tool call |
| **Tool Invocation** | One model-requested tool execution carried through middleware to one success or error result. | Workflow Task, Step, bash process, tool definition |

## State semantics

| Term | Definition | Aliases to avoid |
|------|------------|------------------|
| **Lifecycle State** | Derived semantic position of a runtime entity based on emitted events and terminal outcome. | Event, status message, legacy AgentState |
| **Terminal Outcome** | Final success, failure, or cancellation result preventing further lifecycle transitions. | Done state, stop reason, error event |
| **Skipped** | Workflow Task outcome showing execution never started after upstream failure or cancellation. | Cancelled, failed, pending |

## Relationships

- A **Mode** binds exactly one **Workflow** and one coordinator **Profile**.
- A **Workflow** contains one or more ordered **Workflow Stages**.
- The current **Workflow** has exactly one final **Coordinator** stage and at most one **Specialist** stage.
- An **Orchestration Run** resolves one **Mode** and executes reached stages as **Workflow Tasks**.
- Each **Workflow Task** uses exactly one **Agent Instance**, **Profile**, and **Session**.
- A **Session** can be reopened by sequential **Agent Instances** across multiple **Orchestration Runs**.
- A research **Orchestration Run** creates one **One-shot Specialist** before its **Coordinator**.
- A child **Session** references its parent **Session** without merging either **Session Tree**.
- A **Session Tree** contains immutable **Session Entries** and selects one active **Session Branch**.
- A **Turn** belongs to one **Agent Instance** and contains ordered **Steps**.
- A **Step** produces zero or more **Tool Invocations**.
- Each emitted agent event remains unchanged inside one **Orchestration Event Envelope**.

## Example dialogue

> **Dev:** "Does research **Mode** create a second **Profile**?"
>
> **Domain expert:** "No. The **Mode** selects a **Workflow** whose stages reference existing **Profiles**."
>
> **Dev:** "Is the specialist stage itself an agent?"
>
> **Domain expert:** "No. The **Workflow Stage** is a definition. Its **Workflow Task** runs through one **One-shot Specialist** **Agent Instance**."
>
> **Dev:** "Can that specialist continue after the **Orchestration Run** ends?"
>
> **Domain expert:** "No. Its **Session** remains durable, but continuation belongs to the deferred **Continuable Child** concept."
>
> **Dev:** "How do we know whether the task succeeded?"
>
> **Domain expert:** "Derive its **Lifecycle State** from attributable events until it reaches one **Terminal Outcome**."

## Flagged ambiguities

- **Agent** previously meant product, configuration, executor, or legacy ManagedAgent. Use **Mia**, **Profile**, or **Agent Instance**.
- **Run** can mean the `mia run` command. Use **Orchestration Run** for domain execution.
- **Task** can mean planning work. Use **Workflow Task** only for run-specific stage execution.
- **Stage** can mean definition or execution. Use **Workflow Stage** for the definition and **Workflow Task** for execution.
- **Coordinator** can mean role, stage, or executor. Qualify it as coordinator role, stage, or Agent Instance when needed.
- **Specialist** does not imply continuity. Use **One-shot Specialist** now and **Continuable Child** only for deferred behavior.
- **Session** does not mean Run or Turn. Use **Session Tree** for storage shape and **Session Branch** for replay selection.
- **State** must not import legacy Herd semantics. Use **Lifecycle State** derived from native orchestration events.
