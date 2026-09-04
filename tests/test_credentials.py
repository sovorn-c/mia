"""Tests for Tau-style Credentials, Auth, and Configuration Resolution."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mia_agent.auth.config import ConfigManager
from mia_agent.auth.credentials import FileCredentialStore, OAuthCredential


def test_file_credential_store_api_key_lifecycle(tmp_path: Path) -> None:
    store_file = tmp_path / "credentials.json"
    store = FileCredentialStore(path=store_file)

    # Empty initially
    assert store.get_api_key("anthropic") is None
    assert store.list_stored_providers() == []

    # Store API key
    store.set_api_key("anthropic", "sk-ant-test-12345")
    assert store.get_api_key("anthropic") == "sk-ant-test-12345"
    assert store.get_api_key("ANTHROPIC") == "sk-ant-test-12345"  # Case-insensitive
    assert store.list_stored_providers() == ["anthropic"]

    # Store another key
    store.set_api_key("openai", "sk-openai-999")
    assert store.list_stored_providers() == ["anthropic", "openai"]

    # Delete key
    assert store.delete("anthropic") is True
    assert store.get_api_key("anthropic") is None
    assert store.list_stored_providers() == ["openai"]


def test_file_credential_store_oauth_lifecycle(tmp_path: Path) -> None:
    store_file = tmp_path / "credentials.json"
    store = FileCredentialStore(path=store_file)

    oauth_cred = OAuthCredential(
        access="gho_access_token_123",
        refresh="gho_refresh_token_456",
        expires=1700000000,
        account_id="user_github",
        metadata={"scope": "copilot"},
    )

    store.set_oauth("github", oauth_cred)
    retrieved = store.get_oauth("github")

    assert retrieved is not None
    assert retrieved.access == "gho_access_token_123"
    assert retrieved.refresh == "gho_refresh_token_456"
    assert retrieved.account_id == "user_github"
    assert retrieved.metadata == {"scope": "copilot"}


def test_config_manager_resolution_hierarchy(tmp_path: Path) -> None:
    store_file = tmp_path / "credentials.json"
    config_file = tmp_path / "config.json"

    store = FileCredentialStore(path=store_file)
    store.set_api_key("deepseek", "sk-deepseek-from-store")

    manager = ConfigManager(config_path=config_file, credential_store=store)

    # 1. Infer provider from model name
    assert manager.infer_provider("claude-3-5-sonnet") == "anthropic"
    assert manager.infer_provider("gpt-4o") == "openai"
    assert manager.infer_provider("deepseek-chat") == "deepseek"

    # 2. Fallback to store when no env or explicit arg
    prov, mod, key, url = manager.resolve_credentials(model="deepseek-chat")
    assert prov == "deepseek"
    assert mod == "deepseek-chat"
    assert key == "sk-deepseek-from-store"
    assert url == "https://api.deepseek.com/v1"

    # 3. Environment variable override
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-from-env"}):
        prov, mod, key, url = manager.resolve_credentials(model="claude-3-5-sonnet")
        assert prov == "anthropic"
        assert key == "sk-ant-from-env"

    # 4. Explicit parameter overrides environment & store
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-from-env"}):
        prov, mod, key, url = manager.resolve_credentials(
            model="claude-3-5-sonnet",
            api_key="sk-ant-explicit",
            base_url="https://custom.anthropic.com",
        )
        assert key == "sk-ant-explicit"
        assert url == "https://custom.anthropic.com"


def test_credentials_resolution_sanitizes_errors_without_exposing_keys(tmp_path: Path) -> None:
    manager = ConfigManager(
        config_path=tmp_path / "config.json",
        credential_store=FileCredentialStore(path=tmp_path / "creds.json"),
    )
    with pytest.raises(ValueError) as excinfo:
        manager.resolve_credentials(model="nonexistent-provider:nonexistent-model")
    err_msg = str(excinfo.value)
    assert "sk-" not in err_msg
    assert "token" not in err_msg.lower()
