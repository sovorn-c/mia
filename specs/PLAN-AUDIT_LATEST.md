# Plan Audit — e14 Agent Workspace Interaction (implementation plan)
**Date:** 2026-09-12 · **Verdict:** READY
**Plan revision:** 7ba51e19f3172273
**Mode:** implementation (story + task + test plan)

This is the story+task implementation-plan audit required before `/bp-build`. Earlier scope-only / epic-blueprint READY verdicts below do **not** satisfy this gate. Git HEAD at audit time: `3f6256d` on `feat/align-codex-model-selection`. `specs/state.yaml` records `plan_approval.status: approved` for this exact revision.

## Principles Alignment

| Check | Status | Note |
| --- | --- | --- |
| Vertical slices | ✅ | Five user-visible slices: transcript+lifecycle (s01), compact Tool rows (s02), async approval (s03), selectors+footer (s04), follow-up queue+fallbacks (s05). Not layer cakes. |
| Scope bounded | ✅ | `SCOPE_E14_LATEST.yaml` in/out plus epic `boundaries`. v0.6.0 `SCOPE_LATEST.yaml` oos-11 keeps e14 off the current production release. Steering, concurrent Runs, new Core event families, live cards, and frontend rewrites stay out. |
| Happy-path and failure AC | ✅ | Every unfinished story has both. s01 success/error/cancel + intermediate-not-terminal; s02 expand + sanitization/error rows; s03 approve + deny/fail-closed; s04 search + busy/no-network; s05 enqueue/success-run + restore/occupied/no-concurrency. |
| Scenario IDs | ✅ | 25 IDs match `SC-e14sYY-P0/P1/P2/P3-NN`, appear in each story §17, and match `e14-TEST_PLAN_LATEST.md` 1:1 (no extras on either side). |
| Runnable task ledgers | ✅ | Five `*-tasks.yaml` files, 20 tasks, every `verify:` non-empty, every `status: failing`. Verify commands are real `uv run --offline pytest` / spec / ruff gates. |
| Dependency order | ✅ | s01 → s02 → s03; s04 depends on s01+s03; s05 depends on s01+s03+s04. Acyclic; matches `epic.yaml`. |
| Architecture constraints | ✅ | AgentRunner path only; projection in `mia_cli` not `mia_agent`; no new Core event families; no concurrent Runs; no in-flight steering; prompt-toolkit owns interactive input; Sessions append-only; Tool middleware mandatory; ADR 0002 consume/cancel/close preserved. |
| Requirement deltas | ✅ | ADDED/MODIFIED with before/after on every behavior change (idle/running, Tool lines, blocking `input()`, selectors/footer, compose-without-queue). |
| BCP sum | ✅ | 5+5+4+3+4 = 21; matches epic, release-plan, and execution-status. WSJF (9+6+8)/8 = 2.875. |
| Hard gates | ✅ | Transcript exactly-once (s01 P0-01); Core terminal truth (s01 P0-02/P0-03); approval fail-closed (s03 P0-03/P1-01); queue success-only auto-run (s05 P0-02); secret-free Tool display (s02 P0-03). |
| Expand gesture named | ⚠️ | s02 requires expand/collapse of retained results but does not name the key/command. Behavioral contract + renderer tests are enough for TDD; do not promote live cards. |
| Fail-to-admit SC | ⚠️ | s01 requirements/risks mention a Run that never admits; no dedicated SC. Covered by `e14-transcript-source` (render only from admitted `TurnStartEvent.user_prompt`). |
| Security echo suffix | ⚠️ | s02/s03/s05 task 3 append `echo "no new security findings..."`. Pytest still fails closed; echo is a reminder, not a scan. |

## Conventions Completeness

| Check | Status | Note |
| --- | --- | --- |
| `CLAUDE.md` / `AGENTS.md` | ✅ | Present; canonical AgentRunner path and offline quality gate. |
| `CONVENTIONS.md` | ✅ | Present; Conventional Commits, solo-git, MockProvider, required checks. |
| `specs/` cockpit | ✅ | Product, epics, tech-architecture, ADR, impact, release, execution, state. |
| Commit / git workflow | ✅ | Conventional Commits; `specs/state.yaml` `workflow_mode: solo-git`. |
| No new runtime dependency | ✅ | prompt-toolkit [OK], Rich [OK]; none proposed. |
| Spec consistency helper | ✅ | `scripts/check-spec-consistency.py` is the inventory helper (`specification consistency: clean`). `scripts/lib/plan-consistency-check.sh` **is** present despite the e14 epic note; it reports `CRITICAL=0 HIGH=0 MED=0` / `PASS` for this capsule. Absence of a generic helper is not a blocker. |

## Outcome coverage vs stories

| Scope outcome | Story | Status |
| --- | --- | --- |
| e14-visible-transcript | e14s01 | ✅ SC-e14s01-P0-01, P1-01 |
| e14-run-state | e14s01 | ✅ SC-e14s01-P0-02, P0-03 |
| e14-tool-summary | e14s02 | ✅ SC-e14s02-P0-01, P0-02, P1-01 |
| e14-safety | e14s02, e14s05 | ✅ SC-e14s02-P0-03; s05 bounded/plain fallbacks |
| e14-theme | e14s02, e14s05 | ✅ SC-e14s02-P2-01, SC-e14s05-P1-02 |
| e14-approval | e14s03 | ✅ SC-e14s03-P0-01..P1-01 |
| e14-composer | e14s03, e14s05 (selector drafts in s04) | ✅ approval restore; queue restore; SC-e14s04-P1-02 |
| e14-discovery | e14s04 | ✅ SC-e14s04-P1-01..P1-03 |
| e14-status | e14s04 | ✅ SC-e14s04-P1-04 |

No in-scope e14 outcome is unmapped. Out-of-scope items (steering, concurrency, live cards, new Core events, Textual/web) remain excluded in stories, test plan, and `REPL-UI-FUTURE-DIRECTIONS.md`.

## Pre-flight Answers

| Command or decision | Value |
| --- | --- |
| test | `uv run --offline pytest` |
| build | `uv build --offline` |
| lint | `uv run --offline ruff check .` |
| format | `uv run --offline ruff format .` |
| typecheck | `uv run --offline mypy src` |
| CI | Existing GitHub Actions `.github/workflows/ci.yml` (PR/push `main`, Python 3.12–3.14, `scripts/check-release-gate.sh`) plus local offline gates. This audit did not run CI or the full quality gate. |
| workflow | solo-git |
| language | Python 3.12+, prompt-toolkit, Rich, Pydantic, AnyIO |
| codebase | existing, not greenfield |

## Validation evidence

```text
uv run --offline python scripts/check-spec-consistency.py
→ specification consistency: clean

test -f specs/tech-architecture/e14-TEST_PLAN_LATEST.md
→ TEST_PLAN_OK

find specs/epics/e14-agent-workspace-interaction -name '*-tasks.yaml' | wc -l
→ 5

20 tasks: every verify: non-empty, every status: failing

bash scripts/lib/plan-consistency-check.sh specs/epics/e14-agent-workspace-interaction
→ CRITICAL=0 HIGH=0 MED=0 PASS
```

## Open Gaps

None that fail slice-tasks, plan-tests, or plan-work.

Non-blocking `/bp-build` notes (not a return to planning):

- [ ] Pin the s02 expand/collapse control in the first failing test (do not invent live cards).
- [ ] If local submit can still echo before admission, assert fail-to-admit under s01 task 1.
- [ ] Do not treat the security `echo` suffix as a scan.

## Verdict

**READY** — implementation plan revision `7ba51e19f3172273` is detailed enough for `/bp-build`, and `specs/state.yaml` records explicit user approval of this exact revision. Starting cursor remains `e14s01`.

This audit ends at the planning approval checkpoint. The approval checkpoint is satisfied; next step is `/bp-build` for the complete e14 epic.

---

## Preserved previous audits

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

---

# Plan Audit — Mia Agent Workspace Interaction

**Date:** 2026-09-08 · **Verdict:** READY
**Placement:** New queued e14 blueprint for `v0.7.0-agent-workspace`; completed e13 and the v0.6.0 scope remain historical.

## Principles Alignment

| Check | Status | Note |
| --- | --- | --- |
| Vertical slices | ✅ | e14 is bounded around one user outcome: observe and control one foreground Agent Run. Story slicing is intentionally deferred to `bp-plan`. |
| Scope bounded | ✅ | `specs/product/SCOPE_E14_LATEST.yaml` defines immediate inclusions, explicit exclusions, constraints, and promotion boundaries. |
| Success criteria | ✅ | Criteria cover exactly-once transcript presentation, Core-truthful outcomes, Tool safety, approval, queue behavior, focus, accessibility, and plain output. |
| Hard gates | ✅ | Core Run truth, Tool middleware, approval safety, no concurrent Runs, terminal ownership, and no credential disclosure are explicit gates. |
| Domain language | ✅ | Agent, Run, Tool, Session, Core, Adapter, approval, draft, and follow-up queue use existing Mia terminology. |
| Prior-art boundary | ✅ | Pi is a read-only reference; no Pi dependency, compatibility promise, or surface clone is introduced. |

## Conventions Completeness

| Check | Status | Note |
| --- | --- | --- |
| Project guidance | ✅ | `CLAUDE.md`, `AGENTS.md`, and `CONVENTIONS.md` exist and define the canonical runtime and solo-git workflow. |
| Specs layout | ✅ | Product, architecture, epic, state, release, and verification directories exist. |
| Commit policy | ✅ | Conventional Commits and protected-main rules are documented. |
| Existing codebase | ✅ | Python 3.12+, prompt-toolkit + Rich, existing REPL and typed runtime events. |
| New dependency | ✅ | None proposed. |

## Pre-flight Answers

| Command or decision | Value |
| --- | --- |
| Test | `uv run --offline pytest` |
| Build | `uv build --offline` |
| Lint | `uv run --offline ruff check .` |
| Format | `uv run --offline ruff format .` |
| Typecheck | `uv run --offline mypy src` |
| CI platform | No new CI platform required; use the repository's local/offline gates. |
| Workflow | `solo-git`; direct commits to `main` are protected, so work uses a local feature branch. |
| Language/framework | Python 3.12+, prompt-toolkit, Rich, Pydantic, AnyIO. |
| Release placement | Queued e14 for `v0.7.0-agent-workspace`. |

## Open Gaps

- [ ] Story specifications and task ledgers — intentionally deferred to `bp-plan` after e14 is selected.
- [x] Queue behavior after provider/tool failure — restore queued text to the draft; auto-run only after successful settlement.
- [x] Cross-terminal delivery of `Ctrl+Q` — `/queue` is the required portable fallback; terminal flow control must not be changed silently.

The unchecked item is an intentional planning boundary, not a blocker for the epic-level blueprint. No build skill should start until e14 is selected and `bp-plan` resolves the story-level behavior.

## Verdict

**READY** — The e14 feature has a bounded next-release scope, explicit exclusions, compatible architecture constraints, observable success criteria, an impact assessment, and an epic capsule. Keep it queued; run `bp-plan` before implementation.

## Verification

```bash
test -f specs/PLAN-AUDIT_LATEST.md && grep -q 'Verdict: READY' specs/PLAN-AUDIT_LATEST.md
```
