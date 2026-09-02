# e06s01 — Canonical Agent Run Runtime

- **Story ID:** e06s01
- **Epic:** e06 — Agent Core Clean Break
- **Status:** passing
- **Risk:** P0

## User story

As a Mia contributor, I want one headless Agent runtime seam so every frontend uses the same trusted Agent, Tool, Plugin, Session, and access path.

## Contract

```text
AgentRunner → AgentRuntimeFactory → AgentHarness → Provider/Tools/Middleware/Session
```

`RuntimeIdentity` contains `run_id`, `task_id`, `agent_id`, `session_id`, and optional `parent_session_id`. `AgentEventEnvelope` and `RunErrorEvent` carry this attribution while preserving the inner Agent event and sanitizing failures. `AgentRuntime` contains the harness, identity, Session store, and resolved Agent.

`AgentRuntimeFactory` resolves one Agent, composes provider, Tools, Plugins, middleware, and Agent-owned Session storage, and restores append-only context. The Research Agent keeps its existing private specialist-then-synthesis sequence inside `AgentRunner`. Delegation uses the same runtime contracts and retains bounded access, timeout, lineage, cancellation, and truthful outcome behavior.

## Boundaries

- Runtime modules remain independent from terminal UI libraries.
- Visible Tools use Agent capability filtering and the middleware pipeline.
- Plugin activation is validated before Tool composition.
- Session writes remain append-only and identity metadata is sanitized.
- No second runtime composition root or public graph abstraction is introduced.

## Verification

```bash
uv run --offline pytest tests/test_agent_runtime.py tests/test_agent_loop.py tests/test_delegation.py tests/test_plugins.py tests/test_agent_templates.py tests/test_sessions.py
uv run --offline ruff format --check .
uv run --offline ruff check .
uv run --offline mypy src
```

See `specs/verifications/e06s03-verify.yaml` for the completed runtime evidence.
