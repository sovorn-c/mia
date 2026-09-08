# e13 — Inline REPL design boundary

Status: approved scope and interaction direction for unpublished v0.6; detailed key/layout choices belong to story planning.

## Chosen direction

Keep the terminal's normal scrollback. Use a restrained hierarchy: compact context/status, readable conversation output, concise Tool summaries with discoverable inspection, and a draft editor. Status must reflect actual runtime facts, not guessed context capacity or intermediate events treated as final outcomes. Adapt to narrow widths; avoid fixed-width decorative framing that obscures content.

VT Code's runtime discipline, Crush's explicit state/focus handling, and Froggit's restrained keyboard vocabulary are design references from the discussion, not dependencies or promises to copy their interfaces. No new research or compatibility claim about those projects is implied.

## Interaction contract

- Idle: draft editing and explicit submission are available.
- Running: streaming continues while the user edits the next draft. Submission is disabled, never queued. Run completion leaves the draft available for explicit submission.
- Approval: approval owns a clearly labelled input context distinct from the draft. Ordinary draft keystrokes cannot authorize a Tool. Restore the draft when approval concludes.
- Cancelling: retain the draft and show cancellation progress until Core determines the outcome. Do not announce success or cancellation from an intermediate event alone.
- Selectors/inspection: explicit focus, discoverable exit, and draft preservation. Agent/model/Session changes must not mutate a running request. Detailed key assignments and whether a busy-state action is disabled or deferred for explicit later invocation are planning decisions; no automatic command queue.
- EOF/exit and explicit draft clearing must remain distinguishable from Run cancellation. Do not silently discard text during focus changes.

## Architecture boundary

Reuse Rich and prompt-toolkit and the canonical AgentRunner → AgentRuntimeFactory → AgentHarness path. Keep UI state and input coordination in mia_cli; no terminal framework enters mia_agent. Draft editing is local UI activity, not a second Run, persisted Session entry, scheduler, or public runtime API.

Current LivePromptSession keybindings can reset or replace the buffer to invoke commands. The new busy/approval/focus contract must prevent that behavior from losing a draft. Streaming rendering is also used by print mode, so interactive changes must preserve non-interactive/plain behavior.

Preserve consume/cancel/awaited-close semantics and exactly-once finalization from ADR 0002. Preserve mandatory Tool middleware and approval policy. Never route approval through an unvalidated draft or expose secrets through additional status/inspection output.

## Options resolved

1. Block editing until completion: smallest implementation, but does not meet the approved compose-while-running experience.
2. Compose while running, explicit later submission: selected; bounded frontend coordination with no execution queue.
3. Queue or execute another prompt: excluded; adds execution semantics outside the approved feature.

No new Core interface or architecture replacement is needed. Exact rendering primitives, key map, and implementation decomposition remain with bp-plan.

## Verification boundary

Use deterministic MockProvider-driven REPL checks, prompt input/PTY checks, and print-mode regressions during delivery. Cover draft preservation under completion, cancellation, approval, focus changes, resize and paste; blocked busy submission; truthful final output; and accessible fallbacks. These are epic-level expectations, not a detailed test or task plan.

Rerun the repository's full offline gate and clean-install/artifact verification after implementation. Earlier v0.6 candidate evidence remains historical and does not verify e13. Publication still requires explicit authorization.
