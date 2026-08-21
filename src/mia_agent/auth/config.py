"""Configuration manager resolving settings across CLI flags, ENV, config files, and credential store."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from mia_agent.auth.credentials import FileCredentialStore


class MiaConfig(BaseModel):
    """User preferences and default model configuration."""

    default_provider: str = "opencode-go"
    default_model: str = "mimo-v2.5"
    base_urls: dict[str, str] = Field(default_factory=dict)
    max_steps_per_turn: int = 25
    temperature: float = 0.7
    compaction_threshold_ratio: float = 0.8
    context_window_tokens: int = 128_000
    keep_recent_tokens: int = 16_000


def default_config_path() -> Path:
    return Path.home() / ".mia" / "config.json"


# Mapping from common model prefixes to provider names
MODEL_PROVIDER_PREFIXES = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "deepseek": "deepseek",
    "gemini": "gemini",
    "mimo": "opencode-go",
    "opencode": "opencode-go",
    "mock": "mock",
}

# Environment variable mappings for API keys
ENV_API_KEY_MAP = {
    "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "opencode-go": ["OPENCODE_GO_API_KEY", "MIMO_API_KEY", "OPENCODE_API_KEY"],
    "mimo": ["MIMO_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"],
}

# Standard Base URLs for known providers
DEFAULT_PROVIDER_BASE_URLS = {
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "opencode-go": "https://opencode.ai/zen/go/v1",
    "mimo": "https://opencode.ai/zen/go/v1",
}


def load_dotenv(dotenv_path: Path | None = None) -> None:
    """Lightweight .env loader into os.environ without third-party dependencies."""
    target = dotenv_path or Path.cwd() / ".env"
    if not target.exists():
        return
    try:
        with open(target, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


class ConfigManager:
    """Manages Mia settings and resolves credentials hierarchically."""

    def __init__(
        self,
        config_path: Path | None = None,
        credential_store: FileCredentialStore | None = None,
    ) -> None:
        load_dotenv()
        self.config_path = config_path or default_config_path()
        self.credential_store = credential_store or FileCredentialStore()
        self._config: MiaConfig = self._load_config()

    def _load_config(self) -> MiaConfig:
        if not self.config_path.exists():
            return MiaConfig()
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
                return MiaConfig.model_validate(data)
        except Exception:
            return MiaConfig()

    def save_config(self, config: MiaConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)
        self._config = config

    @property
    def config(self) -> MiaConfig:
        return self._config

    def infer_provider(self, model: str) -> str:
        """Infer provider name from model name prefix."""
        lower = model.lower()
        for prefix, provider in MODEL_PROVIDER_PREFIXES.items():
            if lower.startswith(prefix):
                return provider
        return self._config.default_provider

    def resolve_credentials(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> tuple[str, str, str | None, str | None]:
        """Resolve (provider, model, api_key, base_url) through the configuration hierarchy."""
        # 1. Resolve Model
        resolved_model = model or os.environ.get("MIA_MODEL") or self._config.default_model

        # 2. Resolve Provider
        resolved_provider = provider or self.infer_provider(resolved_model)

        # 3. Resolve Base URL
        resolved_base_url = (
            base_url
            or os.environ.get(f"{resolved_provider.upper()}_BASE_URL")
            or self._config.base_urls.get(resolved_provider)
            or DEFAULT_PROVIDER_BASE_URLS.get(resolved_provider)
        )

        # 4. Resolve API Key
        resolved_api_key = api_key
        if not resolved_api_key:
            # Check environment variables
            env_vars = ENV_API_KEY_MAP.get(
                resolved_provider, [f"{resolved_provider.upper()}_API_KEY"]
            )
            for var in env_vars:
                val = os.environ.get(var)
                if val:
                    resolved_api_key = val
                    break

        if not resolved_api_key:
            # Check stored credentials
            resolved_api_key = self.credential_store.get_api_key(resolved_provider)

        return resolved_provider, resolved_model, resolved_api_key, resolved_base_url
