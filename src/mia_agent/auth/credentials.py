"""Tau-style local credential store managing API keys and OAuth tokens."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiKeyCredential(BaseModel):
    """API key credential."""

    type: Literal["api_key"] = "api_key"
    key: str


class OAuthCredential(BaseModel):
    """Refreshable OAuth credential."""

    type: Literal["oauth"] = "oauth"
    access: str
    refresh: str
    expires: int = 0
    account_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def default_credentials_path() -> Path:
    """Return default credentials path under ~/.mia/credentials.json."""
    return Path.home() / ".mia" / "credentials.json"


class FileCredentialStore:
    """JSON-backed persistent credential store under ~/.mia/credentials.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_credentials_path()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        temp_dir = self.path.parent
        with NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2)
            temp_path = Path(tf.name)
        temp_path.replace(self.path)

    def get_api_key(self, name: str) -> str | None:
        """Retrieve stored API key by provider name."""
        data = self._load().get(name.lower())
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            if data.get("type") == "api_key":
                return str(data.get("key", ""))
            if "key" in data:
                return str(data["key"])
        return None

    def set_api_key(self, name: str, key: str) -> None:
        """Store an API key for a provider."""
        key = key.strip()
        if not key:
            raise ValueError("API key cannot be empty.")
        data = self._load()
        data[name.lower()] = ApiKeyCredential(key=key).model_dump()
        self._save(data)

    def get_oauth(self, name: str) -> OAuthCredential | None:
        """Retrieve stored OAuth credential by provider name."""
        raw = self._load().get(name.lower())
        if isinstance(raw, dict) and raw.get("type") == "oauth":
            try:
                return OAuthCredential.model_validate(raw)
            except Exception:
                return None
        return None

    def set_oauth(self, name: str, credential: OAuthCredential) -> None:
        """Store an OAuth credential for a provider."""
        data = self._load()
        data[name.lower()] = credential.model_dump()
        self._save(data)

    def delete(self, name: str) -> bool:
        """Delete stored credential by provider name."""
        data = self._load()
        if name.lower() in data:
            del data[name.lower()]
            self._save(data)
            return True
        return False

    def list_stored_providers(self) -> list[str]:
        """List all provider names stored in credentials."""
        return sorted(self._load().keys())
