# Mia Documentation Index

Welcome to the documentation for Mia (Modular Intelligent Agent). Mia is a lightweight, modular local Agent core designed for developer pairing, terminal workflows, and extensible identity-centered agent execution.

## Documentation Guides

- **[User Guide](user-guide.md)** — Installation, provider credential setup, first Run, Agent and Session management, model selection, access policies, keyboard shortcuts, and accessible plain-mode output.
- **[Operator Guide](operator-guide.md)** — Local operational diagnostics, data locations, data sensitivity and ownership, backup and restore procedures, recovery verification, troubleshooting, and non-destructive maintenance.
- **[Plugin Author Guide](plugin-author-guide.md)** — Governed Core Extension Host model, Plugin provenance and trust boundaries, static Skills and Templates, typed contributions, lifecycle management, unsandboxed execution limits, and Core invariants.

## Architecture and Core Invariants

Mia follows an identity-centric, local-first architecture:

1. **Agent acts** — A durable identity owning instructions, configuration, model selection, and Sessions.
2. **Skill guides** — Reusable, prompt-based guidance providing task-oriented workflows.
3. **Tool enables** — Guarded capabilities executed through an onion-style middleware pipeline.
4. **Plugin extends** — Declared packages contributing Tools, Skills, and Templates governed by Mia Core.
5. **Agent delegates** — Bounded cross-agent collaboration coordinated through Mia Core.

Return to the top-level **[Project README](../README.md)** for repository overview, quickstart instructions, and development quality gates.
