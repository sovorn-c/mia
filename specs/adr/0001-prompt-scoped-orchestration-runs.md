---
status: accepted
---

# Use prompt-scoped orchestration runs and session-spanning history

Each submitted prompt creates one **Orchestration Run** with a unique `run_id`. A **Session** can span many sequential runs, allowing durable context without making run identity mode-dependent. This rejects session-scoped runs because research mode already creates prompt-scoped runs, and event attribution requires one consistent boundary.

## Consequences

Interactive single mode must stop reusing `run_id=f"run_{session_id}"` across prompts. A resumed session creates a new run and task-scoped agent instance while preserving the existing session tree.
