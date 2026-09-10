"""OpenAI Codex OAuth 2.0 PKCE browser authentication."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from mia_agent.auth.credentials import FileCredentialStore, OAuthCredential

OPENAI_CODEX_PROVIDER = "openai-codex"
OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_CODEX_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
OPENAI_CODEX_CALLBACK_PORT = 1455
OPENAI_CODEX_SCOPE = "openid profile email offline_access"
OPENAI_CODEX_ACCOUNT_CLAIM = "https://api.openai.com/auth"
TOKEN_REFRESH_SKEW_MS = 60_000

# Compatibility aliases for callers that imported the old names.
OPENAI_AUTH_HOST = "https://auth.openai.com"
OPENAI_CLIENT_ID = OPENAI_CODEX_CLIENT_ID
REDIRECT_PORT = OPENAI_CODEX_CALLBACK_PORT
REDIRECT_URI = OPENAI_CODEX_REDIRECT_URI


@dataclass(frozen=True, slots=True)
class AuthorizationFlow:
    verifier: str
    state: str
    url: str


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Compatibility callback handler with state validation."""

    expected_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.accepted = False
        self.auth_code: str | None = None
        self.error: str | None = None
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        state = _first_query_value(params, "state")
        if self.expected_state is not None and state != self.expected_state:
            self._respond(400, "OAuth state mismatch.")
            return

        if _first_query_value(params, "error"):
            self.error = _first_query_value(params, "error_description") or _first_query_value(
                params, "error"
            )
            self._respond(400, "Authentication failed.")
            return

        code = _first_query_value(params, "code")
        if not code:
            self._respond(400, "Missing authorization code.")
            return

        self.auth_code = code
        self.accepted = True
        self._respond(200, "OpenAI authentication completed. You can close this window.")

    def _respond(self, status: int, message: str) -> None:
        body = (
            f"<!doctype html><meta charset='utf-8'><title>Mia OAuth</title><p>{message}</p>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def generate_pkce() -> tuple[str, str]:
    """Generate a PKCE code verifier and S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def create_authorization_flow(originator: str = "tau") -> AuthorizationFlow:
    """Build the supported OpenAI Codex authorization request."""
    verifier, challenge = generate_pkce()
    state = secrets.token_hex(16)
    params = {
        "response_type": "code",
        "client_id": OPENAI_CODEX_CLIENT_ID,
        "redirect_uri": OPENAI_CODEX_REDIRECT_URI,
        "scope": OPENAI_CODEX_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": originator,
    }
    return AuthorizationFlow(
        verifier=verifier,
        state=state,
        url=f"{OPENAI_CODEX_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}",
    )


class OpenAIOAuthManager:
    """Manage OpenAI Codex OAuth credentials and legacy API-key login."""

    def __init__(self, cred_store: FileCredentialStore | None = None) -> None:
        self.cred_store = cred_store or FileCredentialStore()

    def start_oauth_flow(self, timeout_seconds: int = 120) -> tuple[bool, str, str | None]:
        """Run the browser flow and persist a refreshable Codex credential."""
        flow = create_authorization_flow()
        result: dict[str, str | None] = {"code": None, "error": None}
        server: ThreadingHTTPServer | None = None
        server_thread: threading.Thread | None = None

        class CallbackHandler(OAuthCallbackHandler):
            expected_state = flow.state

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                super().do_GET()
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if getattr(self, "accepted", False):
                    result["code"] = _first_query_value(params, "code")
                else:
                    result["error"] = "OAuth state mismatch or invalid callback"
                result["error"] = (
                    result["error"]
                    or _first_query_value(params, "error_description")
                    or _first_query_value(params, "error")
                )
                if server is not None:
                    threading.Thread(target=server.shutdown, daemon=True).start()

        try:
            server = ThreadingHTTPServer(("localhost", OPENAI_CODEX_CALLBACK_PORT), CallbackHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
        except OSError as exc:
            return False, f"Could not start OAuth callback listener: {exc}", None

        try:
            with contextlib.suppress(Exception):
                webbrowser.open(flow.url)
            server_thread.join(timeout=timeout_seconds)
            code = result["code"]
            if result["error"]:
                return False, f"OAuth error: {result['error']}", None
            if not code:
                return False, "OAuth callback timed out or was not received", None
            return self._exchange_code_for_token(code, flow.verifier)
        finally:
            server.shutdown()
            server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=1)

    def _exchange_code_for_token(self, code: str, verifier: str) -> tuple[bool, str, str | None]:
        """Exchange an authorization code and persist the typed OAuth credential."""
        payload = {
            "grant_type": "authorization_code",
            "client_id": OPENAI_CODEX_CLIENT_ID,
            "code": code,
            "redirect_uri": OPENAI_CODEX_REDIRECT_URI,
            "code_verifier": verifier,
        }
        try:
            response = httpx.post(
                OPENAI_CODEX_TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
            if response.status_code >= 400:
                return False, f"Token exchange failed (HTTP {response.status_code})", None
            data = response.json()
            access = _required_string(data, "access_token")
            refresh = _required_string(data, "refresh_token")
            account_id = account_id_from_access_token(access)
            if account_id is None:
                return False, "Token exchange failed: access token has no ChatGPT account", None
            expires = token_expiry(data, access)
            try:
                self.cred_store.set_oauth(
                    OPENAI_CODEX_PROVIDER,
                    OAuthCredential(
                        access=access,
                        refresh=refresh,
                        expires=expires,
                        account_id=account_id,
                    ),
                )
            except OSError as exc:
                return (
                    False,
                    f"Token exchange succeeded but credentials could not be saved: {exc}",
                    None,
                )
            return True, "OpenAI Codex OAuth authenticated successfully", access
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            return False, f"Token exchange error: {exc}", None

    def refresh_token(self, refresh_token: str) -> OAuthCredential:
        """Refresh one Codex OAuth credential."""
        response = httpx.post(
            OPENAI_CODEX_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": OPENAI_CODEX_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        if response.status_code >= 400:
            raise ValueError(f"Token refresh failed (HTTP {response.status_code})")
        data = response.json()
        access = _required_string(data, "access_token")
        account_id = account_id_from_access_token(access)
        if account_id is None:
            raise ValueError("Token refresh failed: access token has no ChatGPT account")
        return OAuthCredential(
            access=access,
            refresh=str(data.get("refresh_token") or refresh_token),
            expires=token_expiry(data, access),
            account_id=account_id,
        )

    def save_codex_access_token(self, token: str) -> tuple[bool, str]:
        """Persist a pasted Codex access JWT for the rest of its lifetime."""
        token = token.strip()
        if not token:
            return False, "Token cannot be empty"
        account_id = account_id_from_access_token(token)
        expires = _access_token_expiry(token)
        if account_id is None or expires is None:
            return False, "Invalid OpenAI Codex access token"
        try:
            self.cred_store.set_oauth(
                OPENAI_CODEX_PROVIDER,
                OAuthCredential(access=token, refresh="", expires=expires, account_id=account_id),
            )
        except OSError as exc:
            return False, f"Credentials could not be saved: {exc}"
        return True, "OpenAI Codex access token saved successfully"

    def save_direct_token(self, token: str) -> tuple[bool, str]:
        """Keep the legacy API-token helper for ordinary OpenAI API credentials."""
        token = token.strip()
        if not token:
            return False, "Token cannot be empty"
        try:
            response = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {token}"},
                timeout=6.0,
            )
            if response.status_code == 200:
                self.cred_store.set_api_key("openai", token)
                return True, "OpenAI token validated and saved successfully"
            if response.status_code in (401, 403):
                return False, f"Invalid OpenAI token (HTTP {response.status_code} Unauthorized)"
            self.cred_store.set_api_key("openai", token)
            return True, f"Token saved (HTTP {response.status_code})"
        except Exception as exc:
            return False, f"Validation error: {exc}"


def account_id_from_access_token(access_token: str) -> str | None:
    payload = _jwt_payload(access_token)
    auth = payload.get(OPENAI_CODEX_ACCOUNT_CLAIM) if payload else None
    account_id = auth.get("chatgpt_account_id") if isinstance(auth, dict) else None
    return account_id.strip() if isinstance(account_id, str) and account_id.strip() else None


def _access_token_expiry(access_token: str) -> int | None:
    payload = _jwt_payload(access_token)
    exp = payload.get("exp") if payload else None
    return int(exp * 1000) if isinstance(exp, int | float) and exp > 0 else None


def token_expiry(data: dict[str, Any], access_token: str) -> int:
    expires_in = data.get("expires_in")
    if isinstance(expires_in, int | float) and not isinstance(expires_in, bool):
        return int(time.time() * 1000) + int(expires_in * 1000)
    expiry = _access_token_expiry(access_token)
    if expiry is None:
        raise ValueError("Token response has no expiry")
    return expiry


def oauth_credential_is_expired(credential: OAuthCredential) -> bool:
    expires = credential.expires if credential.expires > 10**12 else credential.expires * 1000
    return int(time.time() * 1000) >= expires - TOKEN_REFRESH_SKEW_MS


def _jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload + padding))
        return value if isinstance(value, dict) else None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _required_string(data: object, key: str) -> str:
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Token response missing {key}")
    return value


def _first_query_value(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values and values[0] else None
