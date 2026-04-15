import contextlib
import json
import os
from base64 import urlsafe_b64decode
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


STRIX_API_BASE = "https://models.strix.ai/api/v1"


class Config:
    """Configuration Manager for Strix."""

    _ENV_ALIASES = {
        "openai_auth_type": ("STRIX_OPENAI_AUTH_TYPE",),
    }

    # LLM Configuration
    strix_llm = None
    llm_api_key = None
    openai_session_token = None
    openai_auth_type = "api_key"
    llm_api_base = None
    openai_api_base = None
    litellm_base_url = None
    ollama_api_base = None
    strix_reasoning_effort = "high"
    strix_llm_max_retries = "5"
    strix_memory_compressor_timeout = "30"
    llm_timeout = "300"
    _LLM_CANONICAL_NAMES = (
        "strix_llm",
        "llm_api_key",
        "openai_session_token",
        "openai_auth_type",
        "llm_api_base",
        "openai_api_base",
        "litellm_base_url",
        "ollama_api_base",
        "strix_reasoning_effort",
        "strix_llm_max_retries",
        "strix_memory_compressor_timeout",
        "llm_timeout",
    )

    # Tool & Feature Configuration
    perplexity_api_key = None
    strix_disable_browser = "false"

    # Runtime Configuration
    strix_image = "ghcr.io/usestrix/strix-sandbox:0.1.13"
    strix_runtime_backend = "docker"
    strix_sandbox_execution_timeout = "120"
    strix_sandbox_connect_timeout = "10"

    # Telemetry
    strix_telemetry = "1"
    strix_otel_telemetry = None
    strix_posthog_telemetry = None
    traceloop_base_url = None
    traceloop_api_key = None
    traceloop_headers = None

    # Config file override (set via --config CLI arg)
    _config_file_override: Path | None = None

    @classmethod
    def _tracked_names(cls) -> list[str]:
        return [
            k
            for k, v in vars(cls).items()
            if not k.startswith("_") and k[0].islower() and (v is None or isinstance(v, str))
        ]

    @classmethod
    def tracked_vars(cls) -> list[str]:
        return [name.upper() for name in cls._tracked_names()]

    @classmethod
    def _llm_env_vars(cls) -> set[str]:
        return {name.upper() for name in cls._LLM_CANONICAL_NAMES}

    @classmethod
    def _llm_env_changed(cls, saved_env: dict[str, Any]) -> bool:
        for var_name in cls._llm_env_vars():
            current = os.getenv(var_name)
            if current is None:
                continue
            if saved_env.get(var_name) != current:
                return True
        return False

    @classmethod
    def get(cls, name: str) -> str | None:
        env_name = name.upper()
        default = getattr(cls, name, None)
        value = os.getenv(env_name)
        if value is not None:
            return value

        for alias in cls._ENV_ALIASES.get(name, ()):
            alias_value = os.getenv(alias)
            if alias_value is not None:
                return alias_value

        return default

    @classmethod
    def config_dir(cls) -> Path:
        return Path.home() / ".strix"

    @classmethod
    def config_file(cls) -> Path:
        if cls._config_file_override is not None:
            return cls._config_file_override
        return cls.config_dir() / "cli-config.json"

    @classmethod
    def load(cls) -> dict[str, Any]:
        path = cls.config_file()
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                return data
        except (json.JSONDecodeError, OSError):
            return {}

    @classmethod
    def save(cls, config: dict[str, Any]) -> bool:
        try:
            cls.config_dir().mkdir(parents=True, exist_ok=True)
            config_path = cls.config_dir() / "cli-config.json"
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except OSError:
            return False
        with contextlib.suppress(OSError):
            config_path.chmod(0o600)  # may fail on Windows
        return True

    @classmethod
    def apply_saved(cls, force: bool = False) -> dict[str, str]:
        saved = cls.load()
        env_vars = saved.get("env", {})
        if not isinstance(env_vars, dict):
            env_vars = {}
        cleared_vars = {
            var_name
            for var_name in cls.tracked_vars()
            if var_name in os.environ and os.environ.get(var_name) == ""
        }
        if cleared_vars:
            for var_name in cleared_vars:
                env_vars.pop(var_name, None)
            if cls._config_file_override is None:
                cls.save({"env": env_vars})
        if cls._llm_env_changed(env_vars):
            for var_name in cls._llm_env_vars():
                env_vars.pop(var_name, None)
            if cls._config_file_override is None:
                cls.save({"env": env_vars})
        applied = {}

        for var_name, var_value in env_vars.items():
            if var_name in cls.tracked_vars() and (force or var_name not in os.environ):
                os.environ[var_name] = var_value
                applied[var_name] = var_value

        return applied

    @classmethod
    def capture_current(cls) -> dict[str, Any]:
        env_vars = {}
        for var_name in cls.tracked_vars():
            value = os.getenv(var_name)
            if value:
                env_vars[var_name] = value
        return {"env": env_vars}

    @classmethod
    def save_current(cls) -> bool:
        existing = cls.load().get("env", {})
        merged = dict(existing)

        for var_name in cls.tracked_vars():
            value = os.getenv(var_name)
            if value is None:
                pass
            elif value == "":
                merged.pop(var_name, None)
            else:
                merged[var_name] = value

        return cls.save({"env": merged})


def apply_saved_config(force: bool = False) -> dict[str, str]:
    return Config.apply_saved(force=force)


def save_current_config() -> bool:
    return Config.save_current()


def _get_codex_auth_data() -> dict[str, str | None]:
    """Try to read the auth data from ~/.codex/auth.json."""
    auth_path = Path.home() / ".codex" / "auth.json"
    result = {"access_token": None, "organization": None, "project": None}
    if not auth_path.exists():
        return result
    try:
        with auth_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            # Access Token
            token = data.get("access_token")
            if not token and "tokens" in data:
                token = data["tokens"].get("access_token")
            result["access_token"] = token

            # Organization and Project IDs (often needed for subscription scopes)
            result["organization"] = data.get("organization_id") or data.get("org_id")
            result["project"] = data.get("project_id")
            return result
    except (json.JSONDecodeError, OSError):
        return result


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying the signature."""
    if token.count(".") != 2:
        return {}

    try:
        _, payload, _ = token.split(".")
        payload += "=" * (-len(payload) % 4)
        return json.loads(urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}


def _get_openai_token_scopes(token: str | None) -> set[str]:
    if not token:
        return set()

    payload = _decode_jwt_payload(token)
    scopes = payload.get("scp") or payload.get("scope") or []

    if isinstance(scopes, str):
        return {scope for scope in scopes.split() if scope}
    if isinstance(scopes, list):
        return {str(scope) for scope in scopes if scope}
    return set()


def _validate_openai_session_token(token: str, source: str) -> None:
    scopes = _get_openai_token_scopes(token)
    if scopes and "model.request" not in scopes:
        raise ValueError(
            f"The OpenAI session token from {source} does not include the 'model.request' scope. "
            "Codex login tokens cannot be used for LiteLLM/OpenAI API requests. "
            "Set LLM_API_KEY to a real OpenAI API key instead, or use a local Codex-compatible proxy "
            "such as openai-oauth via LLM_API_BASE."
        )


def _looks_like_openai_model(model: str) -> bool:
    if "/" not in model:
        return True
    return model.startswith("openai/")


def _is_local_openai_compatible_base(api_base: str | None, model: str) -> bool:
    if not api_base or not _looks_like_openai_model(model):
        return False

    parsed = urlparse(api_base)
    hostname = (parsed.hostname or "").lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def resolve_llm_config() -> tuple[str | None, str | None, str | None, dict[str, str]]:
    """Resolve LLM model, api_key, api_base and extra headers.

    Returns:
        tuple: (model_name, api_key, api_base, extra_headers)
        - model_name: Original model name (strix/ prefix preserved for display)
        - api_key: LLM API key or session token
        - api_base: API base URL (auto-set to STRIX_API_BASE for strix/ models)
        - extra_headers: Additional HTTP headers (e.g., OpenAI-Project)
    """
    model = Config.get("strix_llm")
    if not model:
        return None, None, None, {}

    api_key = Config.get("llm_api_key")
    auth_type = (Config.get("openai_auth_type") or "api_key").strip().lower()
    session_token = Config.get("openai_session_token")
    extra_headers = {}

    if not api_key and session_token:
        _validate_openai_session_token(session_token, "OPENAI_SESSION_TOKEN")
        api_key = session_token

    # Explicit OAuth mode reads the Codex auth cache, but only if requested.
    if auth_type == "oauth" and not api_key:
        auth_data = _get_codex_auth_data()
        session_token = auth_data["access_token"]

        if session_token:
            _validate_openai_session_token(session_token, "~/.codex/auth.json")
            api_key = session_token
            if auth_data["organization"]:
                extra_headers["OpenAI-Organization"] = auth_data["organization"]
            if auth_data["project"]:
                extra_headers["OpenAI-Project"] = auth_data["project"]

    if model.startswith("strix/"):
        api_base: str | None = STRIX_API_BASE
    else:
        api_base = (
            Config.get("llm_api_base")
            or Config.get("openai_api_base")
            or Config.get("litellm_base_url")
            or Config.get("ollama_api_base")
        )

    # LiteLLM's OpenAI path still constructs an OpenAI client that requires an api_key
    # argument even when talking to a local OpenAI-compatible proxy that ignores auth.
    if not api_key and _is_local_openai_compatible_base(api_base, model):
        api_key = "strix-local-proxy"

    return model, api_key, api_base, extra_headers
