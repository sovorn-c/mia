# Audit Code — e04s04

- **Branch:** `e04-agent-centric-foundation`
- **Scope:** `main...HEAD` plus audit remediation in the working tree.
- **Run:** 2026-09-02T00:22:25Z
- **Verdict:** **PASS (scope-qualified)**

The audit found and fixed three concrete boundary issues: legacy Mode/Profile execution did not receive the Agent access middleware or approval callback; persisted full-access consent was overridden by the runner's default; and nested tuple/set metadata could bypass credential-key validation. Filesystem Tools now reject paths outside their configured working directory. The e04 core implementation was split into focused contract, runner, compatibility, factory, delegation, storage, and legacy-adapter modules. All checks passed after these fixes.

## Checklist

### Supply Chain & Security

- ✓ **Dependencies:** no dependency files changed; slopcheck classification was not applicable.
- ✓ **SLOP packages:** none added.
- ✓ **Secrets:** no real credential values found in the diff. Test-only redaction fixtures are clearly synthetic.
- ✓ **OWASP spot-check:** input/path traversal, access control, sensitive-data exposure, malformed JSON, provider/tool errors, and approval boundaries reviewed.
- ✓ **Security findings:** `specs/security/REVIEW.md` records PASS; no unaddressed HIGH finding remains in the reviewed paths.

### Provenance & Metadata

- ✓ **Plan metadata:** the e04 epic and story include `type` and `context` metadata.
- ✓ **Decision references:** active e04s04 story/task artifacts reference the prompt-run ADR and the canonical AgentRunner, CLI, and Delegation commits.

### Law of Demeter

- ✓ No unsafe multi-hop collaborator chains were found in the changed paths. `runtime.harness`, `runtime.session_store`, and `self.factory.agent_manager` are direct collaborators used at their owning boundary.

### CONVENTIONS.md Compliance

- ✓ No root documentation was added; verification output is under `specs/`.
- ✓ No issue-creation calls, GitHub REST calls, or unrelated `gh` operations were introduced.
- ⚠ `CONVENTIONS.md` is absent in this checkout. Compliance was checked against byte-identical `AGENTS.md`/`CLAUDE.md` and the project instructions.

### Scope

- ✓ Changes remain within Agent/runtime/access/compatibility, security, test, and verification scope.
- ✓ No speculative feature or dependency was added.
- ✓ Audit-discovered defects were fixed with focused regression tests.

### Boy Scout Rule

- ✓ Changed files contain no commented-out code or dead code introduced by this work.
- ✓ The filesystem path helper, policy forwarding, and consent resolution reduce existing risk without broad refactoring.

### Types and Safety

- ✓ Public Python functions are typed; `mypy src` passes.
- ✓ No unsafe ignore directives or unchecked cast additions were found.
- ✓ `ruff check .` passes.

### Test Coverage

- ✓ New and corrected behavior is covered through public AgentRunner, ModeRuntime, AgentManager, and Tool interfaces.
- ✓ Regression tests cover nested secret metadata, persisted full-access consent, legacy approval enforcement, and filesystem boundary rejection.
- ✓ Full suite passes: **146 tests**.
- ⚠ The repository-local `skills/enforce-first` verifier is absent; FIRST properties were checked from the focused tests and existing suite behavior.

### SOLID and Heuristics

- ✓ No new unrelated responsibility was introduced by the remediation.
- ✓ Existing dependency injection boundaries are preserved; no global provider/runtime root was added.
- ✓ No concrete G/N/C/T heuristic violation was found in the remediation diff.

### Refactoring Smells

- ✓ No new Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Message Chain, or Middle Man was introduced by the remediation.
- ⚠ The broader e04 diff retains intentionally large orchestration/CLI modules; this is a maintainability concern, not a new remediation defect.

### Code Style

- ✓ Formatting, lint, types, and diff whitespace checks pass.
- ✓ Coverage gate passes: 89% scoped first-party core and 97% execution/access/filesystem business boundary.
- ✓ **Structural size:** e04 core modules are now focused and below 300 lines (`manager.py` 298, `delegation.py` 263, `runtime_factory.py` 265, `mode_runtime.py` 226, `agent_runner.py` 170). The existing CLI shells (`main.py` 367 and `repl.py` 1,227) received only thin routing/approval changes and remain separately scoped UI-maintenance work; moving methods without reducing responsibility was intentionally skipped.
- ✓ Names and conditionals are clear in the remediation; no new magic values or commented-out code were added.

## Validation

```text
uv run --offline ruff format --check .   PASS
uv run --offline ruff check .            PASS
uv run --offline mypy src                 PASS (58 files)
uv run --offline pytest                   PASS (146 tests)
./scripts/check-coverage.sh                PASS (89% / 97%)
uv build --offline                       PASS
spec YAML validation                     PASS
git diff --check                         PASS
```

Unavailable repository helpers:

- `scripts/bp-churn-rank.sh`
- `scripts/check-blind-spots.sh`
- `scripts/lib/completeness-critic.sh`
- `skills/enforce-first`
- `skills/request-review`

Fallback used: `git diff --numstat` for churn ranking, direct guidance comparison, focused public-interface tests, and the full quality gate.

## Scope note

The repository-local helper scripts and `CONVENTIONS.md` remain unavailable in this checkout. The fallback checks are recorded above. A future UI-maintenance change may split the pre-existing CLI shells, but that is not required for this e04 audit because the changed CLI code is limited to routing and approval propagation.
