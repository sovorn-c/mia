# Security Review — e03s01

- **Branch:** `e03-native-orchestration`
- **Diff scope:** merge-base `main` through current implementation
- **Reviewed:** `src/mia_agent/orchestration.py`, `src/mia_agent/harness.py`, `src/mia_cli/main.py`, `src/mia_cli/repl.py`, `src/mia_cli/interactive_input.py`, profile/session/tool boundaries
- **Verdict:** PASS — no concrete HIGH or MEDIUM vulnerability at confidence >= 8 was identified.

## Checks

- Profile-local tool filtering remains enforced by `ProfileManager.filter_tools` before every `AgentHarness` is built.
- Existing `SecurityGuardMiddleware` remains in every profile pipeline that enables it.
- Session persistence uses JSON plus Pydantic validation; no unsafe deserializer was added.
- Provider credentials remain resolved through `ConfigManager`; credentials are passed to provider clients and are not added to orchestration envelopes.
- Orchestration identity is metadata only and does not execute shell input or alter tool permissions.
- CLI `--profile`, `--mode`, `--resume`, session deletion, and prompt key handling are local trusted terminal inputs under the repository's security-review precedent; no remote attacker boundary exists in this application slice.

## Notes

`session_id` and custom profile names are used in local filesystem paths by pre-existing session/profile infrastructure. This review found no new remotely reachable exploit path; path hardening remains a reasonable future defense-in-depth improvement if Mia exposes these values to an untrusted service boundary.

## e03s02 In-Flight Adjustment Addendum

- **Diff scope:** `e903f00..HEAD`
- **Verdict:** PASS — no HIGH or MEDIUM vulnerability at confidence >= 8.
- Model APIs are queried only for providers with stored credentials/OAuth records or recognized API-key environment variables; keys are not rendered or persisted in model scope state.
- Provider identity remains attached to model choices with internal `provider::model` IDs, preventing same-name models from selecting another provider's credential.
- Disconnected providers and their scoped models are pruned on the next discovery pass.
- Top-level `--session` accepts IDs only; path components are rejected before session filesystem resolution. The CLI emits a bounded Typer error without traceback, and rendered IDs are Rich-escaped.
- No shell interpolation, unsafe deserialization, new network endpoint, dependency, or secret-bearing log was introduced.

## BUG-001 Addendum

- **Scope:** `/scoped-models` interactive multi-selection and config-backed scope persistence.
- **Verdict:** PASS — no security impact identified.
- The selector accepts model IDs from provider discovery and persists them as ordinary JSON strings; no selected model ID is executed as a command or used as a filesystem path.
- Escape/cancel preserves the previous scope, and config updates use Pydantic-validated `MiaConfig` data.

## e04 Agent-Centric Foundation Addendum

- **Branch:** `e04-agent-centric-foundation`
- **Diff scope:** `main...HEAD`, limited to changed Agent, access, Delegation, runtime, Session, Tool, CLI, and compatibility paths.
- **Reviewed:** Agent ID/path normalization and atomic writes; legacy Profile projection; capability/effect filtering; approval callback data; full-access confirmation; one-hop Delegation; provider/tool error propagation; session attribution; CLI aliases.
- **Verdict:** PASS — no concrete HIGH or MEDIUM vulnerability at confidence >= 8 was identified.

### Boundary checks

- Agent and Session filesystem paths are derived from normalized IDs; native Agent definitions use atomic same-directory replacement. Legacy files are read without rewrite. Filesystem Tools reject absolute, traversal, and symlink-resolved paths outside their configured working directory.
- Access policy is fail-closed for unknown or side-effecting Tools, read-only Agents filter mutating Tools, approval requests redact credential-shaped keys and values, and full access requires explicit confirmation. Legacy Mode/Profile adapters now pass the same policy and approval callback.
- Delegation validates recipient eligibility before provider/session access, rejects self/recursive requests, bounds prompt/timeout/depth, intersects caller and recipient capabilities, and requires both sides' full-access consent for a delegated full-access child.
- Provider, Tool, orchestration, audit, and Delegation error payloads are sanitized before user-visible event/session/telemetry boundaries. No credential literal was introduced in changed source.
- No new shell interpolation, unsafe deserialization, SQL/HTTP sink, authentication endpoint, or dependency was introduced. `BashTool` still runs with the configured working directory and remains approval-gated for side effects; the filesystem Tools now reject paths outside that directory.

## e05 Plugin and Agent Template Addendum

- **Branch:** `e05-notes-plugin`
- **Diff scope:** `main...HEAD`, limited to Plugin manifests/lifecycle, Notes storage Tools, Agent Template validation/instantiation, runtime Tool composition, telemetry attribution, and CLI commands.
- **Reviewed:** local installation state and JSON validation; Agent/Plugin ID normalization; template allowlisting and secret rejection; requirement checks before persistence; Agent-owned note/session paths; symlink and traversal checks; capability/effect filtering; Plugin Tool attribution; CLI error/output paths.
- **Verdict:** PASS — no concrete HIGH or MEDIUM vulnerability at confidence >= 8 was identified.

### Boundary checks

- Plugin installation is bundled and explicit; no arbitrary Python loading, network fetch, or implicit installation was added. Installed state is JSON-loaded and validated through Pydantic, with malformed/duplicate state rejected.
- Template instantiation validates required compatible Plugins and target identity before `AgentManager` persistence. Templates exclude runtime identity, credentials, Sessions, memory, metadata, defaults, and full-access consent; full-access templates are rejected.
- Plugin and Agent IDs are normalized before local path use. Notes roots reject symlinked ancestors, note IDs are allowlisted, note files are atomically replaced, and list/read reject unsafe symlinks.
- Plugin Tools are composed through the existing access/effect middleware and carry Plugin provenance into events and audit records. CLI inspection renders metadata only and does not expose Plugin configuration values.
- No new command, HTTP, SQL, unsafe-deserialization, or secret-bearing logging sink was introduced.
