"""Tests for issue #195: Per-stage Groq spend attached to run report (settings API).

The issue identified that _record_spend() only emits a Python logger line; the
structured run-report (the /api/settings endpoint) never surfaces groq_usd_spent
so callers have no programmatic way to observe Groq spend alongside Anthropic spend.

AC derived from the issue body:
  AC1 — GET /api/settings response includes groq_usd_spent field (default 0.0)
  AC2 — groq_usd_spent in the response reflects spend accumulated via add_groq_spend()
  AC3 — POST /api/settings/reset-spend zeroes groq_usd_spent in the response
  AC4 — _record_spend() returns the per-stage spend dict {tokens_in, tokens_out, usd}
         so callers that need structured detail can capture it without parsing the log
"""
import importlib
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isolated settings store backed by a throwaway file."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", str(tmp_path / "settings.local.json"))
    import app.settings_store as ss
    importlib.reload(ss)
    return ss


@pytest.fixture()
def api_client(store):
    from fastapi.testclient import TestClient

    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.main import app

    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    return tc


@pytest.fixture()
def groq_provider(store, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    import app.llm_providers as lp
    importlib.reload(lp)
    return lp.GroqProvider()


# ---------------------------------------------------------------------------
# AC1: GET /api/settings response includes groq_usd_spent (default 0.0)
# ---------------------------------------------------------------------------

def test_settings_endpoint_exposes_groq_usd_spent_field(api_client):
    """AC1: /api/settings response body contains groq_usd_spent key."""
    r = api_client.get("/api/settings")
    assert r.status_code == 200
    assert "groq_usd_spent" in r.json()


def test_settings_endpoint_groq_usd_spent_defaults_to_zero(api_client):
    """AC1: groq_usd_spent is 0.0 on a fresh store."""
    r = api_client.get("/api/settings")
    assert r.json()["groq_usd_spent"] == 0.0


# ---------------------------------------------------------------------------
# AC2: groq_usd_spent reflects accumulated spend
# ---------------------------------------------------------------------------

def test_settings_endpoint_reflects_groq_spend(api_client, store):
    """AC2: groq_usd_spent in the response matches what was added via add_groq_spend()."""
    store.add_groq_spend(0.00123)
    r = api_client.get("/api/settings")
    assert r.status_code == 200
    assert abs(r.json()["groq_usd_spent"] - 0.00123) < 1e-9


def test_settings_endpoint_groq_spend_accumulates(api_client, store):
    """AC2: multiple add_groq_spend() calls accumulate correctly in the response."""
    store.add_groq_spend(0.001)
    store.add_groq_spend(0.002)
    r = api_client.get("/api/settings")
    assert abs(r.json()["groq_usd_spent"] - 0.003) < 1e-9


# ---------------------------------------------------------------------------
# AC3: reset-spend zeroes groq_usd_spent in the response
# ---------------------------------------------------------------------------

def test_reset_spend_zeroes_groq_usd_spent_in_response(api_client, store):
    """AC3: POST /api/settings/reset-spend resets groq_usd_spent to 0.0."""
    store.add_groq_spend(0.05)
    r = api_client.post("/api/settings/reset-spend")
    assert r.status_code == 200
    assert r.json()["groq_usd_spent"] == 0.0


def test_put_settings_response_also_includes_groq_usd_spent(api_client, store):
    """AC3: PUT /api/settings response also exposes groq_usd_spent."""
    store.add_groq_spend(0.007)
    r = api_client.put("/api/settings", json={"api_usd_budget": 5.0})
    assert r.status_code == 200
    assert abs(r.json()["groq_usd_spent"] - 0.007) < 1e-9


# ---------------------------------------------------------------------------
# AC4: _record_spend() returns structured per-stage dict
# ---------------------------------------------------------------------------

def test_record_spend_returns_structured_dict(groq_provider, store, monkeypatch):
    """AC4: _record_spend() returns {tokens_in, tokens_out, usd} for the caller."""
    store.update_settings(
        groq_rates={"llama-3.1-8b-instant": {"input_per_1m": 0.05, "output_per_1m": 0.08}}
    )
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    result = groq_provider._record_spend("llama-3.1-8b-instant", usage)

    assert isinstance(result, dict)
    assert result["tokens_in"] == 1000
    assert result["tokens_out"] == 500
    expected_usd = (1000 / 1_000_000) * 0.05 + (500 / 1_000_000) * 0.08
    assert abs(result["usd"] - expected_usd) < 1e-12


def test_record_spend_dict_keys_present(groq_provider, store, monkeypatch):
    """AC4: returned dict always has tokens_in, tokens_out, and usd keys."""
    store.update_settings(groq_rates={})  # unknown model → usd=0.0
    usage = {"prompt_tokens": 200, "completion_tokens": 100}
    result = groq_provider._record_spend("unknown-model", usage)

    assert "tokens_in" in result
    assert "tokens_out" in result
    assert "usd" in result
    assert result["tokens_in"] == 200
    assert result["tokens_out"] == 100
    assert result["usd"] == 0.0
