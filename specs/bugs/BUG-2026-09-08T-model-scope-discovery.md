---
bug_id: BUG-2026-09-08T-model-scope-discovery
status: open
severity: medium
scope: cli/providers
title: Scoped models include stale providers and use incomplete model discovery
---

# Scoped model availability and discovery

## Problem

`/scoped-models` must show models that are usable through providers currently configured in Mia. A saved scope can outlive a credential logout, and provider choices must not leak in from a user's shell or project `.env` file.

## Decision

Follow Tau's provider/model selection design with a persisted catalog:

- Treat a provider as connected only when it has a stored API/OAuth credential under `~/.mia`, or an explicitly configured local `custom` endpoint.
- After authentication, fetch Pi's current curated provider catalog from `https://pi.dev/api/models/providers/{provider}` and persist the model IDs under `~/.mia`. Fall back to native/provider-local discovery only when Pi's catalog is unavailable.
- `/scoped-models` reloads local settings and reads the stored catalog; it does not fetch on every picker open. Never read shell or project environment credentials.
- Treat `provider::model` as the durable identity in scoped-model persistence.
- Intersect saved scope with currently usable provider/model choices before opening any selector.
- Use the local catalog fallback only when a provider listing request is unavailable or fails.

## Evidence

Provider documentation checked:

- OpenAI: https://platform.openai.com/docs/api-reference/models/list
- Anthropic: https://docs.anthropic.com/en/api/models-list
- Google Gemini: https://ai.google.dev/api/models
- OpenRouter: https://openrouter.ai/docs/api-reference/models/get-models
- DeepSeek: https://api-docs.deepseek.com/api/list-models
- OpenCode Zen: https://opencode.ai/docs/zen
- Pi catalog implementation: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/remote-catalog-provider.ts
- Pi catalog endpoint: https://pi.dev/api/models/providers/openai-codex

## Acceptance criteria

- [x] `/scoped-models` lists only models belonging to currently connected providers.
- [x] A refresh after logout/removal removes that provider's models from the in-memory and persisted scope.
- [x] After refresh, `/model` and cycling cannot resolve a stale/unavailable scoped ID.
- [x] Connected providers are limited to credentials/configuration stored under `~/.mia`.
- [x] Authenticated providers fetch and persist their model catalog under `~/.mia`.
- [x] `/scoped-models` reads the stored catalog instead of fetching every time.
- [x] Provider listing failures use the local catalog fallback.
- [x] No scope-picker path reads shell or project environment credentials.
- [x] Focused tests, full quality checks, and spec consistency are run; unrelated warnings are reported.

## Implementation progress

- [x] Connected-provider detection now requires a known provider with a stored API/OAuth credential or configured custom endpoint.
- [x] Authenticated provider catalogs are fetched from Pi's curated catalog and persisted.
- [x] Saved scopes are reconciled and persisted against stored provider-qualified choices.
- [x] `/scoped-models`, `/model`, and cycling do not read shell/project environment credentials.
- [x] Full repository validation passed; three non-blocking test warnings remain.
