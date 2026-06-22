"""Tests for the runtime provider toggle + API USD budget.

Covers:
  - settings_store: defaults, update, spend accounting, reset, budget_remaining
  - claude_cli.complete provider dispatch: cli vs api, no-key fallback,
    budget-exhausted fallback, and API cost accounting
  - /api/settings router: GET / PUT / reset-spend, validation, auth gating
"""
import asyncio
import importlib
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Point settings_store at a throwaway file and reload it fresh."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", str(tmp_path / "settings.local.json"))
    import app.settings_store as ss
    importlib.reload(ss)
    return ss


# ---------------------------------------------------------------------------
# settings_store
# ---------------------------------------------------------------------------

def test_defaults_to_cli_provider(store):
    s = store.get_settings()
    assert s["provider"] == "cli"
    assert s["api_usd_spent"] == 0.0


def test_update_and_spend_accounting(store):
    store.update_settings(provider="api", api_usd_budget=2.0)
    store.add_spend(0.5)
    store.add_spend(-1.0)  # ignored
    s = store.get_settings()
    assert s["provider"] == "api"
    assert s["api_usd_spent"] == 0.5
    assert store.budget_remaining(s) == 1.5


def test_reset_spend(store):
    store.update_settings(provider="api", api_usd_budget=1.0)
    store.add_spend(0.9)
    store.reset_spend()
    assert store.get_settings()["api_usd_spent"] == 0.0


def test_invalid_provider_coerced_to_cli(store):
    store.update_settings(provider="bogus")
    assert store.get_settings()["provider"] == "cli"


# ---------------------------------------------------------------------------
# claude_cli provider dispatch
# ---------------------------------------------------------------------------

def _reload_cli(store):
    import app.claude_cli as cc
    importlib.reload(cc)
    return cc


@pytest.mark.parametrize(
    "provider,budget,has_key,expected",
    [
        ("cli", 2.0, True, "CLI"),
        ("api", 2.0, False, "CLI"),   # no key -> fall back
        ("api", 0.0, True, "CLI"),    # budget exhausted -> fall back
        ("api", 2.0, True, "API"),    # selected, keyed, under budget
    ],
)
def test_complete_provider_selection(store, provider, budget, has_key, expected):
    cc = _reload_cli(store)
    store.update_settings(provider=provider, api_usd_budget=budget)

    async def fake_cli(s, u, m=None):
        return "CLI"

    async def fake_api(s, u, m):
        return ("API", 0.01)

    env = {"ANTHROPIC_API_KEY": "sk-test"} if has_key else {}
    with patch.dict(os.environ, env, clear=False):
        if not has_key:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        with patch.object(cc, "_cli_complete", side_effect=fake_cli), \
             patch.object(cc, "_api_complete", side_effect=fake_api):
            out = asyncio.run(cc.complete("s", "u", "claude-haiku-4-5"))
    assert out == expected


def test_api_path_records_spend(store):
    cc = _reload_cli(store)
    store.update_settings(provider="api", api_usd_budget=5.0)

    async def fake_api(s, u, m):
        return ("RESULT", 0.0035)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
        with patch.object(cc, "_api_complete", side_effect=fake_api):
            out = asyncio.run(cc.complete("s", "u", "claude-haiku-4-5"))
    assert out == "RESULT"
    assert abs(store.get_settings()["api_usd_spent"] - 0.0035) < 1e-9


def test_api_cost_uses_model_pricing(store):
    cc = _reload_cli(store)
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    # haiku $1/$5, sonnet $3/$15
    assert abs(cc._api_cost_usd("claude-haiku-4-5", usage) - 6.0) < 1e-9
    assert abs(cc._api_cost_usd("claude-sonnet-4-6", usage) - 18.0) < 1e-9


def test_api_failure_falls_back_to_cli(store):
    import httpx

    cc = _reload_cli(store)
    store.update_settings(provider="api", api_usd_budget=5.0)

    async def boom(s, u, m):
        raise httpx.ConnectError("network down")

    async def fake_cli(s, u, m=None):
        return "CLI"

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
        with patch.object(cc, "_api_complete", side_effect=boom), \
             patch.object(cc, "_cli_complete", side_effect=fake_cli):
            out = asyncio.run(cc.complete("s", "u", "claude-haiku-4-5"))
    assert out == "CLI"


# ---------------------------------------------------------------------------
# /api/settings router
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_client(store):
    from fastapi.testclient import TestClient

    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.main import app

    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    return tc


def test_get_settings_endpoint(api_client):
    r = api_client.get("/api/settings")
    assert r.status_code == 200
    d = r.json()
    assert d["provider"] == "cli"
    assert "api_usd_remaining" in d and "api_key_present" in d


def test_put_settings_endpoint(api_client):
    r = api_client.put("/api/settings", json={"provider": "api", "api_usd_budget": 10})
    assert r.status_code == 200
    d = r.json()
    assert d["provider"] == "api" and d["api_usd_budget"] == 10.0
    assert d["api_usd_remaining"] == 10.0


def test_put_settings_validation(api_client):
    assert api_client.put("/api/settings", json={"provider": "bogus"}).status_code == 422
    assert api_client.put("/api/settings", json={"api_usd_budget": -1}).status_code == 422


def test_reset_spend_endpoint(api_client):
    r = api_client.post("/api/settings/reset-spend")
    assert r.status_code == 200
    assert r.json()["api_usd_spent"] == 0.0


def test_settings_requires_auth(store):
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/api/settings", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")
