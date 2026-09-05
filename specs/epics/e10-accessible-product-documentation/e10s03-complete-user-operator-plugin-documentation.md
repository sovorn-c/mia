# e10s03 — Complete User, Operator, and Plugin Documentation

## 1. Identity

- **Story ID:** e10s03
- **Epic:** e10 — Accessible Product Experience and Documentation
- **Type:** docs
- **Risk:** P1
- **Context:** README, local guides, CLI contract, Plugin trust, operations, recovery, and supported limits
- **BCPs:** 4
- **Status:** planned
- **Requirement delta:** ADDED

## 2. User Story

As a Mia user, operator, or Plugin author, I want complete local documentation for installation, configuration, execution, trust, data, recovery, accessibility, and supported limits so that I can operate and extend the Agent without guessing or making unsafe assumptions.

## 3. Context

The repository currently has a concise `README.md` but no `docs/` directory. Core contracts are distributed across CLI help, Agent/Plugin models, e07–e09 specifications, ADRs, and source docstrings. Documentation must turn those contracts into a navigable local guide without inventing hosted behavior, unsupported commands, sandbox guarantees, or new extension points.

## 4. Problem

A short quickstart does not explain provider credential ownership, Agent and Session data locations, Plugin provenance and trusted-code limits, diagnostics and recovery, accessibility modes, troubleshooting, upgrades, or author contribution boundaries. Missing or contradictory guidance is a production risk even when code is correct.

## 5. Goal

Publish a small cross-linked documentation set anchored by README that lets a fresh user install and run Mia, an operator diagnose/back up/recover local data, and a Plugin author understand the governed host. Every command example must use the supported CLI surface and every security-sensitive limitation must be explicit.

## 6. Non-Goals

- A web documentation platform, hosted support service, localization, screenshots, or full API reference generation.
- New CLI commands, Plugin contribution types, providers, package installation, or runtime behavior solely for documentation.
- OS/process sandbox claims, automatic repair, remote telemetry, or remote Plugin catalogs.
- Rewriting all historical specifications or duplicating every test plan in prose.

## 7. Stakeholders

- New users installing and configuring a local Agent.
- Operators inspecting diagnostics, data locations, backup/restore, and recovery findings.
- Plugin authors reviewing trust, provenance, lifecycle, contribution, and compatibility rules.
- Maintainers reviewing release gates, upgrades, and known limitations.

## 8. Dependencies

- e07 Run/Session/CLI contracts, e08 Plugin host/ADR, and e09 operations/recovery behavior.
- Current `README.md`, `pyproject.toml`, CLI `--help`, `specs/product/`, `specs/adr/`, `specs/security/`, and archived e09 evidence.
- e10s01 keyboard/help vocabulary and e10s02 plain/status behavior.
- Existing package commands and local-only verification; no new dependency.

## 9. Assumptions

- README remains the first entry point and links to focused guides under `docs/`.
- Documentation examples use placeholders such as `<provider>` and `<archive>` and never real credentials.
- The supported package is local Python 3.12+ installed with the existing uv/build flow.
- The project glossary and technical architecture are authoritative when prose needs a canonical term.

## 10. Constraints

- Use canonical terms Agent, Skill, Tool, Plugin, Task, Delegation, Run, Session, and Mia Core.
- Document credentials as machine-global and separate from Agent, Session, diagnostic, Plugin, and archive data.
- State that trusted Python Plugins are not sandboxed and that supported APIs cannot replace Core invariants.
- State recovery is read-only/non-destructive unless an explicit verified restore is requested.
- Keep all examples offline-capable and testable from the repository; do not add documentation tooling dependencies.

## 11. Domain Model

- **Agent:** durable identity users configure and select.
- **Run/Session:** execution and append-only history users operate and resume.
- **Tool:** policy-mediated capability; approval and access semantics must be documented.
- **Plugin:** declared extension with explicit trust/provenance and Core-owned lifecycle.
- **Diagnostic/Recovery record:** local operator evidence that is secret-free and non-destructive.
- **Supported surface:** commands, package paths, configuration, and lifecycle behavior the release guarantees.

## 12. Requirements

### ADDED: User installation and operation guide

Document Python/uv installation, provider credential setup without displaying secrets, first Run, Agent creation/selection, model/session controls, access policy, keyboard operation, plain output, and common command examples.

### ADDED: Operator data and recovery guide

Document Agent, Session, Plugin, diagnostic, credential, backup, restore, interrupted-write, corrupt-data, unsupported-data, diagnostics, and troubleshooting behavior. Explain safe non-destructive verification, integrity checks, restore boundaries, and truthful exit/status results.

### ADDED: Plugin author and trust guide

Document declarative versus trusted-code Plugins, provenance and explicit trust, static Skills/Templates, typed contributions, dependency/activation/cleanup lifecycle, attribution, compatibility, data ownership, and the absence of a process sandbox or Core replacement authority.

### ADDED: Release and known-limit navigation

Cross-link accessibility, upgrade expectations, supported Python/package surface, troubleshooting, security boundaries, known limitations, and relevant ADR/spec references. Avoid placeholders, obsolete identity vocabulary, and unsupported promises.

## 13. Non-Functional Requirements

- Guides are locally navigable from README and use stable headings/links.
- Examples use supported command names and safe placeholders.
- Required content is searchable and validated without network access.
- Prose is concise, canonical, and readable in plain Markdown/terminal contexts.
- Documentation never contains credential values or claims stronger than the code/spec contracts.

## 14. Contracts

### Existing contracts preserved

- README quickstart commands remain valid or are updated to the current Agent-native CLI.
- The documented runtime path remains `CLI/REPL/TUI → AgentRunner → AgentRuntimeFactory → AgentHarness`.
- Plugin docs reflect ADR 0003 and technical architecture, including Core-owned trust/lifecycle and unsandboxed trusted Python.
- Operations/recovery docs reflect e09 public commands and non-destructive behavior.

### New contracts

- `README.md` links to `docs/README.md` and the three focused guides.
- `docs/user-guide.md`, `docs/operator-guide.md`, and `docs/plugin-author-guide.md` contain required topics and supported examples.
- A documentation validation command checks required files/headings, local links, canonical terms, supported command references, and placeholder/secret exclusions.

## 15. Reason for Depth and Zoom-Out

This story modifies release-facing documents rather than a shared runtime module. Its callers are users, operators, Plugin authors, maintainers, and the release gate. Its contracts are navigability, factual alignment with CLI/spec behavior, secret-free examples, and explicit trust/recovery limits. A focused three-guide structure is enough; a documentation site generator or API extraction framework would add depth without value.

## 16. Implementation Steps

1. Create the README navigation and user guide covering install, credentials, first Run, Agent/Session/model controls, access, keyboard, and plain mode → verify: `test -s README.md && test -s docs/README.md && test -s docs/user-guide.md && rg -n 'uv sync|mia run|mia agent|NO_COLOR|--plain' README.md docs/user-guide.md`
2. Create the operator guide covering diagnostics, data locations, backup/restore, recovery, troubleshooting, integrity, and non-destructive limits → verify: `test -s docs/operator-guide.md && rg -n 'diagnostics|data locations|backup|restore|recovery|non-destructive|credential' docs/operator-guide.md`
3. Create the Plugin author guide covering trust/provenance, static resources, typed contributions, lifecycle, compatibility, data ownership, and unsandboxed trusted code → verify: `test -s docs/plugin-author-guide.md && rg -n 'trust|provenance|static|contribution|lifecycle|sandbox|Core' docs/plugin-author-guide.md`
4. Add a deterministic documentation validation test/command for local links, headings, supported commands, canonical vocabulary, no placeholders, and no secret-shaped values → verify: `uv run --offline pytest tests/test_documentation.py`
5. Run the complete documentation and frontend regression checks and confirm the guides match current CLI help and e07–e09 contracts → verify: `uv run --offline pytest tests/test_documentation.py tests/test_cli_print_mode.py tests/test_cli_repl.py tests/test_tui_app.py`

## 17. Acceptance Criteria

### Scenario SC-e10s03-P1-01: Fresh users can install and operate Mia

- Given only README and the user guide, then a user can find installation, provider setup without secret disclosure, first Run, Agent/Session/model controls, access semantics, keyboard operation, and plain output guidance.
- Every shown command exists in the supported CLI surface or is clearly marked as a shell prerequisite.

### Scenario SC-e10s03-P1-02: Operators can protect and recover local data

- Given the operator guide, then an operator can find diagnostics, ownership/sensitivity locations, backup/restore validation, recovery verification, troubleshooting, and the non-destructive boundary.
- Credential exclusion, archive integrity, path safety, and explicit restore behavior are stated without promising automatic repair.

### Scenario SC-e10s03-P1-03: Plugin authors understand governed trust and lifecycle

- Given the Plugin author guide, then an author can identify supported contributions, explicit trust/provenance, activation/disposal behavior, attribution, data ownership, compatibility, and trusted-code unsandboxed limits.
- The guide does not imply Core replacement, Tool override, remote catalog, automatic installation, or process isolation.

### Scenario SC-e10s03-P2-04: Documentation is internally verifiable

- Given the repository, then the documentation validation command finds all required files/headings and local links, rejects placeholders/secret-shaped values/obsolete terms, and passes offline.

## 18. Verification Script (Step-by-Step)

1. Open README and follow its local links to the user, operator, and Plugin author guides.
2. Compare every CLI command example with `uv run --offline mia --help` and relevant subcommand help.
3. Confirm user guidance separates provider credentials from Agent/Session/Plugin/diagnostic data.
4. Confirm operator guidance says verification is non-destructive and restore is explicit and integrity-checked.
5. Confirm Plugin guidance states explicit trust, Core-owned lifecycle, supported contributions, and no sandbox guarantee.
6. Run the offline documentation validation test and inspect any missing-link or placeholder failure.

## 19. Risks and Mitigations

- Documentation can drift from implementation; validate command names and headings against current CLI/tests.
- Trust language can overpromise isolation; quote the technical architecture/ADR boundary and explicitly state trusted Python is unsandboxed.
- Examples can leak real-looking credentials; use placeholders and reject API-key-shaped strings in tests.
- Duplicated prose can diverge; keep README as navigation/quickstart and focused guides as the detailed source.

## 20. Definition of Done and Slopcheck

- Every task has a runnable verification command and starts `failing` in its ledger.
- All four documentation scenarios pass and required topics are searchable.
- README links resolve to all guides; no unsupported command or obsolete identity term remains.
- No new package is proposed; Markdown, standard library, and existing pytest are `[OK]`.
- No hosted-docs, localization, API-generation, or visual-redesign claim is included.

### Slopcheck

No documentation framework or external package is needed. Plain Markdown plus a small offline validator is the shortest durable solution.

### Red-Flag Check

The plan avoids duplicating the entire specs cockpit and does not invent commands for gaps; examples are restricted to the existing supported surface.
