import base64
import json

import pytest

from strix.config.config import Config, resolve_llm_config


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(data: dict[str, object]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{encode(header)}.{encode(payload)}.signature"


def test_config_get_accepts_strix_openai_auth_type_alias(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_AUTH_TYPE", raising=False)
    monkeypatch.setenv("STRIX_OPENAI_AUTH_TYPE", "oauth")

    assert Config.get("openai_auth_type") == "oauth"


def test_resolve_llm_config_does_not_auto_use_codex_auth_cache(monkeypatch, tmp_path) -> None:
    auth_dir = tmp_path / ".codex"
    auth_dir.mkdir()
    (auth_dir / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": _jwt({"scp": ["openid", "api.connectors.invoke"]}),
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("strix.config.config.Path.home", lambda: tmp_path)
    monkeypatch.setenv("STRIX_LLM", "openai/gpt-5.4")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_AUTH_TYPE", raising=False)
    monkeypatch.delenv("STRIX_OPENAI_AUTH_TYPE", raising=False)

    _, api_key, _, _ = resolve_llm_config()

    assert api_key is None


def test_resolve_llm_config_rejects_session_tokens_without_model_request(monkeypatch) -> None:
    monkeypatch.setenv("STRIX_LLM", "openai/gpt-5.4")
    monkeypatch.setenv("OPENAI_SESSION_TOKEN", _jwt({"scp": ["openid", "api.connectors.invoke"]}))
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValueError, match="model.request"):
        resolve_llm_config()


def test_resolve_llm_config_rejects_codex_oauth_tokens_without_model_request(
    monkeypatch, tmp_path
) -> None:
    auth_dir = tmp_path / ".codex"
    auth_dir.mkdir()
    (auth_dir / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": _jwt({"scp": ["openid", "api.connectors.read"]}),
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("strix.config.config.Path.home", lambda: tmp_path)
    monkeypatch.setenv("STRIX_LLM", "openai/gpt-5.4")
    monkeypatch.setenv("STRIX_OPENAI_AUTH_TYPE", "oauth")
    monkeypatch.delenv("OPENAI_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Codex login tokens cannot be used"):
        resolve_llm_config()


def test_resolve_llm_config_injects_dummy_key_for_local_openai_compatible_proxy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRIX_LLM", "gpt-5.4")
    monkeypatch.setenv("LLM_API_BASE", "http://127.0.0.1:10531/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_AUTH_TYPE", raising=False)
    monkeypatch.delenv("STRIX_OPENAI_AUTH_TYPE", raising=False)

    _, api_key, api_base, _ = resolve_llm_config()

    assert api_key == "strix-local-proxy"
    assert api_base == "http://127.0.0.1:10531/v1"
