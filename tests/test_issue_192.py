"""Tests for issue #192: Wire Groq token spend into USD budget tracker.

AC coverage:
  AC1 — groq_rates configurable per model in settings
  AC2 — prompt_tokens / completion_tokens → USD after each Groq call
  AC3 — each stage logs groq token spend (tokens in/out + USD cost)
  AC4 — groq USD spend added to budget-guard total; guard trips at combined limit
  AC5 — Tavily / research fetch-budget accounting untouched
  AC6 — unknown Groq model → warning logged, $0 counted, run continues
  AC7 — existing Anthropic/CLI budget tests pass (no modification)
  AC8 — simulated Groq response with known token counts → correct USD deduction
         and guard trips at correct threshold
"""
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isolated settings store backed by a throwaway file."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", str(tmp_path / "settings.local.json"))
    import app.settings_store as ss
    importlib.reload(ss)
    return ss


@pytest.fixture()
def groq_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
    import app.llm_providers as lp
    importlib.reload(lp)
    return lp.GroqProvider()


# ---------------------------------------------------------------------------
# AC1: groq_rates configurable per model in settings
# ---------------------------------------------------------------------------

def test_groq_rates_persist_to_settings_file(store):
    """AC1: groq_rates written via update_settings are returned by get_settings."""
    rates = {"llama3-70b-8192": {"input_per_1m": 0.59, "output_per_1m": 0.79}}
    store.update_settings(groq_rates=rates)
    saved = store.get_settings()
    assert saved["groq_rates"] == rates


def test_groq_rates_default_to_empty_dict(store):
    """AC1: fresh store starts with groq_rates = {}."""
    assert store.get_settings()["groq_rates"] == {}


def test_groq_rates_multi_model(store):
    """AC1: multiple model entries are stored without collision."""
    rates = {
        "model-a": {"input_per_1m": 0.59, "output_per_1m": 0.79},
        "model-b": {"input_per_1m": 0.10, "output_per_1m": 0.20},
    }
    store.update_settings(groq_rates=rates)
    assert store.get_settings()["groq_rates"]["model-a"]["input_per_1m"] == 0.59
    assert store.get_settings()["groq_rates"]["model-b"]["output_per_1m"] == 0.20


# ---------------------------------------------------------------------------
# AC2: prompt_tokens / completion_tokens → USD after each Groq call
# ---------------------------------------------------------------------------

def test_groq_cost_usd_matches_formula(store, groq_provider, monkeypatch):
    """AC2: cost = (prompt/1M * input_rate) + (completion/1M * output_rate)."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)

    rates = {"llama-3.1-8b-instant": {"input_per_1m": 0.05, "output_per_1m": 0.08}}
    store.update_settings(groq_rates=rates)

    usage = {"prompt_tokens": 500_000, "completion_tokens": 200_000}
    cost = groq_provider._groq_cost_usd("llama-3.1-8b-instant", usage)

    expected = (500_000 / 1_000_000) * 0.05 + (200_000 / 1_000_000) * 0.08
    assert abs(cost - expected) < 1e-10


def test_groq_cost_usd_per_stage_with_known_tokens(store, groq_provider, monkeypatch):
    """AC2 / AC8: 500 input + 200 output tokens with known rates → correct USD."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)

    input_rate = 0.59
    output_rate = 0.79
    store.update_settings(
        groq_rates={"llama3-70b-8192": {"input_per_1m": input_rate, "output_per_1m": output_rate}}
    )

    usage = {"prompt_tokens": 500, "completion_tokens": 200}
    cost = groq_provider._groq_cost_usd("llama3-70b-8192", usage)

    expected = (500 / 1_000_000) * input_rate + (200 / 1_000_000) * output_rate
    assert abs(cost - expected) < 1e-12


# ---------------------------------------------------------------------------
# AC3: stage logs tokens in/out + USD cost
# ---------------------------------------------------------------------------

def test_record_spend_logs_token_details(store, groq_provider, monkeypatch, caplog):
    """AC3: _record_spend() emits a log line with model, tokens, and USD."""
    import logging

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    store.update_settings(
        groq_rates={"llama-3.1-8b-instant": {"input_per_1m": 0.05, "output_per_1m": 0.08}}
    )

    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    with caplog.at_level(logging.INFO, logger="app.llm_providers"):
        groq_provider._record_spend("llama-3.1-8b-instant", usage)

    log_text = " ".join(caplog.messages)
    assert "llama-3.1-8b-instant" in log_text
    assert "1000" in log_text
    assert "500" in log_text


# ---------------------------------------------------------------------------
# AC4: groq USD added to budget-guard total; guard trips at combined limit
# ---------------------------------------------------------------------------

def test_groq_usd_spent_default_zero(store):
    """AC4: fresh store has groq_usd_spent = 0.0."""
    assert store.get_settings()["groq_usd_spent"] == 0.0


def test_add_groq_spend_accumulates(store):
    """AC4: add_groq_spend() accumulates correctly."""
    store.add_groq_spend(0.001)
    store.add_groq_spend(0.002)
    assert abs(store.get_settings()["groq_usd_spent"] - 0.003) < 1e-9


def test_budget_remaining_includes_groq_spend(store):
    """AC4: budget_remaining() = budget - (api_spent + groq_spent)."""
    store.update_settings(api_usd_budget=1.0)
    store.add_spend(0.3)        # Anthropic spend
    store.add_groq_spend(0.4)   # Groq spend
    remaining = store.budget_remaining()
    assert abs(remaining - 0.3) < 1e-9


def test_budget_guard_trips_when_combined_spend_hits_limit(store, groq_provider, monkeypatch):
    """AC4: _check_budget() raises GroqBudgetExhaustedError when budget is gone."""
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=0.01)
    store.add_groq_spend(0.01)  # exactly at limit

    with pytest.raises(lp.GroqBudgetExhaustedError):
        provider._check_budget()


def test_budget_guard_includes_anthropic_spend(store, monkeypatch):
    """AC4: guard trips when Anthropic spend alone consumes the budget."""
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=0.01)
    store.add_spend(0.01)  # Anthropic spend fills the budget

    with pytest.raises(lp.GroqBudgetExhaustedError):
        provider._check_budget()


def test_budget_guard_does_not_trip_when_budget_zero(store, monkeypatch):
    """AC4: api_usd_budget=0 means 'no limit'; guard must not trip."""
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=0.0)
    store.add_groq_spend(999.0)  # massive spend — should still not trip

    provider._check_budget()  # must not raise


def test_complete_raises_before_api_call_when_budget_exhausted(store, monkeypatch):
    """AC4: complete() raises GroqBudgetExhaustedError without hitting the API."""
    import asyncio
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=0.001)
    store.add_groq_spend(0.001)

    with patch.object(provider, "_post", new_callable=AsyncMock) as mock_post:
        with pytest.raises(lp.GroqBudgetExhaustedError):
            asyncio.run(provider.complete("sys", "user", None))
    mock_post.assert_not_called()


def test_complete_deducts_groq_spend_after_call(store, monkeypatch):
    """AC4 / AC8: complete() adds Groq cost to groq_usd_spent in settings."""
    import asyncio
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    input_rate, output_rate = 0.05, 0.08
    store.update_settings(
        api_usd_budget=1.0,
        groq_rates={"llama-3.1-8b-instant": {"input_per_1m": input_rate, "output_per_1m": output_rate}},
    )

    usage = {"prompt_tokens": 500, "completion_tokens": 200}
    expected_cost = (500 / 1_000_000) * input_rate + (200 / 1_000_000) * output_rate

    with patch.object(provider, "_post", new_callable=AsyncMock, return_value=("result text", usage)):
        asyncio.run(provider.complete("sys", "user", "claude-haiku-4-5"))

    assert abs(store.get_settings()["groq_usd_spent"] - expected_cost) < 1e-12


def test_guard_trips_mid_run_at_correct_threshold(store, monkeypatch):
    """AC4 / AC8: guard trips on the call that would exceed the budget.

    Budget = $0.01. Each call costs exactly $0.01 (5000 input @ $1/1M + 5000 output @ $1/1M).
    First call succeeds and exhausts the budget; second call sees remaining=0 and raises.
    """
    import asyncio
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    input_rate, output_rate = 1.0, 1.0  # $1/$1 per 1M tokens
    store.update_settings(
        api_usd_budget=0.01,
        groq_rates={"llama-3.1-8b-instant": {"input_per_1m": input_rate, "output_per_1m": output_rate}},
    )

    # Each call: 5000 input + 5000 output → $0.01 exactly
    usage = {"prompt_tokens": 5000, "completion_tokens": 5000}
    single_call_cost = (5000 / 1_000_000) * input_rate + (5000 / 1_000_000) * output_rate  # $0.01

    call_count = 0
    with patch.object(provider, "_post", new_callable=AsyncMock, return_value=("ok", usage)):
        for _ in range(20):
            try:
                asyncio.run(provider.complete("sys", "user", "claude-haiku-4-5"))
                call_count += 1
            except lp.GroqBudgetExhaustedError:
                break

    # First call succeeds (remaining=$0.01 > 0), second sees remaining=0 and raises
    assert call_count == 1
    spent = store.get_settings()["groq_usd_spent"]
    assert abs(spent - single_call_cost) < 1e-12


# ---------------------------------------------------------------------------
# AC5: Tavily / research fetch-budget accounting untouched
# ---------------------------------------------------------------------------

def test_research_fetcher_budget_is_integer_and_unchanged():
    """AC5: ResearchFetcherBase.budget is an integer count, unchanged by this issue."""
    from app.research.fetchers import ResearchFetcherBase
    rb = ResearchFetcherBase(budget=5)
    assert rb.budget == 5
    rb._consume_budget()
    assert rb.budget == 4


def test_budget_exhausted_error_still_in_research_types():
    """AC5: research BudgetExhaustedError is untouched."""
    from app.research.types import BudgetExhaustedError
    with pytest.raises(BudgetExhaustedError):
        raise BudgetExhaustedError("still works")


# ---------------------------------------------------------------------------
# AC6: unknown model → warning logged, $0 counted, run continues
# ---------------------------------------------------------------------------

def test_unknown_model_cost_is_zero(store, groq_provider, monkeypatch):
    """AC6: _groq_cost_usd returns 0.0 for unconfigured model."""
    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)

    store.update_settings(groq_rates={})  # no rates configured
    cost = groq_provider._groq_cost_usd("unknown-model-xyz", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert cost == 0.0


def test_unknown_model_emits_warning(store, groq_provider, monkeypatch, caplog):
    """AC6: warning is logged when model has no rate configured."""
    import logging

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    store.update_settings(groq_rates={})

    with caplog.at_level(logging.WARNING, logger="app.llm_providers"):
        groq_provider._groq_cost_usd("ghost-model", {"prompt_tokens": 100, "completion_tokens": 50})

    assert any("ghost-model" in m for m in caplog.messages)


def test_run_continues_after_unknown_model_warning(store, monkeypatch):
    """AC6: complete() returns result even when model has no configured rate."""
    import asyncio
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=1.0, groq_rates={})
    usage = {"prompt_tokens": 500, "completion_tokens": 200}

    with patch.object(provider, "_post", new_callable=AsyncMock, return_value=("result", usage)):
        result = asyncio.run(provider.complete("sys", "user", None))

    assert result == "result"
    # No spend recorded for unconfigured model
    assert store.get_settings()["groq_usd_spent"] == 0.0


# ---------------------------------------------------------------------------
# AC7: reset_spend also clears groq_usd_spent
# ---------------------------------------------------------------------------

def test_reset_spend_clears_groq_usd_spent(store):
    """AC7 / settings: reset_spend zeroes both api_usd_spent and groq_usd_spent."""
    store.update_settings(api_usd_budget=1.0)
    store.add_spend(0.3)
    store.add_groq_spend(0.4)
    store.reset_spend()
    s = store.get_settings()
    assert s["api_usd_spent"] == 0.0
    assert s["groq_usd_spent"] == 0.0


# ---------------------------------------------------------------------------
# AC8: sync path also deducts spend and respects budget guard
# ---------------------------------------------------------------------------

def test_complete_sync_deducts_groq_spend(store, monkeypatch):
    """AC8: complete_sync() adds Groq cost to groq_usd_spent."""
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    input_rate, output_rate = 0.05, 0.08
    store.update_settings(
        api_usd_budget=1.0,
        groq_rates={"llama-3.1-8b-instant": {"input_per_1m": input_rate, "output_per_1m": output_rate}},
    )

    usage = {"prompt_tokens": 500, "completion_tokens": 200}
    expected_cost = (500 / 1_000_000) * input_rate + (200 / 1_000_000) * output_rate

    with patch.object(provider, "_post_sync", return_value=("result text", usage)):
        provider.complete_sync("sys", "user", "claude-haiku-4-5")

    assert abs(store.get_settings()["groq_usd_spent"] - expected_cost) < 1e-12


def test_complete_sync_raises_when_budget_exhausted(store, monkeypatch):
    """AC8: complete_sync() raises GroqBudgetExhaustedError when budget is gone."""
    import app.llm_providers as lp

    monkeypatch.setenv("CRUX_SETTINGS_FILE", store._PATH.__str__())
    importlib.reload(store)
    importlib.reload(lp)
    provider = lp.GroqProvider()

    store.update_settings(api_usd_budget=0.001)
    store.add_groq_spend(0.001)

    with patch.object(provider, "_post_sync") as mock_post:
        with pytest.raises(lp.GroqBudgetExhaustedError):
            provider.complete_sync("sys", "user", None)
    mock_post.assert_not_called()
