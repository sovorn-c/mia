---
bug_id: BUG-2026-09-08T090648Z
status: open
severity: medium
priority: P1
scope: auth
security_impact: low
title: OpenAI browser authentication uses an unsupported OAuth client contract
---

# BUG-2026-09-08T090648Z: OpenAI browser authentication does not create a Mia login

## Problem

The OpenAI browser login can reach a local callback page that says
`Mia Authentication Successful!`, but the terminal does not obtain a usable,
persistent OpenAI session. With the current values, OpenAI rejects the token
exchange as `invalid_client`; when the exchange is mocked, Mia stores the
OAuth access token as an API key and routes it through the ordinary OpenAI API
provider. A successful browser callback therefore does not mean that Mia is
logged in.

Expected behavior: a successful browser login uses an OpenAI-supported OAuth
client contract, validates the callback, persists a refreshable OAuth
credential, and activates a provider that can use that credential. A failed
exchange must not display or persist a successful login state.

Minimal reproduction:

1. Start Mia and run `/login`.
2. Select `Auth` and press Enter at the manual-token prompt.
3. Inspect the generated authorization URL or complete the browser flow.
4. Observe that the request uses `client_id=app-mia-coding-agent` and
   `redirect_uri=http://localhost:14555/auth/callback`.
5. The token endpoint rejects a dummy exchange with:

   ```text
   HTTP 401 {"error": {"code": "invalid_client"}}
   ```

6. In a deterministic local callback simulation with a mocked successful token
   response, the callback returns HTTP 200 and the flow returns success, but
   `FileCredentialStore.get_oauth("openai")` returns `None` after the flow.

Security impact: LOW. No confirmed token-theft path was identified; PKCE
reduces the impact of code substitution. The callback handler does not
validate `state`, however, so OAuth login-CSRF protection and concurrent-flow
isolation are incomplete. The resulting failure is also an authentication
integrity problem because the browser success page can be shown before token
exchange succeeds.

## Root Cause Analysis

### Phase 1 — Reproduce

Environment: Mia repository on local `main`, Python 3.14.6, uv offline
environment, macOS development host, no stored credentials. The browser and
network behavior was reproduced without using a real account or persisting a
real token.

Evidence:

- Capturing `start_oauth_flow()` produced an authorization request containing
  `app-mia-coding-agent`, port `14555`, and scopes
  `openid email profile model.read model.request`.
- `POST https://auth.openai.com/oauth/token` with that client ID and a dummy
  authorization code returned HTTP 401 `invalid_client`.
- The OpenAI discovery document currently advertises `openid`, `profile`,
  `email`, and `offline_access`; it does not advertise Mia's
  `model.read`/`model.request` scopes.
- A real local callback simulation returned HTTP 200 with the Mia success page,
  then invoked the token exchange. This separates local callback receipt from
  successful authentication.
- A mocked 200 token exchange returned success but left only an `api_key`
  record in `credentials.json`; the refreshable OAuth record was gone.

### Phase 2 — Isolate

The feature was introduced by `f1c8dbf` and has no browser-flow regression
tests. The failure is isolated across three boundaries:

1. **Authorization contract:** the auth manager constructs a generic-looking
   OAuth request with a self-created client ID, a non-standard redirect port,
   unsupported scopes, and no OpenAI/Codex-specific parameters.
2. **Credential boundary:** `_exchange_code_for_token()` first writes an
   `OAuthCredential`, then immediately writes an API-key record under the
   same provider key. The second write replaces the first, discarding the
   refresh token and expiry metadata.
3. **Provider boundary:** `OpenAICompatibleProvider` always sends its bearer to
   `<base_url>/chat/completions`, which for `openai` is
   `https://api.openai.com/v1/chat/completions`. ChatGPT/Codex OAuth requires
   its supported backend route and auth headers; it is not interchangeable
   with an OpenAI API key.

The REPL config write is not the primary failure: a mocked successful login
sets `default_provider` to `openai` and persists the config. It leaves
`default_model` empty by design, so `/model` is still required after a
successful provider login.

### Phase 3 — Hypotheses

1. **Confirmed candidate — Mia implements an unsupported OpenAI OAuth
   contract.** Falsification test: compare the generated authorization/token
   request with OpenAI's discovery document and the supported Codex login
   contract, then call the token endpoint with a dummy code. The current client
   receives `invalid_client`, while the supported Codex client ID is recognized
   and reaches code validation. This is confirmed.
2. **Confirmed contributing defect — OAuth persistence is overwritten.**
   Falsification test: mock a successful token response and inspect the public
   credential-store getters. `get_api_key("openai")` succeeds but
   `get_oauth("openai")` is `None`; this is confirmed.
3. **Rejected as the primary cause — the local callback server cannot receive
   the redirect.** Falsification test: send a local callback request with a
   code and matching browser-flow timing. The handler returns HTTP 200 and the
   exchange is invoked, so local receipt works in isolation.
4. **Rejected as the primary cause — `_save_auth_state()` fails to persist the
   provider.** Falsification test: run the REPL login with a mocked successful
   OAuth manager. `default_provider` is saved as `openai`; only model selection
   remains pending.
5. **Confirmed contributing security defect — callback state is ignored.**
   Falsification test: send a callback with an arbitrary state and a code. The
   handler accepts it with HTTP 200 because it has no expected-state input or
   comparison.

### Phase 4 — Verified root cause

The root cause is an architectural contract mismatch: Mia treats ChatGPT/OpenAI
OAuth as a generic API-key OAuth flow. It uses an unregistered client ID and
request contract, stores the result in the API-key slot, and sends the token
through the API-key provider. The direct token-endpoint response
(`invalid_client`), the successful-but-non-refreshable mocked flow, and the
provider route inspection confirm that changing only the browser callback or
redirect handling would not produce a usable login.

The missing callback-state validation and credential overwrite are concrete
secondary defects exposed by the same unsupported integration. A complete fix
must either remove the browser OAuth option and require an OpenAI API key, or
implement ChatGPT/Codex OAuth as a separate supported credential/provider
path. The recommended fix is the latter; keep ordinary OpenAI API-key auth
unchanged and never route a ChatGPT OAuth token through the API-key provider.

Risk: Medium. The change crosses authentication, credential persistence, and
provider construction boundaries. The security impact is low because no
confirmed token-theft exploit was found, but state validation and secret
handling must remain explicit.

## TDD Fix Plan

1. **RED:** Add a public authorization-flow contract test that asserts the
   authorization and token requests use the configured supported OpenAI OAuth
   endpoints, registered client identity, matching redirect URI, supported
   scopes, PKCE, and state. The test must fail for the current
   `app-mia-coding-agent` request.
   **GREEN:** Replace scattered constants with one supported OAuth configuration
   and use it for both authorization and token exchange. Keep the existing API
   key login contract separate.
   **verify:** `uv run --offline pytest tests/test_openai_codex_oauth.py -k contract`

2. **RED:** Add callback tests through the local HTTP boundary: matching state
   returns a code; missing or mismatched state returns an error and never
   starts token exchange.
   **GREEN:** Pass the expected state into a per-flow callback handler/result,
   validate it before accepting a code, and close the callback server on
   success, error, timeout, or cancellation.
   **verify:** `uv run --offline pytest tests/test_openai_codex_oauth.py -k callback`

3. **RED:** Add a credential-store regression test that completes a mocked
   successful exchange and then asserts that the OAuth record still contains
   refresh and expiry data and that no second write replaces it with an API-key
   record.
   **GREEN:** Persist one typed OAuth credential atomically; extend the model
   with the account/ID-token metadata required by the supported provider. Do
   not call `set_api_key()` for a ChatGPT OAuth credential.
   **verify:** `uv run --offline pytest tests/test_openai_codex_oauth.py -k credential`

4. **RED:** Add a provider integration test that runs one authenticated request
   with an OAuth credential and asserts the supported ChatGPT/Codex route and
   required headers are used, while an ordinary OpenAI API key still uses
   `api.openai.com/v1`.
   **GREEN:** Add the smallest separate OAuth-aware provider/transport and
   refresh path needed by the official contract. Keep
   `OpenAICompatibleProvider` API-key-only rather than adding OAuth branches to
   every OpenAI-compatible provider.
   **verify:** `uv run --offline pytest tests/test_openai_codex_oauth.py tests/test_openai_codex_provider.py`

5. **RED:** Add a REPL scenario test for success and failure: success makes the
   provider discoverable and reports the next model-selection action; token
   exchange failure leaves credentials/config unchanged and reports an
   actionable failure instead of a browser-only success.
   **GREEN:** Wire the typed authenticated state into `MiaREPL`, preserve the
   existing `/model` requirement, and only call `_save_auth_state()` after the
   complete exchange and persistence path succeeds.
   **verify:** `uv run --offline pytest tests/test_cli_repl.py -k 'login or oauth'`

6. **RED:** Add port-in-use, timeout, cancellation, and browser-open-failure
   tests proving no orphaned server or stale class-level code/error remains.
   **GREEN:** Use a per-flow result object and deterministic server cleanup;
   return a truthful terminal error for every incomplete flow.
   **verify:** `uv run --offline pytest tests/test_openai_codex_oauth.py -k 'timeout or cancel or port'

**REFACTOR:** Remove the class-level callback state and any compatibility
writes that blur API-key and OAuth credential types. Keep secrets out of logs
and user-visible exception text.

## Acceptance Criteria

- [ ] Browser authorization uses a supported OpenAI OAuth client contract.
- [ ] The callback validates state and handles only the active flow.
- [ ] Token exchange failure cannot produce a successful login state.
- [ ] Successful OAuth login preserves refreshable credential data.
- [ ] ChatGPT/Codex OAuth uses its supported provider route; API-key OpenAI
      login remains unchanged.
- [ ] `/model` remains the explicit model-selection step after provider login.
- [ ] Timeout, cancellation, port collision, and browser failures clean up
      without stale credentials or callback state.
- [ ] No credential, token, or authorization value appears in logs or output.
- [ ] All new and existing tests pass.

## Implementation progress

- [x] Adopted Tau's supported Codex PKCE contract: registered client, `/oauth/authorize`, `/oauth/token`, port 1455, supported scopes, account-ID extraction, and refresh-token persistence.
- [x] Added state-validated callback handling and truthful exchange failure behavior.
- [x] Added a separate ChatGPT/Codex Responses provider with the required route and headers; ordinary OpenAI API-key routing remains unchanged.
- [x] Wired OAuth provider/model selection through ConfigManager, AgentRuntimeFactory, and the inline REPL.
- [x] Added OAuth contract, callback, refresh, credential, routing, text-stream, and tool-call tests.
- [ ] Full repository suite is still blocked by three pre-existing no-model REPL tests; auth-focused tests pass.

## Resolution

Implementation is complete locally but remains uncommitted pending the repository's existing unrelated test failures being resolved or explicitly waived.

Evidence:

- `uv run --offline pytest tests/test_openai_codex_oauth.py tests/test_openai_codex_provider.py` — 10 passed; `tests/test_cli_repl.py -k 'login or oauth'` — 3 passed.
- `uv run --offline ruff check .` — passed.
- `uv run --offline mypy src` — passed.
- `uv build --offline` — passed.
- Full suite: 380 passed, 3 pre-existing no-model REPL failures.
