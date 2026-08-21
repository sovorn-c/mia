"""OpenAI OAuth 2.0 PKCE and Browser Authentication handler."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from mia_agent.auth.credentials import FileCredentialStore, OAuthCredential

OPENAI_AUTH_HOST = "https://auth.openai.com"
OPENAI_CLIENT_ID = "app-mia-coding-agent"  # Mia client ID
REDIRECT_PORT = 14555
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/auth/callback"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Local HTTP callback listener for OAuth redirection."""

    auth_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
                b"<h2 style='color:#FF7A00;'>&#x1F955; Mia Authentication Successful!</h2>"
                b"<p>You can close this tab and return to your terminal.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            OAuthCallbackHandler.error = params.get("error_description", ["Authentication failed"])[
                0
            ]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authentication failed</h2></body></html>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        # Silence HTTP server logs
        pass


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class OpenAIOAuthManager:
    """Manages OpenAI OAuth 2.0 PKCE browser authentication and token lifecycle."""

    def __init__(self, cred_store: FileCredentialStore | None = None) -> None:
        self.cred_store = cred_store or FileCredentialStore()

    def start_oauth_flow(self, timeout_seconds: int = 120) -> tuple[bool, str, str | None]:
        """Start browser-based OAuth PKCE login flow.

        Returns (success, message, access_token).
        """
        verifier, challenge = generate_pkce()
        state = secrets.token_hex(16)

        auth_params = {
            "response_type": "code",
            "client_id": OPENAI_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": "openid email profile model.read model.request",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        auth_url = f"{OPENAI_AUTH_HOST}/authorize?{urllib.parse.urlencode(auth_params)}"

        OAuthCallbackHandler.auth_code = None
        OAuthCallbackHandler.error = None

        server: HTTPServer | None = None
        server_thread: threading.Thread | None = None

        try:
            server = HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
            server_thread = threading.Thread(target=server.handle_request, daemon=True)
            server_thread.start()
        except Exception:
            # Port might be in use, continue to allow manual token entry
            pass

        with contextlib.suppress(Exception):
            webbrowser.open(auth_url)

        # If server is running, wait for browser callback
        if server and server_thread:
            server_thread.join(timeout=timeout_seconds)

            if OAuthCallbackHandler.auth_code:
                code = OAuthCallbackHandler.auth_code
                return self._exchange_code_for_token(code, verifier)

            if OAuthCallbackHandler.error:
                return False, f"OAuth error: {OAuthCallbackHandler.error}", None

        return False, "OAuth callback timed out or was not received", None

    def _exchange_code_for_token(self, code: str, verifier: str) -> tuple[bool, str, str | None]:
        """Exchange authorization code for access and refresh tokens."""
        token_url = f"{OPENAI_AUTH_HOST}/oauth/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": OPENAI_CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }

        try:
            resp = httpx.post(token_url, data=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token", "")
                expires_in = data.get("expires_in", 3600)

                if access_token:
                    oauth_cred = OAuthCredential(
                        access=access_token,
                        refresh=refresh_token,
                        expires=expires_in,
                    )
                    self.cred_store.set_oauth("openai", oauth_cred)
                    self.cred_store.set_api_key("openai", access_token)
                    return True, "OpenAI OAuth authenticated successfully", access_token

            return False, f"Token exchange failed (HTTP {resp.status_code}): {resp.text}", None
        except Exception as e:
            return False, f"Token exchange error: {e}", None

    def save_direct_token(self, token: str) -> tuple[bool, str]:
        """Save a direct OpenAI OAuth session/bearer token with validation."""
        token = token.strip()
        if not token:
            return False, "Token cannot be empty"

        # Validate against OpenAI models endpoint
        try:
            resp = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {token}"},
                timeout=6.0,
            )
            if resp.status_code == 200:
                self.cred_store.set_api_key("openai", token)
                return True, "OpenAI token validated and saved successfully"
            elif resp.status_code in (401, 403):
                return False, f"Invalid OpenAI token (HTTP {resp.status_code} Unauthorized)"
            else:
                self.cred_store.set_api_key("openai", token)
                return True, f"Token saved (HTTP {resp.status_code})"
        except Exception as e:
            return False, f"Validation error: {e}"
