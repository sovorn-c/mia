"""Configuration manager backed by Mia's local config and credential store."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from mia_agent.auth.credentials import FileCredentialStore
from mia_agent.auth.openai_auth import OPENAI_CODEX_PROVIDER

PI_CATALOG_BASE_URL = "https://pi.dev/api/models/providers"
PI_CATALOG_PROVIDER_IDS = {"gemini": "google"}


class MiaConfig(BaseModel):
    """User preferences and default model configuration."""

    default_provider: str = ""
    default_model: str = ""
    scoped_models: list[str] = Field(default_factory=list)
    model_catalog: dict[str, list[str]] = Field(default_factory=dict)
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

# Standard Base URLs for known providers
DEFAULT_PROVIDER_BASE_URLS = {
    "anthropic": "https://api.anthropic.com/v1",
    OPENAI_CODEX_PROVIDER: "https://chatgpt.com/backend-api",
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


def _fetch_pi_catalog_models(provider_id: str) -> list[str] | None:
    """Read Pi's current curated, tool-capable catalog for one provider."""
    import httpx

    catalog_provider = PI_CATALOG_PROVIDER_IDS.get(provider_id, provider_id)
    try:
        response = httpx.get(
            f"{PI_CATALOG_BASE_URL}/{catalog_provider}",
            headers={"Accept": "application/json", "User-Agent": "mia"},
            timeout=5.0,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        entries: object = payload.get("models", payload) if isinstance(payload, dict) else payload
        if isinstance(entries, dict):
            entries = list(entries.values())
        if not isinstance(entries, list):
            return None
        models = sorted(
            {
                item["id"]
                for item in entries
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        )
        return models or None
    except Exception:
        return None


def discover_provider_models(
    provider_id: str,
    api_key: str | None = None,
    base_url: str | None = None,
    oauth_access_token: str | None = None,
    account_id: str | None = None,
) -> list[str]:
    """Load Pi's curated catalog, then provider-native models, with a static fallback."""
    import httpx

    if provider_id != "custom" and provider_id != "mock":
        catalog_models = _fetch_pi_catalog_models(provider_id)
        if catalog_models:
            return catalog_models

    if provider_id == OPENAI_CODEX_PROVIDER:
        if oauth_access_token and account_id:
            try:
                response = httpx.get(
                    f"{(base_url or DEFAULT_PROVIDER_BASE_URLS[provider_id]).rstrip('/')}/codex/models",
                    params={"client_version": "0.144.3"},
                    headers={
                        "Authorization": f"Bearer {oauth_access_token}",
                        "chatgpt-account-id": account_id,
                        "originator": "tau",
                        "User-Agent": "tau",
                        "accept": "application/json",
                    },
                    timeout=5.0,
                )
                if response.status_code in {401, 403}:
                    return []
                if response.status_code == 200:
                    payload = response.json()
                    remote_models = [
                        str(item["slug"])
                        for item in payload.get("models", [])
                        if isinstance(item, dict) and isinstance(item.get("slug"), str)
                    ]
                    if remote_models:
                        return sorted(set(remote_models))
            except Exception:
                pass
        return [
            "gpt-5.6",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.3-codex-spark",
            "gpt-5.2",
        ]
    if provider_id == "mock":
        return ["mock-model-1", "mock-model-2"]

    headers: dict[str, str] = {}
    params: dict[str, str | int] = {}
    if provider_id == "gemini":
        # Gemini's native model API is not the OpenAI-compatible /models route.
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        if api_key:
            params["key"] = api_key
        params["pageSize"] = 1000
    else:
        resolved_base_url = (
            base_url or DEFAULT_PROVIDER_BASE_URLS.get(provider_id) or "https://api.openai.com/v1"
        )
        url = f"{resolved_base_url.rstrip('/')}/models"
        if provider_id == "anthropic":
            headers.update({"x-api-key": api_key or "", "anthropic-version": "2023-06-01"})
            params["limit"] = 1000
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    models: list[str] = []
    if not (api_key and api_key.startswith("sk-test-")):
        try:
            response = httpx.get(url, headers=headers, params=params, timeout=3.5)
            if response.status_code in {401, 403} or (
                provider_id == "gemini" and response.status_code == 400
            ):
                return []
            if response.status_code == 200:
                payload = response.json()
                if provider_id == "gemini":
                    models = [
                        str(item["name"]).removeprefix("models/")
                        for item in payload.get("models", [])
                        if isinstance(item, dict)
                        and isinstance(item.get("name"), str)
                        and "generateContent" in item.get("supportedGenerationMethods", [])
                    ]
                elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    models = [
                        str(item["id"])
                        for item in payload["data"]
                        if isinstance(item, dict) and isinstance(item.get("id"), str)
                    ]
                elif isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict) and isinstance(item.get("id"), str):
                            models.append(item["id"])
        except Exception:
            pass

    if models:
        return sorted(set(models))

    # Offline fallback. Refreshable providers should normally use their live endpoint.
    fallback_presets: dict[str, list[str]] = {
        "opencode-go": ["mimo-v2.5", "qwen2.5-coder-32b-instruct", "deepseek-v3"],
        "openrouter": [
            "anthropic/claude-3.7-sonnet",
            "deepseek/deepseek-r1",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "openai": ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-4o", "gpt-4o-mini"],
        "anthropic": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"],
        "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
    }
    return fallback_presets.get(provider_id, [])


class ConfigManager:
    """Manages Mia settings and resolves credentials hierarchically."""

    def __init__(
        self,
        config_path: Path | None = None,
        credential_store: FileCredentialStore | None = None,
    ) -> None:
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
        """Infer provider, preserving an explicitly selected default model route."""
        if not model:
            return self._config.default_provider or ""
        if model == self._config.default_model and self._config.default_provider:
            return self._config.default_provider
        for scoped in self._config.scoped_models:
            provider, separator, scoped_model = scoped.partition("::")
            if separator and scoped_model == model and provider:
                return provider
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
        """Resolve provider settings strictly from Mia's local files and arguments."""
        resolved_model = model or self._config.default_model
        resolved_provider = provider or self.infer_provider(resolved_model)
        if not resolved_provider:
            raise ValueError(f"Could not resolve provider for model '{resolved_model}'")

        resolved_base_url = (
            base_url
            or self._config.base_urls.get(resolved_provider)
            or DEFAULT_PROVIDER_BASE_URLS.get(resolved_provider)
        )
        resolved_api_key = api_key or self.credential_store.get_api_key(resolved_provider)
        return resolved_provider, resolved_model, resolved_api_key, resolved_base_url
