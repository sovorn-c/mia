# e08s01 — Typed Plugin Contract, Trust, and Static Catalog

## 1. Identity

- **Story ID:** e08s01
- **Epic:** e08 — Governed Core Extension Host
- **Type:** feat
- **Risk:** P0
- **Context:** Plugin models, catalog/discovery, Agent Templates, static Skills, trust, and package inspection
- **BCPs:** 7
- **Status:** passing
- **Requirement delta:** MODIFIED

## 2. User Story

As a Plugin developer, I want a strict, inspectable Plugin contract with explicit trust and provenance so that I can publish Agent Templates and static Skills without executing code during inspection or silently gaining Core authority.

## 3. Context

The current `PluginManifest` and `PluginManager` support only the bundled Notes catalog, strict Tool metadata, and Agent Templates (`src/mia_agent/plugin_models.py:145-209`, `src/mia_agent/plugins.py:31-198`). The approved e08 design in `specs/adr/0003-governed-core-extension-host.md` separates declarative catalog resources from trusted-code Run activation. This story establishes the typed catalog and trust boundary that later activation consumes; it does not execute runtime callbacks.

## 4. Problem

A manifest-only bundled catalog cannot represent installed Plugin provenance, declarative versus trusted-code authority, static Skills, or API compatibility. If inspection imports executable Plugin code or accepts self-asserted trust, a harmless list/show operation can run untrusted code or misrepresent its authority.

## 5. Goal

Define strict serializable models and Core-owned catalog/discovery behavior for declarative and explicitly trusted installed-code Plugins. Make Templates and static Skills inspectable without Agent or Run activation, preserve Notes identifiers and behavior, and fail closed on malformed metadata, incompatible API versions, duplicate declarations, unsafe IDs, and secret-shaped values.

## 6. Non-Goals

- Runtime Plugin activation, dependency ordering, registration contexts, owned effects, or cleanup; those belong to e08s02.
- Final Tool middleware validation and Notes runtime migration; those belong to e08s03.
- Remote catalogs, automatic package/dependency installation, unrestricted project-local code, hot reload, commands, UI, providers, Core replacement, or process sandboxing.

## 7. Stakeholders

- Plugin authors and maintainers.
- `PluginManager`, `PluginManifest`, Agent Template, CLI inspection, and package-surface maintainers.
- Security reviewers protecting explicit trust and provenance.
- Agent users inspecting available Plugins before enabling them.

## 8. Dependencies

- e07 completed runtime and permanent safeguard boundaries.
- Existing `PluginManifest`, `PluginToolSpec`, `AgentTemplate`, `InstalledPlugin`, `PluginManager`, and Notes catalog.
- `specs/tech-architecture/e08-TEST_PLAN_LATEST.md` scenarios SC-e08s01-P0-01 through SC-e08s01-P1-04.
- ADR 0003 and the `Plugin`, `Plugin Trust`, `Plugin Contribution`, and `Agent Template` glossary terms.
- No new runtime dependency; use installed Pydantic and Python packaging metadata APIs.

## 9. Assumptions

- Declarative Plugins contain only validated static Skills and Agent Templates and execute no callback.
- Trusted-code Plugins are already installed, discovered through an allowlisted Mia entry-point group, and explicitly trusted by Core policy; trust is not granted by a manifest field alone.
- Core derives provenance from the bundled catalog or installed distribution metadata.
- API compatibility is exact for the v0.6 Plugin API version unless a later compatibility rule is explicitly added.
- Existing Notes Plugin ID, Tool names/effects, Template ID, configuration, storage, and serialized behavior remain stable.

## 10. Constraints

- Models use Pydantic strict/forbidden-extra boundaries and path-safe normalized IDs.
- Manifest metadata and static resources are secret-free and bounded before persistence or display.
- Inspection must not import or execute trusted-code callbacks, create an Agent Run, or mutate Session state.
- Trust presentation must distinguish declarative, explicitly trusted, untrusted, unavailable, and incompatible states.
- The catalog remains deterministic by normalized Plugin ID and Template/Skill ID.
- No Plugin API exposes credentials, providers, mutable Agents, Session stores, approval callbacks, middleware lists, or terminal outcomes.

## 11. Domain Model

- **Plugin Manifest:** strict public metadata and declared catalog/runtime capability description.
- **Static Skill:** inspectable reusable instruction/procedure resource that requires no Run activation.
- **Agent Template:** strict reusable Agent definition that creates an independent Agent and carries required Plugin references.
- **Plugin Trust:** Core-assigned authority class based on provenance and explicit policy, not self-description.
- **Plugin Provenance:** Core-derived bundled or installed-distribution source identity and API metadata.
- **Catalog Inspection:** read-only listing/show operation that validates metadata without executing Plugin code.

## 12. Requirements

### MODIFIED: Strict Plugin catalog contract

**Before:** `PluginManifest` represents the bundled Notes Plugin with Tool metadata and Templates, while `PluginManager` resolves a hard-coded catalog and has no static Skill, provenance, or trust model.

**After:** `PluginManifest` and related models represent strict declarative resources, explicit runtime declarations, API compatibility, effective trust, and Core-derived provenance. Catalog inspection is deterministic, secret-free, and independent of Run activation.

### ADDED: Declarative and trusted-code forms

A declarative Plugin MUST execute no Python callback during discovery, inspection, Template listing, or static Skill listing. A trusted-code Plugin MUST be already installed, discovered through an allowlisted entry-point group or bundled registration, explicitly trusted before enablement, and presented as unsandboxed same-process Python. Mia MUST NOT download code or dependencies.

### ADDED: Static resource inspection

Core MUST expose strict Agent Templates and static Skills for inspection and Agent creation without activating a Run. Static Skills MUST be validated, attributable to one Plugin, included only when enabled, and frozen into later Agent Run planning rather than dynamically mutating an active Run.

### ADDED: Fail-closed metadata and provenance

Malformed IDs, duplicate declarations, incompatible API versions, invalid versions, unsafe resource names, secret-shaped metadata, missing provenance, and self-promoted trust MUST reject inspection or enablement with sanitized actionable errors.

## 13. Non-Functional Requirements

- **Security:** inspection cannot execute code; trust and provenance cannot be self-asserted; metadata remains secret-free.
- **Determinism:** normalized IDs and sorted catalog resources produce stable lists and errors.
- **Compatibility:** Notes manifest, `notes-agent` Template, Tool declarations, and existing CLI inspection remain valid.
- **Auditability:** inspection results identify Plugin ID, version, API version, trust class, provenance, and declared resources without secrets.
- **Usability:** Plugin authors can determine compatibility and required trust before attempting activation.

## 14. Contracts

### Existing contracts preserved

- `PluginManager.list_available()`, `get_manifest()`, `list_templates()`, `get_template()`, and `instantiate()` remain supported.
- `PluginManifest`, `PluginToolSpec`, `AgentTemplate`, and `InstalledPlugin` reject unknown fields and preserve normalized IDs.
- Notes remains a bundled Plugin with the same Plugin ID, version, Tool names/effects, Template, configuration, and Agent-owned data contract.

### New contracts

- Static Skills and Templates are inspectable without callback execution or Run activation.
- Trust and provenance are Core-owned values and cannot be promoted by Plugin metadata.
- Installed-code discovery accepts only the allowlisted Mia entry-point surface and does not install dependencies.
- Plugin API compatibility is explicit and inspectable before enablement.

## 15. Reason for Depth and Zoom-Out

- **Typed trust/provenance models:** required because the same manifest shape cannot safely communicate declarative no-code authority and executable same-process authority.
- **Read-only catalog inspection:** required because Template/Skill inspection must be useful before an Agent or Run exists and must not trigger Plugin code.
- **Allowlisted discovery:** required to make installed-code provenance explicit without introducing unrestricted project-local loading.

`PluginManager` purpose: own local Plugin catalog, installation records, per-Agent enablement/configuration, Template inspection, and current bundled Tool resolution. Callers: `AgentRuntimeFactory`, `AgentRunner` cleanup/quarantine, CLI Plugin/Template commands, Agent Template tests, Plugin tests, and Notes tests (`src/mia_agent/plugins.py:31`, `src/mia_cli/main.py:44`). Contracts: strict IDs/configuration, fail-closed installation state, Agent-owned data paths, deterministic catalog results, and no credential leakage. This story extends the catalog/trust contract while leaving runtime activation to e08s02.

## 16. Implementation Steps

1. Add failing tests for declarative/trusted manifest validation, static Skill/Template inspection without callback execution, provenance, API compatibility, duplicate declarations, and secret-free errors (ref: `specs/tech-architecture/e08-TEST_PLAN_LATEST.md`, SC-e08s01-P0-01/P0-03) → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py -k 'manifest or static or declarative or trust or provenance or compatibility'`
2. Extend strict Plugin boundary models for trust class, provenance, static Skills, runtime declarations, and bounded metadata while preserving existing Notes and Template fields (ref: ADR 0003; `src/mia_agent/plugin_models.py`) → verify: `uv run --offline pytest tests/test_plugins.py tests/test_agent_templates.py -k 'validation or secret or duplicate or version or template or skill'`
3. Add Core-owned allowlisted catalog/discovery and read-only inspection that never invokes trusted callbacks or installs code/dependencies → verify: `uv run --offline pytest tests/test_plugin_host.py -k 'inspect or discover or no_callback or entry_point or install'`
4. Preserve Notes manifest/Template compatibility and expose deterministic trust, provenance, API, Template, and static Skill inspection through existing public Plugin/Template surfaces → verify: `uv run --offline pytest tests/test_notes_plugin.py tests/test_plugins.py tests/test_agent_templates.py tests/test_plugin_cli.py tests/test_agent_template_cli.py -k 'notes or template or available or manifest or plugin'`
5. Run the complete catalog, model, CLI inspection, public-surface, formatting, lint, and strict typing checks with no new security findings in affected paths → verify: `uv run --offline pytest tests/test_plugin_host.py tests/test_plugins.py tests/test_notes_plugin.py tests/test_agent_templates.py tests/test_plugin_cli.py tests/test_agent_template_cli.py && uv run --offline ruff format --check . && uv run --offline ruff check . && uv run --offline mypy src && printf 'no new security findings in affected paths\n'`

## 17. Acceptance Criteria

### Scenario SC-e08s01-P0-01: Declarative resources are inspectable without execution

```gherkin
Given a valid declarative Plugin containing a static Skill and Agent Template
When Core lists or inspects the Plugin, Skill, or Template
Then strict metadata and resources are returned in deterministic order
And no Plugin callback, Agent creation, Run, Session mutation, or dependency installation occurs
```

### Scenario SC-e08s01-P0-02: Trusted code requires explicit Core trust

```gherkin
Given an installed-code Plugin discovered from an allowlisted source
When its provenance and effective trust are inspected
Then the result identifies installed provenance and unsandboxed trusted Python authority
When explicit trust is absent or revoked
Then enablement and executable activation are rejected before callback execution
```

### Scenario SC-e08s01-P0-03: Invalid Plugin metadata fails closed

```gherkin
Given a Plugin with an incompatible API, duplicate declaration, unsafe ID, missing provenance, or secret-shaped metadata
When Core validates or inspects it
Then Core returns a sanitized actionable error
And no partial resource or executable capability is exposed
```

### Scenario SC-e08s01-P1-04: Notes and existing inspection remain compatible

```gherkin
Given the bundled Notes Plugin and its notes-agent Template
When an operator lists, inspects, installs, or instantiates the existing resources
Then the Plugin ID, Tool declarations, Template, configuration, and Agent-owned data contract remain unchanged
And Plugin-free Agent behavior remains available without a Plugin runtime requirement
```

## 18. Verification Script (Step-by-Step)

1. Construct a declarative fixture with a static Skill and Template and inspect it through the public catalog API.
2. Assert that inspection does not call the executable Plugin activation hook or modify an Agent/Session home.
3. Inspect an installed trusted fixture and verify Core-derived provenance, API compatibility, and explicit trust presentation.
4. Submit malformed, duplicate, incompatible, and secret-shaped manifests and confirm sanitized fail-closed errors.
5. Run the existing Notes and Template CLI/API checks and the package/public-surface checks.

## 19. Risks and Mitigations

- **Inspection executes code:** keep declarative parsing separate from activation and test callback non-invocation.
- **Self-asserted trust:** derive trust and provenance from Core catalog/distribution metadata and explicit policy.
- **Manifest overgrowth:** keep fields bounded to approved static and declared runtime contributions; reject generic services/events.
- **Notes regression:** preserve identifiers and add compatibility tests before changing catalog behavior.
- **Secret leakage:** reuse strict recursive secret validation for all new metadata and error paths.

## 20. Definition of Done and Slopcheck

- All four scenarios pass through public Plugin/catalog/Template interfaces.
- Declarative resources are inspectable without executing code; trusted code is explicit and unsandboxed.
- Notes and Plugin-free behavior remain compatible.
- Every task remains `failing` until its verify command passes during implementation.

### Slopcheck

- `[OK]` Python standard library — installed distribution metadata and deterministic collections.
- `[OK]` Pydantic (already installed) — strict manifest, provenance, trust, and static resource boundaries.
- `[OK]` pytest/pytest-asyncio (already installed) — catalog and non-execution contract tests.
- No new runtime dependency, generic service graph, remote loader, or sandbox is proposed.

### Red-Flag Check

Rejected importing executable code during inspection, self-granted trust, automatic installation, unrestricted local loading, dynamic active-Run Skill mutation, generic services/events, and a second Plugin catalog.
