# e06s04 — Purge Legacy Project Surfaces and Verify the Clean Break

## 1. Identity

- **Story ID:** e06s04
- **Epic:** e06 — Zero-Legacy Agent Core
- **Type:** refactor
- **Risk:** P1
- **Context:** living documentation, instructions, specifications, release metadata, tests, and packaging
- **BCPs:** 5
- **Status:** failing
- **Requirement delta:** MODIFIED

## 2. User Story

As a public Mia contributor, I want the project guidance, specifications, and package surface to describe the same Agent-centric system as the code so that obsolete architecture is not taught or rediscovered.

## 3. Context

The source and frontend cleanup leave a second class of legacy: agent instructions, README/help text, product language, architecture notes, release metadata, old planning capsules, and verification records still explain the historical identity model. This story makes active documentation truthful, removes legacy-only artifacts under the agreed Git-history-only rule, and verifies that the retained Textual frontend is still packaged.

## 4. Problem

Stale documentation is an active contributor interface. If it teaches Profile, Mode, Workflow, Herd, compatibility, or the old orchestration flow, future work will recreate the deleted architecture even when runtime code is clean. Broken release-plan references and stale package expectations also make the clean break unverifiable.

## 5. Goal

Rewrite active guidance and specifications around Agent, Skill, Tool, Plugin, Task, Delegation, Run, and Session; delete legacy-only planning/history artifacts and obsolete verification records; update release/state metadata for e06; retain Textual packaging; and leave one runnable scan/build gate proving the project surface is clean.

## 6. Non-Goals

- New product capabilities or a deeper TUI design pass.
- Rewriting Agent, Plugin, Delegation, Session, or provider behavior.
- Deleting or migrating user files outside the repository.
- Removing Textual or the `mia tui` command.
- Preserving old planning artifacts in the working tree when Git history already preserves them.
- Reclassifying generic prose that does not describe a public domain identity or runtime path.

## 7. Stakeholders

- Public contributors reading AGENTS.md, CLAUDE.md, README, and specs.
- Maintainers using release/state metadata and verification gates.
- Users discovering `mia`, Agent, Plugin, Template, Session, and TUI commands.
- Package consumers relying on the retained CLI and Textual frontend.

## 8. Dependencies

- e06s01 canonical runtime names and contracts.
- e06s02 retained TUI boundary.
- e06s03 source, tests, CLI, Session, and access cleanup.
- Current README, AGENTS.md, CLAUDE.md, product specs, technical architecture, ADRs, release/status metadata, and package configuration.

## 9. Assumptions

- AGENTS.md and CLAUDE.md remain byte-for-byte identical.
- Active documentation teaches only the target model; it does not need a migration guide for deleted commands.
- Legacy-only docs, old planning capsules, and obsolete verification records may be deleted because Git history is the preservation mechanism.
- Useful e05 Plugin/Template contracts are retained in current code and rewritten active product docs, not preserved through old compatibility prose.
- Textual remains an intentionally shallow supported frontend and stays in dependencies and wheel output.

## 10. Constraints

- No new dependency and no package metadata change that removes Textual.
- Documentation must not claim unsupported isolation, integrations, autonomy, or runtime features.
- Active specs must reference existing files and current story/status IDs.
- No secrets, credentials, or user-home data are copied into documentation or fixtures.
- The final forbidden-surface scan covers source, tests, README, guidance, docs, and specs after legacy-only deletions.
- Use the repository's existing YAML, consistency, coverage, Ruff, Mypy, pytest, and build checks.

## 11. Domain Model

- **Agent:** only durable configured/addressable identity.
- **Skill:** reusable instruction or procedure.
- **Tool:** callable capability mediated by Mia Core.
- **Plugin:** installable executable extension.
- **Task/Delegation:** bounded Agent-to-Agent work and routing.
- **Run/Session:** execution and append-only durable history.
- **Mia Core:** trusted composition, policy, attribution, persistence, and routing boundary.

## 12. Requirements

### MODIFIED: Contributor guidance

**Before:** AGENTS.md, CLAUDE.md, and architecture docs describe Profile, ModeRuntime, Workflow, and Herd as current behavior and instruct contributors to use them.

**After:** guidance describes CLI/REPL/TUI → AgentRunner → AgentRuntimeFactory → AgentHarness and the Agent/Skill/Tool/Plugin/Delegation model only. AGENTS.md and CLAUDE.md remain identical.

### MODIFIED: Product language

**Before:** active vision, glossary, README, and technical docs contain historical identity taxonomies and compatibility claims.

**After:** active product language uses Agent as the only identity and describes private sequencing without a public legacy object. Capability claims match shipped code.

### MODIFIED: Planning/status cockpit

**Before:** release/state/status metadata points at superseded compatibility capsules and obsolete active paths.

**After:** the cockpit points at e06 and current Agent-centric artifacts; no active reference points to deleted legacy-only files.

### REMOVED: Legacy-only documentation and verification artifacts

**Before:** initial plans, old plans, old orchestration capsules/snapshots, compatibility migration records, and obsolete verification files remain in the repository.

**After:** (removed) — those files are deleted after their durable Agent contracts are represented in active docs. Git history remains the preservation mechanism.

### MODIFIED: Package surface

**Before:** package and test expectations are coupled to deleted legacy modules, while TUI packaging is not explicitly protected during cleanup.

**After:** the wheel contains Agent, Plugin, Delegation, Session, CLI/REPL, and retained Textual TUI packages; deleted legacy modules are absent and Textual remains available.

### ADDED: Forbidden-surface regression gate

A repeatable repository check MUST fail if removed identity symbols, imports, commands, aliases, or package paths reappear in active source, tests, docs, or package output.

## 13. Non-Functional Requirements

- **Clarity:** a new contributor can identify AgentRunner, AgentRuntimeFactory, AgentHarness, AgentManager, Plugins, Delegation, Sessions, and TUI without historical terminology.
- **Truthfulness:** docs do not promise deleted compatibility, unsupported integrations, or deeper TUI functionality.
- **Durability:** status and release references are internally consistent.
- **Security:** forbidden scans do not print credentials; existing security checks remain unchanged.
- **Reproducibility:** YAML validation, source scans, package inspection, and quality gates run offline.

## 14. Contracts

### Existing contracts preserved

- Current Agent, Plugin, Template, Delegation, access, Session, provider, CLI, REPL, and TUI behavior.
- Textual dependency and `mia tui` entrypoint.
- Byte-identical AGENTS.md/CLAUDE.md requirement.
- Existing release quality commands and coverage threshold.

### Removed contracts

- Documentation promise of Profile/Mode/Herd compatibility.
- References to deleted legacy capsules and verification files.
- Package presence of legacy modules and old import paths.

### New contracts

- Active repository surfaces expose only Agent-centric identity and execution vocabulary.
- Release/status metadata references only existing active artifacts.
- Forbidden-symbol scan and wheel inspection are required completion evidence.

## 15. Reason for Depth and Zoom-Out

- **Guidance rewrite:** required because contributor instructions are a source-of-truth interface and currently direct new work toward deleted architecture.
- **Artifact deletion:** required because the user explicitly chose Git history over retaining legacy-only project files; no migration/archive framework is needed.
- **Forbidden-surface gate:** required because deletion-only cleanup regresses easily when a later contributor restores an old import or command.

`specs/` is the project planning and verification cockpit. Its callers are contributors, release scripts, quality gates, and future planning sessions. Its contracts are valid paths, coherent story/status metadata, truthful product vocabulary, and runnable verification evidence. The retained TUI is intentionally protected rather than redesigned.

## 16. Implementation Steps

1. Rewrite AGENTS.md and CLAUDE.md byte-for-byte together, plus README, active glossary, vision, ubiquitous language, technical architecture, security review, and package/CLI descriptions, to document only the current Agent-centric flow → verify: `cmp -s AGENTS.md CLAUDE.md && grep -RInE '\b(AgentRunner|AgentRuntimeFactory|AgentHarness|AgentManager|Plugin|Delegation|Session)\b' README.md AGENTS.md CLAUDE.md specs/product specs/tech-architecture >/dev/null`
2. Remove legacy-only docs/specs/verification records and update release-plan, execution-status, planning context, state, and ADR references so every active path exists and no deleted architecture is named → verify: `test -f specs/epics/e06-zero-legacy-agent-core/epic.yaml && ! grep -RInE 'docs/initial_plan|specs/old_plan|e03-native-orchestration|archive/e04|archive/e05|AUDIT-e03|AUDIT-e04|e03s01-verify|e04s04-verify' specs --include='*.yaml' --include='*.md'`
3. Keep Textual and mia tui in package metadata, inspect the built wheel, and verify deleted source packages/modules are absent while the retained TUI package is present → verify: `grep -q 'textual>=' pyproject.toml && uv build --offline && uv run --offline python - <<'PY'
import glob
import zipfile
wheels = sorted(glob.glob('dist/*.whl'))
assert wheels
with zipfile.ZipFile(wheels[-1]) as wheel:
    names = set(wheel.namelist())
    assert any(name.startswith('mia_cli/tui/') for name in names)
    assert not any(name.startswith(('mia_agent/profiles/', 'mia_agent/herd/', 'mia_agent/mode_runtime')) for name in names)
print('wheel surface is clean and TUI is retained')
PY`
4. Run the repository-wide forbidden-surface scan, YAML/spec consistency check, and full quality gate; record evidence only after all commands pass → verify: `! grep -RInE '\b(AgentProfile|ProfileManager|ModeRuntime|ModeCatalog|WorkflowStage|HerdManager|ManagedAgent|AgentState|MiaHerdApp)\b|mia_agent\.(profiles|herd)|--profile|/profile|--mode|/mode|code_mode' src tests README.md AGENTS.md CLAUDE.md docs specs && bash scripts/lib/plan-consistency-check.sh specs/epics/e06-zero-legacy-agent-core/ && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest && ./scripts/check-coverage.sh && uv build --offline`

## 17. Acceptance Criteria

### Scenario SC-e06s04-P1-01: Guidance teaches one model

```gherkin
Given a new contributor reads AGENTS.md, CLAUDE.md, README.md, and active architecture/spec documents
When they look for the runtime and domain model
Then they find Agent/Skill/Tool/Plugin/Delegation/Run/Session terminology
And they find no instructions to use deleted identity or orchestration concepts
And AGENTS.md and CLAUDE.md are byte-for-byte identical
```

### Scenario SC-e06s04-P1-02: Legacy-only artifacts are gone

```gherkin
Given the repository after cleanup
When active documentation and planning paths are enumerated
Then legacy-only plans, capsules, snapshots, and verification records are absent
And release/state metadata references only existing active artifacts
```

### Scenario SC-e06s04-P1-03: TUI packaging remains

```gherkin
Given the retained shallow Textual frontend
When Mia is built and the wheel is inspected
Then Textual remains declared
And mia_cli/tui is present
And deleted Profile/Herd/Mode modules are absent
```

### Scenario SC-e06s04-P1-04: Forbidden surface is guarded

```gherkin
Given a contributor accidentally reintroduces a removed symbol, import, flag, or slash command
When the repository forbidden-surface check runs
Then the check fails before release verification can pass
```

### Scenario SC-e06s04-P1-05: Full project quality remains green

```gherkin
Given source, tests, docs, and metadata have been cleaned
When the complete quality gate runs
Then formatting, lint, strict typing, tests, coverage, specification consistency, and build all pass
```

## 18. Verification Script (Step-by-Step)

1. Run `cmp -s AGENTS.md CLAUDE.md` and inspect active guidance for the Agent-only flow.
2. Run the forbidden-surface scan and confirm it returns no matches.
3. Run the planning consistency check against the e06 capsule.
4. Run the full Ruff, Mypy, pytest, coverage, and build commands.
5. Inspect the wheel and confirm `mia_cli/tui` exists while deleted legacy packages do not.

## 19. Risks and Mitigations

- **Over-deleting useful product evidence:** delete only legacy-only artifacts; retain current Agent/Plugin contracts in active docs and Git history.
- **Broken status links:** run the consistency check after every metadata deletion/update.
- **TUI accidentally removed:** assert Textual declaration, `mia tui --help`, TUI tests, and wheel contents.
- **Documentation drift:** require the forbidden scan and byte-identical guidance check in the final gate.
- **False capability claims:** rewrite current reality and architecture from shipped source, not old planning prose.

## 20. Definition of Done and Slopcheck

- Active guidance, product docs, architecture, release metadata, and package checks describe the Agent-centric system.
- Legacy-only docs/specs/verification files are removed under the Git-history-only decision.
- Textual and `mia tui` remain supported and packaged.
- Forbidden-surface, consistency, quality, coverage, and build gates pass.
- All tasks remain `failing` until their verify commands pass.

### Slopcheck

- `[OK]` Existing Python, YAML, shell, pytest, Ruff, Mypy, coverage, and wheel inspection tools — no new dependency.
- `[OK]` Textual (already installed) — explicitly retained, not expanded.
- No documentation generator, migration framework, or archive service is added.

### Red-Flag Check

Rejected preserving obsolete compatibility documentation “for context,” deleting the TUI for convenience, changing Textual dependencies, or claiming a clean break without a source/package scan and full quality gate.
