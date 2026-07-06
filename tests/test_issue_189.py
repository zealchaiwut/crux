"""Tests for Groq as a switchable LLM provider (issue #189).

Covers:
  - Provider factory: each CRUX_LLM_PROVIDER value → correct provider class
  - GroqProvider: model resolution (bulk vs judgment)
  - GroqProvider: HTTP call shape, headers, response parsing, fence stripping
  - Fast-fail: GROQ_API_KEY missing when CRUX_LLM_PROVIDER=groq → sys.exit(1)
  - Fast-fail: unknown CRUX_LLM_PROVIDER value → sys.exit(1)
  - Routing: claude_cli.complete() routes through GroqProvider when configured
  - Backward compat: unset CRUX_LLM_PROVIDER falls through to settings_store logic
"""
import asyncio
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Provider factory — each CRUX_LLM_PROVIDER value maps to correct class
# ---------------------------------------------------------------------------

def test_factory_groq_returns_groq_provider(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    import app.llm_providers as lp
    importlib.reload(lp)
    provider = lp.get_provider()
    assert isinstance(provider, lp.GroqProvider)


def test_factory_anthropic_api_returns_anthropic_provider(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "anthropic_api")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.llm_providers as lp
    importlib.reload(lp)
    from app.claude_cli import AnthropicAPIProvider
    provider = lp.get_provider()
    assert isinstance(provider, AnthropicAPIProvider)


def test_factory_claude_cli_returns_cli_provider(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "claude_cli")
    import app.llm_providers as lp
    importlib.reload(lp)
    from app.claude_cli import ClaudeCLIProvider
    provider = lp.get_provider()
    assert isinstance(provider, ClaudeCLIProvider)


def test_factory_unset_returns_none(monkeypatch):
    monkeypatch.delenv("CRUX_LLM_PROVIDER", raising=False)
    import app.llm_providers as lp
    importlib.reload(lp)
    assert lp.get_provider() is None


def test_factory_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "openai")
    import app.llm_providers as lp
    importlib.reload(lp)
    with pytest.raises(ValueError, match="openai"):
        lp.get_provider()


# ---------------------------------------------------------------------------
# GroqProvider — model resolution
# ---------------------------------------------------------------------------

@pytest.fixture
def groq_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
    # Isolate settings store so _check_budget() never reads a stale on-disk file.
    monkeypatch.setenv("CRUX_SETTINGS_FILE", str(tmp_path / "settings.local.json"))
    import app.settings_store as ss
    importlib.reload(ss)
    import app.llm_providers as lp
    importlib.reload(lp)
    return lp.GroqProvider()


def test_haiku_maps_to_bulk_model(groq_provider):
    assert groq_provider._resolve_model("claude-haiku-4-5-20251001") == "llama-3.1-8b-instant"


def test_sonnet_maps_to_judgment_model(groq_provider):
    assert groq_provider._resolve_model("claude-sonnet-4-6") == "openai/gpt-oss-120b"


def test_opus_maps_to_judgment_model(groq_provider):
    assert groq_provider._resolve_model("claude-opus-4-8") == "openai/gpt-oss-120b"


def test_none_model_maps_to_bulk(groq_provider):
    assert groq_provider._resolve_model(None) == "llama-3.1-8b-instant"


def test_custom_judgment_model_env_var(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    import app.llm_providers as lp
    importlib.reload(lp)
    p = lp.GroqProvider()
    assert p._resolve_model("claude-sonnet-4-6") == "llama-3.3-70b-versatile"


def test_custom_bulk_model_env_var(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "gemma2-9b-it")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
    import app.llm_providers as lp
    importlib.reload(lp)
    p = lp.GroqProvider()
    assert p._resolve_model("claude-haiku-4-5") == "gemma2-9b-it"


# ---------------------------------------------------------------------------
# GroqProvider — HTTP call mechanics
# ---------------------------------------------------------------------------

def test_groq_complete_uses_bulk_model_for_haiku(groq_provider):
    with patch.object(groq_provider, "_post", new_callable=AsyncMock, return_value=("ok", {})) as mock:
        asyncio.run(groq_provider.complete("sys", "user", "claude-haiku-4-5-20251001"))
    assert mock.call_args[0][0] == "llama-3.1-8b-instant"


def test_groq_complete_uses_judgment_model_for_sonnet(groq_provider):
    with patch.object(groq_provider, "_post", new_callable=AsyncMock, return_value=("ok", {})) as mock:
        asyncio.run(groq_provider.complete("sys", "user", "claude-sonnet-4-6"))
    assert mock.call_args[0][0] == "openai/gpt-oss-120b"


def test_groq_complete_includes_system_and_user_messages(groq_provider):
    with patch.object(groq_provider, "_post", new_callable=AsyncMock, return_value=("ok", {})) as mock:
        asyncio.run(groq_provider.complete("my system", "my user", None))
    messages = mock.call_args[0][1]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles
    contents = {m["role"]: m["content"] for m in messages}
    assert contents["system"] == "my system"
    assert contents["user"] == "my user"


def test_groq_complete_omits_system_when_empty(groq_provider):
    with patch.object(groq_provider, "_post", new_callable=AsyncMock, return_value=("ok", {})) as mock:
        asyncio.run(groq_provider.complete("", "user only", None))
    messages = mock.call_args[0][1]
    roles = [m["role"] for m in messages]
    assert "system" not in roles


def test_groq_complete_strips_code_fences(groq_provider):
    with patch.object(groq_provider, "_post", new_callable=AsyncMock, return_value=('```json\n{"k": 1}\n```', {})):
        result = asyncio.run(groq_provider.complete("s", "u", None))
    assert result == '{"k": 1}'


def test_groq_complete_sync_uses_bulk_model(groq_provider):
    with patch.object(groq_provider, "_post_sync", return_value=("ok", {})) as mock:
        groq_provider.complete_sync("sys", "user", "claude-haiku-4-5-20251001")
    assert mock.call_args[0][0] == "llama-3.1-8b-instant"


def test_groq_post_sends_to_groq_url(groq_provider):
    """_post() makes an HTTP POST to the Groq completions endpoint."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockCls.return_value = mock_client

        result = asyncio.run(groq_provider._post("llama-3.1-8b-instant", [{"role": "user", "content": "hi"}]))

    assert result[0] == "hello"
    call_url = mock_client.post.call_args[0][0]
    assert "api.groq.com" in call_url
    assert "/chat/completions" in call_url


def test_groq_post_sends_api_key_header(groq_provider):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockCls.return_value = mock_client

        asyncio.run(groq_provider._post("llama-3.1-8b-instant", []))

    headers = mock_client.post.call_args[1]["headers"]
    assert headers.get("Authorization") == "Bearer gsk-test"


# ---------------------------------------------------------------------------
# Fast-fail validation
# ---------------------------------------------------------------------------

def test_validate_groq_key_missing_exits_with_1():
    from app.config import _validate_llm_provider_config
    with pytest.raises(SystemExit) as exc:
        _validate_llm_provider_config(provider="groq", groq_key="")
    assert exc.value.code == 1


def test_validate_unknown_provider_exits_with_1():
    from app.config import _validate_llm_provider_config
    with pytest.raises(SystemExit) as exc:
        _validate_llm_provider_config(provider="openai", groq_key="")
    assert exc.value.code == 1


def test_validate_valid_providers_do_not_exit():
    from app.config import _validate_llm_provider_config
    for p in ("", "claude_cli", "anthropic_api"):
        _validate_llm_provider_config(provider=p, groq_key="")  # must not raise
    _validate_llm_provider_config(provider="groq", groq_key="gsk-test")  # must not raise


def test_validate_groq_with_key_does_not_exit():
    from app.config import _validate_llm_provider_config
    _validate_llm_provider_config(provider="groq", groq_key="gsk-valid")  # must not raise


# ---------------------------------------------------------------------------
# claude_cli.complete() routing
# ---------------------------------------------------------------------------

def test_complete_routes_to_groq_when_provider_set(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    import app.llm_providers as lp
    import app.claude_cli as cc
    importlib.reload(lp)
    importlib.reload(cc)

    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value="groq_result")

    with patch.object(lp, "get_provider", return_value=mock_provider):
        result = asyncio.run(cc.complete("sys", "user", "claude-haiku-4-5"))

    assert result == "groq_result"
    mock_provider.complete.assert_called_once_with("sys", "user", "claude-haiku-4-5")


def test_complete_falls_through_to_cli_when_no_provider(monkeypatch):
    monkeypatch.delenv("CRUX_LLM_PROVIDER", raising=False)
    import app.llm_providers as lp
    import app.claude_cli as cc
    importlib.reload(lp)
    importlib.reload(cc)

    async def fake_cli(s, u, m=None):
        return "cli_result"

    with patch.object(lp, "get_provider", return_value=None):
        with patch.object(cc, "_cli_complete", side_effect=fake_cli):
            result = asyncio.run(cc.complete("sys", "user", "claude-haiku-4-5"))

    assert result == "cli_result"


def test_complete_sync_routes_to_groq_when_provider_set(monkeypatch):
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    import app.llm_providers as lp
    import app.claude_cli as cc
    importlib.reload(lp)
    importlib.reload(cc)

    mock_provider = MagicMock()
    mock_provider.complete_sync = MagicMock(return_value="groq_sync_result")

    with patch.object(lp, "get_provider", return_value=mock_provider):
        result = cc.complete_sync("sys", "user", "claude-haiku-4-5")

    assert result == "groq_sync_result"
    mock_provider.complete_sync.assert_called_once_with("sys", "user", "claude-haiku-4-5")
