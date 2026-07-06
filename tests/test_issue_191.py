"""Tests for issue #191: Route bulk pipeline stages to CRUX_BULK_MODEL.

AC coverage:
  AC1 — per-source content_summary calls use CRUX_BULK_MODEL from the provider interface
  AC2 — deduplication calls use CRUX_BULK_MODEL from the provider interface
  AC3 — candidate summarization calls use CRUX_BULK_MODEL from the provider interface
  AC4 — CRUX_BULK_MODEL is read from environment/config independently of judgment model setting
  AC5 — changing judgment model does not affect which model bulk calls use
  AC6 — per-source summaries for a case are routed through Groq (as the configured bulk provider)
  AC7 — judgment/scoring calls are unaffected and continue using their configured model
"""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# AC1: content_summary calls use CRUX_BULK_MODEL via the provider interface
# ---------------------------------------------------------------------------

def test_content_summary_calls_call_bulk_stage():
    """AC1: content_summary routes through call_bulk_stage, not call_stage."""
    from app.bulk_stages import content_summary

    mock_result = {"summary": "This source discusses X."}

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value=mock_result) as mock_bulk:
        result = asyncio.run(content_summary("Source text here.", "Test Title"))

    mock_bulk.assert_called_once()
    assert result == "This source discusses X."


def test_content_summary_sync_calls_call_bulk_stage_sync():
    """AC1: content_summary_sync routes through call_bulk_stage_sync."""
    from app.bulk_stages import content_summary_sync

    mock_result = {"summary": "This source discusses Y."}

    with patch("app.bulk_stages.call_bulk_stage_sync", return_value=mock_result) as mock_bulk:
        result = content_summary_sync("Source text.", "My Source")

    mock_bulk.assert_called_once()
    assert result == "This source discusses Y."


def test_content_summary_never_calls_call_stage():
    """AC1: content_summary must NOT use call_stage (judgment routing)."""
    from app.bulk_stages import content_summary

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value={"summary": "ok"}):
        with patch("app.llm_providers.call_stage", new_callable=AsyncMock) as mock_judgment:
            asyncio.run(content_summary("text", "title"))

    mock_judgment.assert_not_called()


def test_content_summary_returns_string():
    """AC1: content_summary returns a string (the summary text)."""
    from app.bulk_stages import content_summary

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value={"summary": "Summary text."}):
        result = asyncio.run(content_summary("long text here", "Some Title"))

    assert isinstance(result, str)
    assert result == "Summary text."


# ---------------------------------------------------------------------------
# AC2: deduplication calls use CRUX_BULK_MODEL via the provider interface
# ---------------------------------------------------------------------------

def test_dedup_candidates_calls_call_bulk_stage():
    """AC2: dedup_candidates routes through call_bulk_stage."""
    from app.bulk_stages import dedup_candidates

    candidates = [
        {"url": "https://a.com", "claim": "Claim A"},
        {"url": "https://b.com", "claim": "Claim B"},
        {"url": "https://a.com", "claim": "Claim A duplicate"},
    ]
    mock_result = {"keep_indices": [0, 1]}

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value=mock_result) as mock_bulk:
        result = asyncio.run(dedup_candidates(candidates))

    mock_bulk.assert_called_once()
    assert len(result) == 2
    assert result[0] == candidates[0]
    assert result[1] == candidates[1]


def test_dedup_candidates_sync_calls_call_bulk_stage_sync():
    """AC2: dedup_candidates_sync routes through call_bulk_stage_sync."""
    from app.bulk_stages import dedup_candidates_sync

    candidates = [
        {"url": "https://a.com", "claim": "Claim A"},
        {"url": "https://b.com", "claim": "Claim B"},
    ]
    mock_result = {"keep_indices": [0, 1]}

    with patch("app.bulk_stages.call_bulk_stage_sync", return_value=mock_result) as mock_bulk:
        result = dedup_candidates_sync(candidates)

    mock_bulk.assert_called_once()
    assert len(result) == 2


def test_dedup_candidates_single_item_skips_llm():
    """AC2: dedup_candidates with one candidate skips LLM call (no-op optimization)."""
    from app.bulk_stages import dedup_candidates

    candidates = [{"url": "https://a.com", "claim": "Only one"}]

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock) as mock_bulk:
        result = asyncio.run(dedup_candidates(candidates))

    mock_bulk.assert_not_called()
    assert result == candidates


def test_dedup_candidates_returns_original_on_error():
    """AC2: dedup_candidates returns original list if LLM call fails."""
    from app.bulk_stages import dedup_candidates

    candidates = [
        {"url": "https://a.com", "claim": "A"},
        {"url": "https://b.com", "claim": "B"},
    ]

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, side_effect=Exception("API error")):
        result = asyncio.run(dedup_candidates(candidates))

    assert result == candidates


def test_dedup_candidates_never_calls_call_stage():
    """AC2: dedup_candidates must NOT use call_stage (judgment routing)."""
    from app.bulk_stages import dedup_candidates

    candidates = [{"url": "https://a.com", "claim": "A"}, {"url": "https://b.com", "claim": "B"}]

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value={"keep_indices": [0, 1]}):
        with patch("app.llm_providers.call_stage", new_callable=AsyncMock) as mock_judgment:
            asyncio.run(dedup_candidates(candidates))

    mock_judgment.assert_not_called()


# ---------------------------------------------------------------------------
# AC3: candidate summarization calls use CRUX_BULK_MODEL via the provider interface
# ---------------------------------------------------------------------------

def test_summarize_candidates_calls_call_bulk_stage():
    """AC3: summarize_candidates routes through call_bulk_stage."""
    from app.bulk_stages import summarize_candidates

    candidates = [
        {"kind": "article", "title": "Source A", "url": "https://a.com", "claim": "Claim A"},
    ]
    mock_result = {
        "sources": [{
            "kind": "article",
            "title": "Source A",
            "url": "https://a.com",
            "claim": "Claim A",
            "citation": "Quote from source",
        }]
    }

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value=mock_result) as mock_bulk:
        result = asyncio.run(summarize_candidates("mechanism text", "prior text", candidates))

    mock_bulk.assert_called_once()
    assert len(result) == 1
    assert result[0]["kind"] == "article"
    assert result[0]["citation"] == "Quote from source"


def test_summarize_candidates_sync_calls_call_bulk_stage_sync():
    """AC3: summarize_candidates_sync routes through call_bulk_stage_sync."""
    from app.bulk_stages import summarize_candidates_sync

    candidates = [{"kind": "article", "title": "T", "url": "https://t.com", "claim": "c"}]
    mock_result = {
        "sources": [{"kind": "article", "title": "T", "url": "https://t.com", "claim": "c", "citation": "q"}]
    }

    with patch("app.bulk_stages.call_bulk_stage_sync", return_value=mock_result) as mock_bulk:
        result = summarize_candidates_sync("mech", "prior", candidates)

    mock_bulk.assert_called_once()
    assert len(result) == 1


def test_summarize_candidates_empty_skips_llm():
    """AC3: summarize_candidates with empty candidate list skips LLM call."""
    from app.bulk_stages import summarize_candidates

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock) as mock_bulk:
        result = asyncio.run(summarize_candidates("mech", "prior", []))

    mock_bulk.assert_not_called()
    assert result == []


def test_summarize_candidates_filters_invalid_rows():
    """AC3: summarize_candidates drops rows with invalid kind, empty title, etc."""
    from app.bulk_stages import summarize_candidates

    candidates = [{"kind": "article", "title": "T", "url": "https://t.com", "claim": "c"}]
    mock_result = {
        "sources": [
            {"kind": "article", "title": "T", "url": "https://t.com", "claim": "c", "citation": "q"},
            {"kind": "bad_kind", "title": "T2", "url": "https://t2.com", "claim": "c2", "citation": "q2"},
            {"kind": "article", "title": "", "url": "https://t3.com", "claim": "c3", "citation": "q3"},
        ]
    }

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value=mock_result):
        result = asyncio.run(summarize_candidates("mech", "prior", candidates))

    assert len(result) == 1
    assert result[0]["kind"] == "article"


def test_summarize_candidates_never_calls_call_stage():
    """AC3: summarize_candidates must NOT use call_stage (judgment routing)."""
    from app.bulk_stages import summarize_candidates

    candidates = [{"kind": "article", "title": "T", "url": "https://t.com", "claim": "c"}]
    mock_result = {
        "sources": [{"kind": "article", "title": "T", "url": "https://t.com", "claim": "c", "citation": "q"}]
    }

    with patch("app.bulk_stages.call_bulk_stage", new_callable=AsyncMock, return_value=mock_result):
        with patch("app.llm_providers.call_stage", new_callable=AsyncMock) as mock_judgment:
            asyncio.run(summarize_candidates("mech", "prior", candidates))

    mock_judgment.assert_not_called()


# ---------------------------------------------------------------------------
# AC4 + AC5: CRUX_BULK_MODEL is independent of judgment model
# ---------------------------------------------------------------------------

def test_call_bulk_stage_uses_complete_bulk_structured_not_complete_structured():
    """AC4/AC5: call_bulk_stage uses complete_bulk_structured (explicit bulk), not complete_structured."""
    from app.llm_providers import call_bulk_stage

    mock_provider = MagicMock()
    mock_provider.supports_structured_output = True
    mock_provider.complete_bulk_structured = AsyncMock(return_value={"result": "bulk"})
    mock_provider.complete_structured = AsyncMock(return_value={"result": "judgment"})

    with patch("app.llm_providers.get_provider", return_value=mock_provider):
        result = asyncio.run(call_bulk_stage("sys", "user", "test_schema", {}))

    mock_provider.complete_bulk_structured.assert_called_once()
    mock_provider.complete_structured.assert_not_called()
    assert result == {"result": "bulk"}


def test_groq_complete_bulk_structured_uses_bulk_model_exclusively(monkeypatch):
    """AC4/AC5: GroqProvider.complete_bulk_structured always uses _bulk_model, never _judgment_model."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")

    from app.llm_providers import GroqProvider
    provider = GroqProvider()

    captured = {}
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    mock_resp.raise_for_status.return_value = None

    async def fake_post(url, json=None, headers=None):
        captured["model"] = (json or {}).get("model")
        return mock_resp

    with patch("httpx.AsyncClient") as MockCls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        MockCls.return_value = mock_client

        asyncio.run(provider.complete_bulk_structured("sys", "user", "test", {"type": "object"}))

    assert captured["model"] == "llama-3.1-8b-instant", \
        f"Expected bulk model, got '{captured['model']}'"
    assert captured["model"] != "openai/gpt-oss-120b", \
        "complete_bulk_structured must NOT use the judgment model"


def test_groq_complete_bulk_structured_sync_uses_bulk_model(monkeypatch):
    """AC4/AC5: GroqProvider.complete_bulk_structured_sync always uses _bulk_model."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")

    from app.llm_providers import GroqProvider
    provider = GroqProvider()

    captured = {}
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    mock_resp.raise_for_status.return_value = None

    def fake_post(url, json=None, headers=None):
        captured["model"] = (json or {}).get("model")
        return mock_resp

    with patch("httpx.Client") as MockCls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post = MagicMock(side_effect=fake_post)
        MockCls.return_value = mock_client

        provider.complete_bulk_structured_sync("sys", "user", "test", {"type": "object"})

    assert captured["model"] == "llama-3.1-8b-instant"
    assert captured["model"] != "openai/gpt-oss-120b"


def test_changing_judgment_model_does_not_affect_bulk_model(monkeypatch):
    """AC5: Changing CRUX_JUDGMENT_MODEL does not change which model bulk calls use."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")

    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
    from app.llm_providers import GroqProvider
    import importlib
    import app.llm_providers as lp
    importlib.reload(lp)
    provider_a = lp.GroqProvider()

    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "llama-3.3-70b-versatile")
    importlib.reload(lp)
    provider_b = lp.GroqProvider()

    assert provider_a._bulk_model == "llama-3.1-8b-instant"
    assert provider_b._bulk_model == "llama-3.1-8b-instant"
    assert provider_a._bulk_model == provider_b._bulk_model
    assert provider_a._judgment_model != provider_b._judgment_model


def test_crux_bulk_model_env_var_is_read_independently(monkeypatch):
    """AC4: CRUX_BULK_MODEL is read from env independently of CRUX_JUDGMENT_MODEL."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "gemma2-9b-it")
    monkeypatch.setenv("CRUX_JUDGMENT_MODEL", "llama-3.3-70b-versatile")

    import importlib
    import app.llm_providers as lp
    importlib.reload(lp)
    provider = lp.GroqProvider()

    assert provider._bulk_model == "gemma2-9b-it"
    assert provider._judgment_model == "llama-3.3-70b-versatile"
    assert provider._bulk_model != provider._judgment_model


# ---------------------------------------------------------------------------
# AC6: per-source summaries routed through Groq as the configured bulk provider
# ---------------------------------------------------------------------------

def test_groq_provider_exposes_complete_bulk_structured():
    """AC6: GroqProvider has complete_bulk_structured and complete_bulk_structured_sync."""
    from app.llm_providers import GroqProvider
    assert callable(getattr(GroqProvider, "complete_bulk_structured", None)), \
        "GroqProvider must have complete_bulk_structured method"
    assert callable(getattr(GroqProvider, "complete_bulk_structured_sync", None)), \
        "GroqProvider must have complete_bulk_structured_sync method"


def test_call_bulk_stage_routes_to_groq_complete_bulk_structured():
    """AC6: When provider is Groq, call_bulk_stage calls complete_bulk_structured."""
    from app.llm_providers import call_bulk_stage, GroqProvider

    provider = MagicMock(spec=GroqProvider)
    provider.supports_structured_output = True
    provider.complete_bulk_structured = AsyncMock(return_value={"summary": "via groq bulk"})

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = asyncio.run(call_bulk_stage("sys", "user", "test_schema", {"type": "object"}))

    provider.complete_bulk_structured.assert_called_once_with("sys", "user", "test_schema", {"type": "object"})
    assert result == {"summary": "via groq bulk"}


def test_content_summary_reaches_groq_bulk_model(monkeypatch):
    """AC6: content_summary routes through Groq's bulk model when provider=groq."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CRUX_BULK_MODEL", "llama-3.1-8b-instant")

    from app.llm_providers import GroqProvider
    provider = GroqProvider()
    provider.complete_bulk_structured = AsyncMock(return_value={"summary": "Groq bulk summary"})

    with patch("app.llm_providers.get_provider", return_value=provider):
        from app.bulk_stages import content_summary
        result = asyncio.run(content_summary("Source text about X.", "Article Title"))

    provider.complete_bulk_structured.assert_called_once()
    assert result == "Groq bulk summary"


def test_call_bulk_stage_sync_routes_to_groq_complete_bulk_structured_sync():
    """AC6: call_bulk_stage_sync uses complete_bulk_structured_sync on Groq provider."""
    from app.llm_providers import call_bulk_stage_sync, GroqProvider

    provider = MagicMock(spec=GroqProvider)
    provider.supports_structured_output = True
    provider.complete_bulk_structured_sync = MagicMock(return_value={"ok": True})

    with patch("app.llm_providers.get_provider", return_value=provider):
        result = call_bulk_stage_sync("sys", "user", "test_schema", {"type": "object"})

    provider.complete_bulk_structured_sync.assert_called_once_with(
        "sys", "user", "test_schema", {"type": "object"}
    )
    assert result == {"ok": True}


# ---------------------------------------------------------------------------
# AC7: judgment/scoring calls are unaffected
# ---------------------------------------------------------------------------

def test_sharpen_uses_call_stage_not_call_bulk_stage():
    """AC7: sharpen.py must use call_stage (judgment), not call_bulk_stage."""
    import app.sharpen
    src = inspect.getsource(app.sharpen)
    assert "call_bulk_stage" not in src, "sharpen.py must not use call_bulk_stage"
    assert "call_stage" in src


def test_bake_off_uses_call_stage_not_call_bulk_stage():
    """AC7: bake_off.py must use call_stage (judgment), not call_bulk_stage."""
    import app.bake_off
    src = inspect.getsource(app.bake_off)
    assert "call_bulk_stage" not in src, "bake_off.py must not use call_bulk_stage"
    assert "call_stage" in src


def test_weigh_uses_call_stage_not_call_bulk_stage():
    """AC7: weigh.py must use call_stage (judgment), not call_bulk_stage."""
    import app.weigh
    src = inspect.getsource(app.weigh)
    assert "call_bulk_stage" not in src, "weigh.py must not use call_bulk_stage"
    assert "call_stage" in src


def test_probe_uses_call_stage_not_call_bulk_stage():
    """AC7: probe.py must use call_stage (judgment), not call_bulk_stage."""
    import app.probe
    src = inspect.getsource(app.probe)
    assert "call_bulk_stage" not in src, "probe.py must not use call_bulk_stage"
    assert "call_stage" in src


def test_call_stage_still_routes_to_complete_structured_not_bulk():
    """AC7: call_stage still calls complete_structured (judgment), not complete_bulk_structured."""
    from app.llm_providers import call_stage

    mock_provider = MagicMock()
    mock_provider.supports_structured_output = True
    mock_provider.complete_structured = AsyncMock(return_value={"sharpened": "ok", "not_investigating": []})
    mock_provider.complete_bulk_structured = AsyncMock()

    with patch("app.llm_providers.get_provider", return_value=mock_provider):
        asyncio.run(call_stage("sys", "user", "claude-haiku-4-5", "sharpen", {"type": "object"}))

    mock_provider.complete_structured.assert_called_once()
    mock_provider.complete_bulk_structured.assert_not_called()


# ---------------------------------------------------------------------------
# call_bulk_stage_sync — sync path correctness
# ---------------------------------------------------------------------------

def test_call_bulk_stage_sync_exists_in_llm_providers():
    """call_bulk_stage_sync must be exported from app.llm_providers."""
    import app.llm_providers
    assert callable(getattr(app.llm_providers, "call_bulk_stage_sync", None)), \
        "app.llm_providers must export call_bulk_stage_sync"


def test_call_bulk_stage_sync_falls_back_without_structured(monkeypatch):
    """call_bulk_stage_sync falls back to complete_sync when provider lacks structured bulk method."""
    import json
    from app.llm_providers import call_bulk_stage_sync
    from app.claude_cli import _strip_fences

    mock_provider = MagicMock()
    mock_provider.supports_structured_output = False
    del mock_provider.complete_bulk_structured_sync
    mock_provider.complete_sync = MagicMock(return_value='{"result": "fallback"}')

    with patch("app.llm_providers.get_provider", return_value=mock_provider):
        result = call_bulk_stage_sync("sys", "user", "schema", {"type": "object"})

    mock_provider.complete_sync.assert_called_once()
    assert result == {"result": "fallback"}


# ---------------------------------------------------------------------------
# Orchestrator integration: bulk stages triggered when provider configured
# ---------------------------------------------------------------------------

def test_orchestrator_calls_content_summary_per_source_when_provider_set():
    """AC1/AC6: _CustomEngine.run() calls content_summary_sync for each fetched source
    when a provider is configured."""
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import Plan, SearchResult, ArticleDocument, Source, SearchQuery

    plan = Plan(mechanism="test mechanism", prior="test prior")

    mock_web_fetcher = MagicMock()
    mock_web_fetcher.fetch.return_value = [
        SearchResult(url="https://a.com", title="Article A"),
    ]

    mock_article_fetcher = MagicMock()
    mock_article_fetcher.fetch.return_value = ArticleDocument(
        url="https://a.com", title="Article A", text="Some factual content here."
    )

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["A factual claim from the article."]

    mock_synthesiser = MagicMock()
    mock_synthesiser.synthesise.return_value = [
        Source(kind="article", title="A", url="https://a.com", claim="claim", citation="cit")
    ]

    mock_config = MagicMock()
    mock_config.max_fetches = 5

    mock_provider = MagicMock()
    mock_provider.supports_structured_output = True

    content_summary_calls = []

    def fake_content_summary_sync(text, title):
        content_summary_calls.append(title)
        return "Summarized."

    with (
        patch("app.research.LLMQueryPlanner") as MockPlanner,
        patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher),
        patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
        patch("app.research.YouTubeTranscriptFetcher"),
        patch("app.research.DuckDuckGoSearchProvider"),
        patch("app.research.ClaimExtractor", return_value=mock_extractor),
        patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
        patch("app.research.ResearchConfig") as MockConfig,
        patch("app.claude_cli.ClaudeCLIClient"),
        patch("app.llm_providers.get_provider", return_value=mock_provider),
        patch("app.bulk_stages.content_summary_sync", side_effect=fake_content_summary_sync),
    ):
        MockPlanner.return_value.plan.return_value = [SearchQuery(query="test query")]
        MockConfig.from_env.return_value = mock_config

        engine = _CustomEngine()
        engine.run(plan)

    assert len(content_summary_calls) >= 1, \
        "content_summary_sync must be called once per successfully fetched source"


def test_orchestrator_skips_bulk_stages_when_no_provider():
    """AC7: _CustomEngine.run() does NOT call bulk stages when no provider is configured."""
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import Plan, SearchResult, ArticleDocument, Source, SearchQuery

    plan = Plan(mechanism="test mechanism", prior="test prior")

    mock_web_fetcher = MagicMock()
    mock_web_fetcher.fetch.return_value = [SearchResult(url="https://a.com", title="Article A")]

    mock_article_fetcher = MagicMock()
    mock_article_fetcher.fetch.return_value = ArticleDocument(
        url="https://a.com", title="Article A", text="Some content."
    )

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["A claim from the article."]

    expected_source = Source(kind="article", title="A", url="https://a.com", claim="c", citation="q")
    mock_synthesiser = MagicMock()
    mock_synthesiser.synthesise.return_value = [expected_source]

    mock_config = MagicMock()
    mock_config.max_fetches = 5

    with (
        patch("app.research.LLMQueryPlanner") as MockPlanner,
        patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher),
        patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
        patch("app.research.YouTubeTranscriptFetcher"),
        patch("app.research.DuckDuckGoSearchProvider"),
        patch("app.research.ClaimExtractor", return_value=mock_extractor),
        patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
        patch("app.research.ResearchConfig") as MockConfig,
        patch("app.claude_cli.ClaudeCLIClient"),
        patch("app.llm_providers.get_provider", return_value=None),
    ):
        MockPlanner.return_value.plan.return_value = [SearchQuery(query="test")]
        MockConfig.from_env.return_value = mock_config

        engine = _CustomEngine()
        result = engine.run(plan)

    # CitationSynthesiser should be called (fallback), bulk stages should NOT
    assert mock_synthesiser.synthesise.called, \
        "CitationSynthesiser.synthesise must still be called when no bulk provider configured"
    assert len(result) > 0


def test_orchestrator_calls_dedup_when_provider_set():
    """AC2: _CustomEngine.run() calls dedup_candidates_sync after collecting candidates."""
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import Plan, SearchResult, ArticleDocument, Source, SearchQuery

    plan = Plan(mechanism="mechanism", prior="prior")

    mock_web_fetcher = MagicMock()
    mock_web_fetcher.fetch.return_value = [
        SearchResult(url="https://a.com", title="A"),
        SearchResult(url="https://b.com", title="B"),
    ]

    mock_article_fetcher = MagicMock()
    mock_article_fetcher.fetch.side_effect = [
        ArticleDocument(url="https://a.com", title="A", text="factual content A"),
        ArticleDocument(url="https://b.com", title="B", text="factual content B"),
    ]

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["A factual claim."]

    mock_synthesiser = MagicMock()
    mock_synthesiser.synthesise.return_value = []

    mock_config = MagicMock()
    mock_config.max_fetches = 5

    mock_provider = MagicMock()
    mock_provider.supports_structured_output = True

    dedup_calls = []

    def fake_dedup(candidates):
        dedup_calls.append(len(candidates))
        return candidates

    def fake_summarize(mech, prior, candidates):
        return []

    with (
        patch("app.research.LLMQueryPlanner") as MockPlanner,
        patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher),
        patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
        patch("app.research.YouTubeTranscriptFetcher"),
        patch("app.research.DuckDuckGoSearchProvider"),
        patch("app.research.ClaimExtractor", return_value=mock_extractor),
        patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
        patch("app.research.ResearchConfig") as MockConfig,
        patch("app.claude_cli.ClaudeCLIClient"),
        patch("app.llm_providers.get_provider", return_value=mock_provider),
        patch("app.bulk_stages.content_summary_sync", return_value="summary"),
        patch("app.bulk_stages.dedup_candidates_sync", side_effect=fake_dedup),
        patch("app.bulk_stages.summarize_candidates_sync", side_effect=fake_summarize),
    ):
        MockPlanner.return_value.plan.return_value = [SearchQuery(query="test")]
        MockConfig.from_env.return_value = mock_config

        engine = _CustomEngine()
        engine.run(plan)

    assert len(dedup_calls) >= 1, "dedup_candidates_sync must be called in the pipeline"
