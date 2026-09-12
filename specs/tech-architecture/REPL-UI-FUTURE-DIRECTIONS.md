# REPL UI Future Directions

**Status:** Durable deferred roadmap
**Scope:** Pi-inspired improvements beyond the immediate e14 Agent Workspace Interaction feature

## Reason for existence

Keep useful Pi interaction ideas available without reopening completed e13 work, repeatedly rediscovering design decisions, or allowing deferred UI and Core capabilities to leak into the current release scope.

## North star

Mia is an Agent workspace, not a chat transcript: users can see what they submitted, what the Agent is doing, which Tool is active, what requires approval, what completed, and what remains queued. The UI is a truthful projection of Core-owned Run state.

## Baseline that must not change

- Agent is the single durable identity.
- `AgentRunner → AgentRuntimeFactory → AgentHarness` is the only prompt execution path.
- `AgentHarness` remains headless and independent from terminal frameworks.
- Sessions remain append-only.
- Every visible Tool remains inside access, security, audit, and execution-control middleware.
- Interactive input has one terminal owner; competing redraw systems are forbidden.
- Plain and non-interactive output remain supported.
- Pi is read-only prior art, not a dependency, source-compatibility target, or UI promise.

## Immediate e14 direction

The next release may adopt these capabilities on the existing prompt-toolkit + Rich foundation:

- Visible user and Agent transcript blocks.
- Truthful Run lifecycle status.
- Compact expandable Tool rows.
- Semantic message and status roles.
- Asynchronous inline approval with distinct focus.
- Searchable commands and selectors.
- Adaptive footer with truthful model, Session, Run, usage, and context information.
- Safe bounded terminal output.
- Draft and focus restoration.
- Explicit follow-up queue through `Ctrl+Q` and `/queue`.

The queue is follow-up-only. It never steers an in-flight Run, starts concurrent Runs, or becomes a background scheduler. Cancellation restores queued text to the draft. `Ctrl+Q` is best-effort because terminal flow control can consume it; `/queue` is the portable fallback.

## Deferred: stronger UI layer

These capabilities require a persistent coordinated renderer before they will be reliable and pleasant:

| Capability | Promotion trigger |
| --- | --- |
| Live expandable Tool cards | Static Tool rows cannot expose important output without flooding the transcript. |
| Partial Tool output | A Tool emits meaningful progress that users need before completion. |
| Selector and approval surfaces without interrupting rendering | Focus transitions still redraw, lose drafts, or corrupt scrollback. |
| Queue display, edit, and dequeue | More than one follow-up is common enough that draft-only visibility is insufficient. |
| Dynamic transcript rebuilding | Streaming or resize causes flicker, duplicate blocks, or stale layout. |
| Flicker-free differential rendering | Normal scrollback cannot preserve readable updates on supported terminals. |
| Overlay and focus stacks | Multiple intentional surfaces need deterministic restoration. |
| Full Session/tree navigation | Session inspection becomes a primary workflow rather than an occasional command. |

A stronger UI layer must still preserve inline operation unless a separately approved product decision changes the frontend boundary. Do not introduce Textual or another terminal framework merely to obtain these features.

## Deferred: Mia Core support

These are Core contracts, not presentation tweaks:

- Tool progress events.
- Compaction and retry lifecycle events.
- Richer message start/update/end events.
- Model-selection events.
- Attachment and image events.
- True in-flight steering.
- Custom Tool renderer contracts.

Promote one only when an existing typed event cannot express a required user-visible state, the contract has clear ownership and cancellation semantics, and deterministic MockProvider tests can prove it. UI code must not infer a new Core fact from timing or an ad-hoc status string.

## Other Pi ideas worth evaluating later

- External-editor and richer multiline workflows.
- Copy, export, share, and message inspection actions.
- Session naming, fork/clone distinction, and branch previews.
- Tool-specific renderers for structured data, diffs, and images.
- Capability-aware terminal rendering for hyperlinks, images, keyboard protocols, and cursor behavior.
- User-loadable themes and theme previews.
- Plugin-provided notification-only status components, subject to the governed Plugin boundary.
- Adaptive help and command palettes with action availability and key hints.

Each item needs a separate scope decision. Pi’s exact shortcuts, visual vocabulary, extension API, terminal protocols, and feature inventory are not automatically inherited by Mia.

## Never rules

- Never run Rich Live beside an active prompt-toolkit editor.
- Never let UI status override Core terminal outcome truth.
- Never authorize a Tool through the draft buffer or an unvalidated string.
- Never expose credentials or unbounded Tool content in transcript, footer, diagnostics, or themes.
- Never add a scheduler, concurrent Run manager, or in-flight steering under the name of a UI queue.
- Never reopen archived e13 artifacts to hide a new requirement.

## Promotion gate

Before moving a deferred item into an active epic:

1. State the user-visible problem and why the current UI cannot solve it.
2. Decide whether the item belongs in the UI Adapter, event contract, or both.
3. Define cancellation, focus, persistence, accessibility, and plain-output behavior.
4. Add a public-interface test and an observable success criterion.
5. Run impact analysis and update the relevant scope, roadmap, and architecture artifacts.

## Verification

```bash
test -f specs/tech-architecture/REPL-UI-FUTURE-DIRECTIONS.md \
  && grep -q 'Deferred: stronger UI layer' specs/tech-architecture/REPL-UI-FUTURE-DIRECTIONS.md \
  && grep -q 'Deferred: Mia Core support' specs/tech-architecture/REPL-UI-FUTURE-DIRECTIONS.md
```
