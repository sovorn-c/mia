# Plan Audit — e13 Inline REPL Feature Blueprint

**Date:** 2026-09-08 · **Verdict:** READY (epic blueprint only)

## Principles and integration

- Approved: both visual and interaction redesign, extending unpublished v0.6.
- One new epic, e13, maps to scope `inline-repl-experience`; no archived epic was reopened.
- Explicit boundaries and observable success criteria cover presentation, input/focus, draft preservation, approval, terminal truth, accessibility, and renewed verification.
- Dependencies e07/e10/e12 are completed. Provisional BCP 13 and WSJF (8+5+5)/5 = 3.6 are consistent across the blueprint; refine estimates during story planning.
- Existing runtime/interface decisions are reused. Compose while running means draft editing only: no automatic queue or concurrent submission.
- High regression risk is recorded in IMPACT_LATEST.md with existing test surfaces and coverage gaps for downstream planning.
- Stable historical IDs, completed artifacts, and previous reports are preserved. e13 is the active epic; story cursor is null until slicing.
- Story slicing, detailed acceptance scenarios, task commands, and test-plan decomposition are intentionally deferred to bp-plan. This is not permission to skip that phase.

## Conventions and pre-flight

Existing Python application; Rich/prompt-toolkit frontend; headless Agent Core. AGENTS.md, CLAUDE.md, and CONVENTIONS.md govern implementation. Workflow is solo-git. GitHub Actions configuration exists under `.github/workflows/`; no CI run was triggered.

Required delivery commands: `uv run --offline ruff format .`, `uv run --offline ruff check .`, `uv run --offline mypy src`, `uv run --offline pytest`, and `uv build --offline`. Also rerun applicable coverage, public-surface, and clean-install/artifact gates. These were not run during blueprinting; earlier release evidence does not cover e13.

## Blueprint validation evidence

- `bash scripts/sync-status-from-epics.sh`: passed; e13 seeded without changing historical statuses.
- `uv run --offline python scripts/check-spec-consistency.py`: passed, specification consistency clean.
- `git diff --check`: passed before final report update; repeated at final validation.
- Generic `scripts/validate-specs-yaml.sh` is absent. The repository's existing check-spec-consistency.py supplies YAML, inventory, dependency, and capsule validation; no missing generic helper is claimed to have run.
- Story-level plan-consistency checks are not applicable to an intentionally unsliced blueprint.

## Handoff

READY for `/orca-loop-run-build e13` or the user's Pi-only loop variant, not direct implementation. The loop must run bp-plan first. No feature implementation, product tests, release, or commit was performed. Publication remains separately authorized. No unresolved blueprint decision remains; exact key/layout choices belong to story planning within the approved design contract.

---

## Preserved previous audit

# Plan Audit — Mia v0.6.0 Production Agent Core

**Date:** 2026-09-04 · **Verdict:** READY

This verdict is the historical audit of the selectively replanned production blueprint. Epic e12 later superseded its full-screen Textual frontend assumption; e12 verification records the resulting CLI/REPL-only surface.

## Principles Alignment

| Check | Status | Note |
| --- | --- | --- |
| Release scope, not feature-only scope | ✅ | `SCOPE_LATEST.yaml` covers the full local product, runtime integrity, governed extensibility, operations, accessibility, documentation, and distribution. |
| Agent-centric product | ✅ | Agent remains the durable user-facing composition; Plugin is the developer extension mechanism; the supported Plugin API cannot replace Mia Core policy. Trusted Python is explicitly not sandboxed. |
| Selective replan | ✅ | Delivered e01-e06 and their story IDs/artifacts remain stable; runtime integrity remains e07; the governed host is e08; only blueprint-only successors were renumbered to e09-e11. |
| Scope bounded | ✅ | Eleven mapped outcomes and ten explicit exclusions separate the local Python product from hosted, remote, scheduler, sandbox, automatic package-management, and replaceable-Core work. |
| Success criteria | ✅ | Twenty observable criteria cover functional, security, Plugin trust/lifecycle, data, reliability, observability, accessibility, documentation, and distribution outcomes. |
| Architecture alternatives | ✅ | Three distinct Plugin Interfaces were compared: narrow registration context, typed service graph, and compiled declarative capabilities. Option A was selected with Option C's declarative trust tier. |
| DSH/Pi lineage used selectively | ✅ | Pi informs author ergonomics; DSH/Cordis informs dependency-ready activation, owned effects, rollback, and teardown; no foreign runtime or generic service/event container is adopted. |
| Constitutional boundary | ✅ | ADR 0003 keeps identity, credentials, access/approval, safeguards, Sessions, attribution, Run admission, lifecycle policy, and terminal truth unavailable for replacement through the supported Plugin API. |
| HARD GATE candidates | ✅ | e07 runtime truth, e08 governed extensions, e09 recovery/diagnostics, e10 accessible operation/docs, and e11 distribution assurance are explicit gates. |
| Domain language | ✅ | Vision, glossary, ubiquitous-language projection, scope, and technical architecture consistently define Plugin, Plugin Activation, Plugin Contribution, and Plugin Trust. |

## Production Outcome Coverage

| Approved scope outcome | Primary epic | Status |
| --- | --- | --- |
| Provider authentication and streaming entry | e01 | ✅ covered |
| Reliable interactive terminal workflow | e02 | ✅ covered |
| Bounded specialist execution | e03 | ✅ covered |
| Agent identity, access, data, and Delegation | e04 | ✅ covered |
| Guarded bundled Plugin and Template foundation | e05 | ✅ covered |
| Canonical runtime/frontend/package surface | e06 | ✅ covered |
| Truthful deterministic production Run contract | e07 | ✅ covered |
| Governed developer Core extension host | e08 | ✅ covered |
| Local observability, Plugin diagnostics, data integrity, and recovery | e09 | ✅ covered |
| Accessible operation and complete user/Plugin documentation | e10 | ✅ covered |
| Reproducible release, Plugin API, and distribution assurance | e11 | ✅ covered |

No approved scope item or production outcome is unmapped.

## Extension Contract Audit

| Check | Status | Note |
| --- | --- | --- |
| Independent extension value | ✅ | A trusted installed Plugin can add declared capabilities without editing Mia Core; Notes proves migration compatibility. |
| Minimal public Interface | ✅ | Static Skills/Templates are inspectable manifest resources; executable authors receive only `register`, `observe`, and `effect`; no mutable runtime or service repository is exposed. |
| Trust honesty | ✅ | Declarative Plugins execute no callback; installed Python code requires explicit trust; the blueprint makes no sandbox claim. |
| Deterministic lifecycle | ✅ | Complete-set planning precedes callbacks; activation is dependency-ordered, transactional, staged, and immutable per Run. While callbacks yield control, cleanup is reverse-ordered and deadline-bounded. Event-loop blocking can delay timeout/quarantine and requires documented restart recovery. |
| Core enforcement sandwich | ✅ | Plugin Tool middleware is inside permanent Core controls and transformed arguments are revalidated before approval/execution. This governs the supported host path without claiming protection from malicious same-process Python. |
| Failure truth | ✅ | Every Run using the supported consume/cancel/close contract is finalized exactly once. Normal consumption emits one matching terminal envelope. Before finalization, cancellation or awaited closure atomically finalizes `cancelled` and then reaches a cooperative cleanup decision; after finalization, late cancellation is deferred until the existing envelope is returned and awaited closure after delivery is an outcome no-op. All supported callers consume, cancel, or await closure; bare abandonment is excluded. Plugin final observers and that decision precede any terminal envelope; failures are separate diagnostics. |
| Scope discipline | ✅ | Commands, UI, providers, generic services/events, Core replacement, Tool override, hot reload, background work, remote catalogs, automatic package installation, and sandbox claims are excluded. |
| Migration | ✅ | Notes retains Plugin/Tool/Template IDs, effects, configuration, Agent-owned data location, and stored format. |

## Roadmap Completeness

| Check | Status | Note |
| --- | --- | --- |
| Complete epic index | ✅ | Eleven epics cover the release; e01-e06 preserve delivered history and e07-e11 close approved production gaps. |
| Boundaries | ✅ | Every planned epic states included and excluded outcomes. |
| Dependencies | ✅ | Dependencies are acyclic and precede dependents; e08 follows e07, e09 follows e08, e10 follows e09, and e11 is the final integration/release gate. |
| WSJF | ✅ | Every epic has numeric factors and score; ordering is dependency-ready WSJF with historical delivery order preserved. |
| BCP estimates | ✅ | 202 total BCP, including 81 planned BCP across e07-e11. Estimates must be refined during story slicing. |
| Security urgency | ✅ | e07/e08 carry maximum risk-reduction inputs for the two trust-boundary epics; e11 remains the release gate. |
| Bug accounting | ✅ | Registry summary records one fixed bug and no open, deferred, or wontfix bugs. |
| Status consistency | ✅ | Release and execution indexes both use `passing` for verified archived e04-e06; `completed` is retained for closed e01-e03. `passing` satisfies a build dependency but is not release publication. |
| Blueprint stage discipline | ✅ | No story specification or `*-tasks.yaml` file was added for e07-e11; each planned capsule hands off to `slice-tasks`. |

## Conventions Completeness

| Check | Status | Note |
| --- | --- | --- |
| `AGENTS.md` / `CLAUDE.md` | ✅ | Present, byte-identical, and aligned to the canonical runtime and quality gate. |
| `CONVENTIONS.md` | ✅ | Present with planning, testing, security, and Git rules. |
| `specs/` cockpit | ✅ | Product, impact, architecture, ADR, epic, security, bug, verification, release, execution, and state artifacts are present. |
| Commit convention | ✅ | Conventional Commits are required. |
| Git workflow | ✅ | `solo-git` on `main` is recorded in `specs/state.yaml`. |
| YAML integrity | ✅ | All 44 specification YAML files parse and release/status/capsule identities, dependencies, and BCP values align. |

## Pre-flight Answers

| Item | Value |
| --- | --- |
| Test | `uv run --offline pytest` |
| Coverage | `./scripts/check-coverage.sh` |
| Build | `uv build --offline` |
| Format | `uv run --offline ruff format --check .` |
| Lint | `uv run --offline ruff check .` |
| Typecheck | `uv run --offline mypy src` |
| Public surface | `./scripts/check-public-surface.sh` |
| Package surface | `uv run --offline python scripts/check-wheel-surface.py <wheel>` |
| Specification validation | Offline PyYAML parse and release/status/capsule alignment fallback until e11 supplies a repository helper |
| CI platform | GitHub Actions target, inferred from the GitHub `origin`; workflow creation is an e11 outcome |
| Workflow mode | `solo-git` |
| Language/framework | Python 3.12+, Pydantic 2, AnyIO, Typer/Rich, prompt-toolkit, Textual, Hatchling/uv |
| Codebase | Existing product with delivered e01-e06 and planned production epics e07-e11 |

The required quality gate was rerun after the selective replan: Ruff formatting left 83 files unchanged, Ruff lint passed, strict mypy passed for 59 source files, all 166 tests passed, and the v0.6.0 source distribution and wheel built successfully. The established coverage baseline remains 91% total and 97% across business-boundary modules.

## Mandatory Story-Slicing Conditions

- [ ] **e07:** centralize exactly-once Run finalization, normal/cancellation/awaited-close semantics, standard-library `aclosing` use in every caller, permanent safeguards, effective provider settings, same-Session admission, and the final Core Tool validation boundary before e08 host implementation.
- [ ] **e08:** split trusted installed-package discovery/explicit trust, transactional lifecycle, contribution validation, safe Tool middleware/context/observer behavior, Notes migration, and Plugin-free compatibility into independently testable vertical outcomes.
- [ ] **e08:** use one test-only installed Plugin as evidence that extension does not require a Core edit; do not add a package manager, service container, or second execution root.
- [ ] **e08:** keep Agent Templates and static Skills inspectable from strict manifests without Agent/Run activation; activate only runtime Tools, context, observers, middleware, and owned effects.
- [ ] **e08:** define strict API-version, exact dependency, collision, rollback, cooperative callback, conditional cleanup-timeout/abandonment, process quarantine/restart, pre-terminal decision, diagnostic, and trust/provenance acceptance criteria before implementation.
- [ ] **e09:** include Plugin activation/disposal diagnostics and Plugin-owned data backup/recovery without secret leakage or deletion.
- [ ] **e10:** cover user trust decisions and Plugin author lifecycle/permissions/compatibility guidance in accessible terminal and documentation outcomes.
- [ ] **e11:** add the absent CI workflow, repository YAML-consistency helper, security-sensitive checks, clean-install and installed-Plugin smoke tests, Plugin API compatibility, provenance, and publication/withdrawal runbook.
- [ ] **`/bp-plan`:** slice e07-e11 into vertical stories and add runnable task plans. Story-level format, acceptance-criteria, test-command, and task-independence checks remain intentionally deferred.

## Release Gates

1. e07 cannot pass while any frontend can disagree about terminal Run truth, Agent configuration can remove a permanent safeguard, or Plugin ordering can bypass final Core validation.
2. e08 cannot pass unless an explicitly trusted installed Plugin extends an Agent without a Core edit and cannot replace Core identity, credentials, policy, Sessions, attribution, lifecycle ownership, or terminal truth through the supported host API; the product must state same-process Python authority honestly.
3. e09 cannot pass without verified secret-free Run/Tool/Plugin diagnostics and non-destructive backup/restore/recovery behavior.
4. e10, after e09, cannot pass while an essential workflow or Plugin trust decision requires color, animation, pointer input, or undocumented knowledge.
5. e11 cannot pass with a failing required command, unresolved critical/high security finding, Plugin API incompatibility, unverified artifact, unauthorized publication path, or missing withdrawal/supersession procedure.
6. The release cannot be approved while any in-scope outcome lacks passing verification evidence.

## Verdict

**READY** — the selective replan is coherent, bounded, dependency-ordered, security-conscious, and detailed enough for story slicing. An independent architecture review initially returned NOT READY; its blockers are now resolved by separating inspectable catalog contributions from Run activation, defining exactly-once Core finalization for consumption, cancellation, and awaited closure while excluding bare abandonment, distinguishing pre- from post-finalization cancellation/closure and fixing the linearization order as finalize → observe → cleanup decision → delivery, requiring cooperative cleanup decisions without claiming progress against event-loop-blocking code, narrowing constitutional claims to the supported host API, making e10 depend on e09, and aligning delivered-epic status vocabulary. A final independent pass found no remaining blocker or concern and returned READY. The public Plugin surface remains materially smaller than either Pi's full-authority extension model or DSH's replaceable-service model while still enabling installed developers to extend Agents without changing Core.

**Next skill:** `/bp-plan`
