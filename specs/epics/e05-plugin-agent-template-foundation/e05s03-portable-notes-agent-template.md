# e05s03 — Portable Notes Agent Template

## 1. Identity

- **Story ID:** e05s03
- **Epic:** e05 — Plugin and Agent Template Foundation
- **Type:** feat
- **Risk:** P0
- **Context:** domain, privacy, persistence, Plugin contributions, and CLI
- **BCPs:** 5
- **Status:** failing
- **Requirement delta:** ADDED

## 2. User Story

As an Agent designer, I want to inspect a reusable Notes Agent Template and instantiate it under my own Agent ID so that I can start with useful behavior without receiving another user's credentials, identity, Sessions, memory, or notes.

## 3. Context

The glossary defines an Agent Template as a distributable starting definition that becomes an independently configured Agent. e05s01 and e05s02 establish Notes installation, enablement, configuration, and Agent-owned data. This story proves the second half of VISION-05: Notes contributes one safe, serializable Agent Template and Mia creates a fresh Agent through existing validation and atomic persistence.

## 4. Problem

Copying `agent.json` is not a safe distribution contract. A live Agent may contain provider/account references, memory paths, metadata, delegation targets, full-access consent, Plugin configuration, and identity. Its home also contains Sessions and Plugin data. A template must be an explicit allowlist, not a sanitized dump that can regress when Agent gains another private field.

## 5. Goal

Deliver one bundled `notes-agent` template that users can list, inspect, serialize, and instantiate under a new path-safe Agent ID after Notes is installed. The resulting Agent has approval-required access, Notes enabled with safe defaults, no base Tools unless declared, and no source-private data. Missing requirements or collisions leave no partial Agent files.

## 6. Non-Goals

- Exporting a live Agent into a Template.
- Sharing or synchronizing Agent identity, credentials, Sessions, memory, notes, defaults, or state.
- Remote Template registries, publishing, signing, version resolution, or downloads.
- Template inheritance, composition, variables, scripts, hooks, or interactive builders.
- Automatic Plugin installation.
- Full-access Agent Templates.
- Mutable overlays for built-in Agents.

## 7. Stakeholders

- Users creating a dedicated Notes Agent quickly.
- Agent designers distributing safe defaults.
- Plugin authors contributing one Agent Template.
- Core maintainers protecting identity, credentials, state, and atomic persistence.

## 8. Dependencies

- e05s01 bundled Notes Plugin and e05s02 strict lifecycle/configuration.
- Canonical Agent and AgentManager validation/persistence.
- Plugin manifest contribution declarations and installed Plugin inspection.
- Product glossary definition of Agent Template.
- Existing Pydantic, Typer, pytest, Ruff, Mypy, coverage, and standard library.

## 9. Assumptions

- The bundled Template is available for inspection with the bundled Plugin catalog even before installation.
- Instantiation requires all declared Plugins already installed; it never installs code implicitly.
- The caller supplies a new Agent ID; the Template does not carry one.
- The Template's approval-required access is a default and never imports full-access consent.
- Notes configuration contains only a safe notebook display name and no Plugin data.
- Created Agents can be edited later through normal Agent and Plugin lifecycle commands.

## 10. Constraints

- Agent Template uses a strict Pydantic model with `extra="forbid"` and an explicit allowlist of reusable fields.
- It cannot represent `agent_id`, provider, account, credential references, memory path, channel identity, delegation targets, metadata, Sessions, selected-default state, Plugin data, or full-access consent.
- Template Plugin IDs and Tool names are normalized, unique, and declared by installed compatible manifests.
- The Notes Agent Template uses approval-required access and cannot request full-access.
- Requirement and target-ID validation completes before AgentManager creates directories or files.
- AgentManager remains the only persistence path and retains built-in/collision/path/full-access guards.
- No Template operation mutates installation state, source definitions, default Agent selection, Sessions, or notes.
- Template errors and inspection output are secret-free and deterministic offline.

## 11. Domain Model

- **Agent Template:** immutable distributable definition with template ID, version, display defaults, instructions, access policy, base Tool scope, required Plugins, and validated Plugin configuration.
- **Template Requirement:** compatible installed Plugin ID required before instantiation.
- **Template Catalog:** bundled read-only set of Agent Templates contributed by bundled Plugins.
- **Instantiation:** validation followed by creation of one fresh independent Agent through AgentManager.

## 12. Requirements

### ADDED: Strict Agent Template contract

Mia MUST define a strict Agent Template model containing only reusable public defaults. Unknown or private Agent fields MUST be rejected rather than ignored. Template serialization MUST be deterministic and contain no credential, Session, memory, Plugin-data, source-identity, default-selection, or full-access-consent value.

### ADDED: Bundled Notes Agent Template

Plugin `notes` MUST declare one `notes-agent` Template with a useful Notes-focused display name, instructions, approval-required access, no unrelated base Tools, required Plugin `notes`, and a safe default notebook display name.

### ADDED: Template inspection

Users MUST be able to list bundled Templates and inspect ID, version, description, access level, base Tools, required Plugins, and safe Plugin configuration without installing or executing code and without displaying private values.

### ADDED: Safe independent instantiation

A user MUST be able to instantiate `notes-agent` under a caller-supplied path-safe non-built-in Agent ID. Mia MUST create a fresh Agent through AgentManager with the Template's allowlisted defaults, Notes enabled, `full_access_confirmed=false`, and no inherited identity or private state.

### ADDED: Requirement validation before writes

All required Plugins MUST be installed and compatible before instantiation. Missing/incompatible requirements, malformed Template data, built-in IDs, path-unsafe IDs, or existing Agent collisions MUST fail before any target Agent path is created or changed.

### ADDED: Ownership separation

The instantiated Agent MUST receive a new Agent home and later create its own Sessions and Notes. It MUST NOT read, copy, link, or reference a source Agent home, Template author home, Plugin data root, Session file, memory file, or default selection.

## 13. Non-Functional Requirements

- **Privacy:** allowlisted construction prevents private fields from entering Templates or created Agents.
- **Security:** no implicit install, overwrite, full-access consent, path traversal, or secret rendering.
- **Durability:** instantiation is all-or-nothing through existing atomic Agent persistence.
- **Compatibility:** existing `mia agent create` without a Template retains its current behavior.
- **Determinism:** catalog, validation, CLI, and instantiation tests run offline in temporary homes.
- **Maintainability:** one concrete Template contract; no inheritance, variable engine, or export sanitizer.

## 14. Contracts

### Existing contracts preserved

- AgentManager validates IDs, rejects built-in mutation/collisions, writes atomically, and remains secret-free.
- Existing Agent creation command and fields continue to work without a Template.
- Full-access always requires explicit user confirmation and is not inherited.
- Plugin installation and Agent enablement remain explicit separate lifecycle actions.
- Agent Sessions and Plugin data remain under the created Agent's independent home.

### New contracts

- `AgentTemplate` is an allowlisted strict definition, not an Agent subclass or dump.
- Plugin manifests may declare bundled Template IDs exercised by the Notes proof.
- Template catalog inspection has no execution or installation side effect.
- Instantiation validates requirements and target identity before calling AgentManager exactly once.
- A Template never carries a durable Agent identity or private state.

## 15. Reason for Depth and Zoom-Out

- **AgentTemplate model:** required because privacy must be guaranteed by an allowlist independent of future Agent fields; a dictionary copy or exclusion list would silently leak newly added private fields.
- **Template catalog in PluginManager:** required because Templates are Plugin contributions and must share installed-requirement/version validation; a separate Template manager would duplicate the only catalog.
- **AgentManager creation reuse:** no new repository or installer is justified; the existing manager already owns validation, collision checks, full-access rules, and atomic writes.

AgentManager serves CLI, REPL, runtime, Delegation, and tests. Its preserved contracts are path-safe identity, immutable built-ins, native/legacy precedence, atomic Agent files, secret-free serialization, and Session ownership. Template instantiation prepares allowlisted fields only; it does not weaken or bypass these guards.

## 16. Implementation Steps

1. Add failing Template model, catalog, privacy, requirement, collision, path-safety, independent ownership, and no-partial-write tests before implementation (ref: VISION-05; `specs/IMPACT_LATEST.md`) → verify: `uv run --offline pytest tests/test_agent_templates.py -k 'model or privacy or requirement or collision or path or independent or partial' && printf 'no new security findings in affected paths\n'`
2. Add strict `AgentTemplate` and one bundled `notes-agent` definition to the Notes manifest/catalog using only allowlisted reusable fields; prove deterministic serialization rejects every private Agent field → verify: `uv run --offline pytest tests/test_agent_templates.py -k 'strict or bundled or notes_agent or serialize or reject or allowlist or full_access' && printf 'no new security findings in affected paths\n'`
3. Add PluginManager Template inspection and instantiation that validates installed compatible requirements and target ID/collision before calling existing AgentManager creation once with allowlisted fields and `full_access_confirmed=false` → verify: `uv run --offline pytest tests/test_agent_templates.py tests/test_agents.py -k 'inspect or instantiate or installed or compatible or create or collision or no_partial or full_access' && printf 'no new security findings in affected paths\n'`
4. Prove a created Notes Agent owns fresh Plugin data and Sessions and contains no source identity, provider/account, credentials, memory, metadata, notes, selected-default state, or consent → verify: `uv run --offline pytest tests/test_agent_templates.py tests/test_notes_plugin.py tests/test_sessions.py -k 'independent or secret or source or session or notes or default or consent' && printf 'no new security findings in affected paths\n'`
5. Add thin Template list/show/create commands while preserving normal Agent creation, and return actionable non-destructive errors for missing requirements and collisions → verify: `uv run --offline pytest tests/test_agent_template_cli.py tests/test_cli_print_mode.py -k 'template and (list or show or create or notes or missing or collision or existing_agent_create)' && printf 'no new security findings in affected paths\n'`
6. Run e05 privacy, compatibility, coverage, package, and specification gates before advancing the epic → verify: `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && uv run --offline pytest tests/test_agent_templates.py tests/test_agent_template_cli.py tests/test_plugins.py tests/test_notes_plugin.py tests/test_plugin_cli.py tests/test_agents.py tests/test_orchestration.py tests/test_access_policy.py tests/test_delegation.py tests/test_sessions.py tests/test_cli_print_mode.py tests/test_cli_repl.py && ./scripts/check-coverage.sh && uv build --offline && uv run --offline python -c "import pathlib,yaml; [yaml.safe_load(p.read_text()) for p in pathlib.Path('specs').rglob('*.yaml')]" && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e05s03-P0-01: Template serialization contains only public defaults

```gherkin
Given the bundled Notes Agent Template
When Mia serializes it for inspection or distribution
Then it contains only Template ID/version, display defaults, instructions, access, base Tools, required Plugins, and safe Plugin configuration
And it contains no Agent ID, provider/account, credential, Session, memory, metadata, note, default-selection, or full-access-consent value
```

### Scenario SC-e05s03-P0-02: Notes Agent is created independently

```gherkin
Given Notes is installed and Agent ID my-notes is unused
When the user instantiates notes-agent as my-notes
Then AgentManager creates one Agent my-notes with approval-required access
And Notes is enabled with safe defaults
And its home, future Sessions, and future notes are independently owned
And it is not selected as default implicitly
```

### Scenario SC-e05s03-P0-03: Missing requirements cause no partial write

```gherkin
Given Notes is not installed or is incompatible
When the user tries to instantiate notes-agent
Then Mia reports the missing or incompatible Plugin requirement
And no Agent directory, definition, default selection, Session, or Plugin data is created
```

### Scenario SC-e05s03-P0-04: Identity collisions are non-destructive

```gherkin
Given a built-in, native Agent, or path-unsafe target ID
When the user tries to instantiate notes-agent with that ID
Then existing Agent and legacy data remain unchanged
And no target file is overwritten or partially created
And the error identifies the corrective action without secrets
```

### Scenario SC-e05s03-P1-05: Existing Agent creation remains compatible

```gherkin
Given a user creates an Agent without selecting a Template
When the existing Agent create command runs
Then its arguments, validation, full-access confirmation, persistence, and output remain unchanged
```

### Scenario SC-e05s03-P1-06: Template inspection has no side effects

```gherkin
Given Notes is bundled but not installed
When the user lists or shows notes-agent
Then the safe Template definition is displayed
And no Plugin or Agent is installed, enabled, selected, or executed
```

## 18. Verification Script (Step-by-Step)

1. Run `uv run --offline pytest tests/test_agent_templates.py`.
2. Run `uv run --offline pytest tests/test_agent_template_cli.py -k 'list or show or create'`.
3. Run `uv run --offline pytest tests/test_agents.py tests/test_notes_plugin.py tests/test_sessions.py`.
4. Run `uv run --offline pytest tests/test_plugins.py tests/test_plugin_cli.py tests/test_orchestration.py tests/test_access_policy.py`.
5. Run `uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src`.
6. Run `./scripts/check-coverage.sh && uv build --offline`.
7. Run the repository YAML validation command.

## 19. Risks and Mitigations

- **Privacy regression:** future Agent fields could leak through copying. Mitigation: independent strict allowlisted Template model.
- **Implicit trust:** creation could install code automatically. Mitigation: installed-compatible requirement gate before any write.
- **Identity overwrite:** Template ID could be mistaken for Agent ID. Mitigation: caller supplies a separately validated target and AgentManager owns collision checks.
- **Partial Agent:** requirement failure could leave directories. Mitigation: validate all requirements/fields first and invoke one atomic Agent create operation.
- **Full-access inheritance:** a Template could carry consent. Mitigation: model forbids consent and Notes uses approval-required.
- **State sharing:** copied paths could link Agents. Mitigation: Template cannot represent state paths; AgentManager allocates the new home.

## 20. Definition of Done and Slopcheck

- All six acceptance scenarios have deterministic automated coverage.
- Template serialization is allowlisted and private-field rejection is tested.
- Missing requirements and collisions leave no partial state.
- Created Notes Agents are independent and approval-required.
- Existing Agent creation and Plugin-free behavior remain green.
- Tasks remain `failing` until their verify commands and full gate pass.

### Slopcheck

- `[OK]` Python standard library — deterministic serialization support and local path checks.
- `[OK]` Pydantic (already installed) — strict allowlisted Template boundary.
- `[OK]` Typer/Rich (already installed) — thin Template inspection and creation commands.
- `[OK]` pytest/coverage (already installed) — privacy, persistence, and compatibility proof.
- No export sanitizer, template engine, variable resolver, registry client, or new package is proposed.

### Red-Flag Check

Rejected these shortcuts: serializing a live Agent then deleting known private keys; carrying `agent_id` in the Template; auto-installing Notes; allowing full-access Templates; linking source Agent paths; overwriting on collision; selecting the created Agent implicitly; and creating a second Agent persistence path.
