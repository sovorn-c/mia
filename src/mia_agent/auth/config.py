"""Configuration manager resolving settings across CLI flags, ENV, config files, and credential store."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from mia_agent.auth.credentials import FileCredentialStore


class MiaConfig(BaseModel):
    """User preferences and default model configuration."""

    default_provider: str = ""
    default_model: str = ""
    scoped_models: list[str] = Field(default_factory=list)
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
    "openrouter": "openrouter",
    "mock": "mock",
}

# Environment variable mappings for API keys
ENV_API_KEY_MAP = {
    "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "opencode-go": ["OPENCODE_GO_API_KEY", "MIMO_API_KEY", "OPENCODE_API_KEY"],
    "mimo": ["MIMO_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"],
}

# Standard Base URLs for known providers
DEFAULT_PROVIDER_BASE_URLS = {
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
    "opencode-go": "https://opencode.ai/zen/go/v1",
    "mimo": "https://opencode.ai/zen/go/v1",
}


def validate_api_key(
    provider_id: str, api_key: str, base_url: str | None = None
) -> tuple[bool, str]:
    """Test API key against the provider with a lightweight 1-token completion probe."""
    import httpx

    # If mock key in offline tests or mock provider
    if api_key.startswith("sk-test-") or provider_id == "mock":
        return True, "Test key accepted"

    resolved_base_url = base_url or DEFAULT_PROVIDER_BASE_URLS.get(
        provider_id, "https://api.openai.com/v1"
    )

    probe_model_map = {
        "opencode-go": "mimo-v2.5",
        "mimo": "mimo-v2.5",
        "openrouter": "openrouter/auto",
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "deepseek": "deepseek-chat",
        "custom": "default",
    }
    probe_model = probe_model_map.get(provider_id, "gpt-4o-mini")

    try:
        if provider_id == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            url = f"{resolved_base_url.rstrip('/')}/messages"
            payload = {
                "model": probe_model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }
            resp = httpx.post(url, headers=headers, json=payload, timeout=6.0)
            if resp.status_code == 200:
                return True, "API Key successfully validated"
            elif resp.status_code in (401, 403):
                return False, f"Invalid API Key (HTTP {resp.status_code} Unauthorized)"
            elif resp.status_code in (400, 404, 429):
                return True, f"Key authenticated (Server status {resp.status_code})"
            return True, f"Endpoint reached (HTTP {resp.status_code})"

        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            url = f"{resolved_base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": probe_model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }
            resp = httpx.post(url, headers=headers, json=payload, timeout=6.0)
            if resp.status_code == 200:
                return True, "API Key successfully validated"
            elif resp.status_code in (401, 403):
                return False, f"Invalid API Key (HTTP {resp.status_code} Unauthorized)"
            elif resp.status_code in (400, 404, 422, 429):
                return True, f"Key authenticated (Server status {resp.status_code})"
            return True, f"Endpoint reached (HTTP {resp.status_code})"

    except httpx.ConnectError:
        return False, f"Connection failed: Could not reach {resolved_base_url}"
    except httpx.TimeoutException:
        return False, f"Timeout: Provider {resolved_base_url} did not respond within 6s"


def discover_provider_models(
    provider_id: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[str]:
    """Dynamically discover available models from provider API endpoint (/models)."""
    import httpx

    # If mock provider
    if provider_id == "mock":
        return ["mock-model-1", "mock-model-2"]

    resolved_base_url = (
        base_url or DEFAULT_PROVIDER_BASE_URLS.get(provider_id) or "https://api.openai.com/v1"
    )

    headers: dict[str, str] = {}
    if api_key:
        if provider_id == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    models: list[str] = []
    # If not a dummy test key, attempt live HTTP fetch
    if not (api_key and api_key.startswith("sk-test-")):
        try:
            url = f"{resolved_base_url.rstrip('/')}/models"
            resp = httpx.get(url, headers=headers, timeout=3.5)
            if resp.status_code == 200:
                payload = resp.json()
                if (
                    isinstance(payload, dict)
                    and "data" in payload
                    and isinstance(payload["data"], list)
                ):
                    models = [
                        item["id"]
                        for item in payload["data"]
                        if isinstance(item, dict) and "id" in item
                    ]
                elif isinstance(payload, list):
                    models = [
                        item["id"] if isinstance(item, dict) and "id" in item else str(item)
                        for item in payload
                    ]
        except Exception:
            pass

    if models:
        # Filter and sort unique models
        return sorted(list(set(models)))

    # Fallback to sensible standard presets if offline or endpoint unlisted
    fallback_presets: dict[str, list[str]] = {
        "opencode-go": ["mimo-v2.5", "qwen2.5-coder-32b-instruct", "deepseek-v3"],
        "openrouter": [
            "anthropic/claude-3.7-sonnet",
            "deepseek/deepseek-r1",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1"],
        "anthropic": [
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ],
        "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    }
    return fallback_presets.get(provider_id, [])


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
        if not model:
            return self._config.default_provider or ""
        lower = model.lower()
        for prefix, provider in MODEL_PROVIDER_PREFIXES.items():
            if lower.startswith(prefix):
                return provider
        return self._config.default_provider or ""

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
