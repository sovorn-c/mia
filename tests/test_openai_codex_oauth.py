from __future__ import annotations

import base64
import json
import socket
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from mia_agent.auth.config import ConfigManager, MiaConfig
from mia_agent.auth.credentials import FileCredentialStore, OAuthCredential
from mia_agent.auth.openai_auth import (
    OPENAI_CODEX_AUTHORIZE_URL,
    OPENAI_CODEX_CLIENT_ID,
    OPENAI_CODEX_REDIRECT_URI,
    OPENAI_CODEX_SCOPE,
    OPENAI_CODEX_TOKEN_URL,
    OpenAIOAuthManager,
    account_id_from_access_token,
    create_authorization_flow,
)


def _jwt(*, account_id: str = "acct_test", expires: int | None = None) -> str:
    payload = {
        "exp": expires or int(time.time()) + 3600,
        "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{encoded}.signature"


def test_codex_authorization_flow_matches_tau_contract() -> None:
    flow = create_authorization_flow()
    query = flow.url.split("?", 1)[1]
    assert flow.url.startswith(f"{OPENAI_CODEX_AUTHORIZE_URL}?")
    assert f"client_id={OPENAI_CODEX_CLIENT_ID}" in query
    assert (
        f"redirect_uri={OPENAI_CODEX_REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')}" in query
    )
    assert f"scope={OPENAI_CODEX_SCOPE.replace(' ', '+')}" in query
    assert "code_challenge_method=S256" in query
    assert flow.state
    assert flow.verifier


def test_codex_exchange_persists_oauth_not_api_key(tmp_path: Path, monkeypatch: Any) -> None:
    access = _jwt()
    calls: list[dict[str, object]] = []

    def post(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append({"url": url, **kwargs})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "access_token": access,
                "refresh_token": "refresh-test",
                "expires_in": 3600,
            },
        )

    monkeypatch.setattr("mia_agent.auth.openai_auth.httpx.post", post)
    store = FileCredentialStore(tmp_path / "credentials.json")
    ok, message, returned = OpenAIOAuthManager(store)._exchange_code_for_token(
        "auth-code", "verifier"
    )

    assert ok is True
    assert "successfully" in message
    assert returned == access
    assert calls[0]["url"] == OPENAI_CODEX_TOKEN_URL
    assert calls[0]["data"] == {
        "grant_type": "authorization_code",
        "client_id": OPENAI_CODEX_CLIENT_ID,
        "code": "auth-code",
        "redirect_uri": OPENAI_CODEX_REDIRECT_URI,
        "code_verifier": "verifier",
    }
    credential = store.get_oauth("openai-codex")
    assert credential is not None
    assert credential.refresh == "refresh-test"
    assert credential.account_id == "acct_test"
    assert store.get_api_key("openai-codex") is None
    assert account_id_from_access_token(access) == "acct_test"


def test_callback_state_mismatch_is_rejected(tmp_path: Path, monkeypatch: Any) -> None:
    from mia_agent.auth import openai_auth

    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]

    monkeypatch.setattr(openai_auth, "OPENAI_CODEX_CALLBACK_PORT", port)

    def open_browser(url: str) -> bool:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        response = httpx.get(
            f"http://localhost:{port}/auth/callback?code=forged&state=wrong",
            timeout=2,
        )
        assert response.status_code == 400
        assert params["state"][0] != "wrong"
        return True

    monkeypatch.setattr("mia_agent.auth.openai_auth.webbrowser.open", open_browser)
    ok, message, token = OpenAIOAuthManager(
        FileCredentialStore(tmp_path / "credentials.json")
    ).start_oauth_flow(timeout_seconds=2)

    assert ok is False
    assert "state mismatch" in message.lower()
    assert token is None


def test_refresh_uses_codex_token_contract(tmp_path: Path, monkeypatch: Any) -> None:
    access = _jwt(account_id="acct_refreshed")

    def post(_url: str, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "access_token": access,
                "refresh_token": "next-refresh",
                "expires_in": 3600,
            },
        )

    monkeypatch.setattr("mia_agent.auth.openai_auth.httpx.post", post)
    credential = OpenAIOAuthManager(
        FileCredentialStore(tmp_path / "credentials.json")
    ).refresh_token("old-refresh")

    assert credential.access == access
    assert credential.refresh == "next-refresh"
    assert credential.account_id == "acct_refreshed"
    assert credential.expires > int(time.time() * 1000)


def test_config_routes_selected_codex_model_to_oauth_provider(tmp_path: Path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set_oauth(
        "openai-codex",
        OAuthCredential(access="access", refresh="refresh", expires=9_999_999_999_999),
    )
    manager = ConfigManager(tmp_path / "config.json", store)
    manager.save_config(MiaConfig(default_provider="openai-codex", default_model="gpt-5.3-codex"))

    provider, model, api_key, base_url = manager.resolve_credentials(model="gpt-5.3-codex")

    assert (provider, model, api_key) == ("openai-codex", "gpt-5.3-codex", None)
    assert base_url == "https://chatgpt.com/backend-api"


def test_pasted_codex_token_is_stored_as_oauth(tmp_path: Path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    access = _jwt()

    ok, message = OpenAIOAuthManager(store).save_codex_access_token(access)

    assert ok is True
    assert "saved" in message
    assert store.get_oauth("openai-codex") is not None
    assert store.get_api_key("openai-codex") is None
