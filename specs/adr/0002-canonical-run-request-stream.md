---
status: accepted
---

# Use one validated request stream as the Agent Run Interface

`AgentRunner.run(RunRequest)` is the target public Interface for prompt execution. It returns one ordered asynchronous stream of attributed events and finalizes every Run used through the supported consumption contract exactly once in Core. A normally consumed stream emits exactly one terminal `TurnCompleteEvent` or sanitized `RunErrorEvent` reflecting that finalized outcome. Before finalization, external caller cancellation atomically finalizes the Run as cancelled, reaches a cleanup completion-or-timeout decision for cancellation-cooperative callbacks, releases Session admission, and re-raises `CancelledError` without promising an envelope. Awaited `aclose()` before finalization does the same with a stream-closed reason. Cancellation after finalization is deferred until the existing terminal envelope is returned; awaited closure after terminal delivery preserves the outcome and is lifecycle-idempotent. Every supported caller consumes to terminal, cancels the consuming task, or wraps the returned `AsyncGenerator` in standard-library `contextlib.aclosing`. Creating but never iterating starts no Run; bare abandonment after iteration is unsupported because Python cannot guarantee asynchronous-generator finalization timing. Supported delivery interruption changes delivery mechanics, not terminal truth. CLI, REPL, TUI, Delegation, and tests do not infer terminal truth from intermediate events or ordinary stream exhaustion.

`RunRequest` is immutable and contains Run input and explicit user overrides. Provider instances, credentials, runtime handles, Tool pipelines, and persistence paths remain private constructor or factory dependencies. Ambient async task cancellation is the supported cancellation mechanism. Concurrent Runs for one Agent-owned Session fail fast; distinct Sessions may proceed independently.

This preserves Mia's hybrid design lineage: Pi/Tau-like lightweight Agent-loop execution plus DeepSeek Harness (DSH)-inspired onion/waterfall middleware around Tool execution. DSH's `pre-execute → execute → post-execute` behavior remains prior art for Core execution controls; DSH is not imported as a dependency or used as a second runtime.

## Consequences

- `AgentRunner → AgentRuntimeFactory → AgentHarness` remains the only execution path.
- Terminal semantics, same-Session admission, sanitization, research sequencing, cancellation recording, and cleanup become local to AgentRunner.
- `prepare_runtime` and `last_runtime` are not part of the target Interface; Session operations expose only the explicit data and actions current frontends require.
- A first-class lifecycle handle is deferred until a real caller needs cancellation without owning the consuming task or needs post-Run lifecycle state.
- A push-callback Interface is rejected because presentation delivery must not become part of headless execution correctness.
- No scheduler, event bus, remote execution protocol, or compatibility overload is introduced.
