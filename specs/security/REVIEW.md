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
