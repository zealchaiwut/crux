"""Tests for issue #81: Wire real web fetchers into custom research engine.

AC coverage:
  AC1  – _CustomEngine.run uses WebSearchFetcher for discovery (not StubFetcher)
  AC2  – Read step uses ArticleReaderFetcher or YouTubeTranscriptFetcher (no StubFetcher)
  AC3  – RESEARCH_ENGINE=custom routes through real fetchers; no code change needed to switch
  AC4  – RESEARCH_ENGINE=fallback returns graceful empty results
  AC5  – max_fetches cap: candidates beyond cap are not fetched
  AC6  – Per-fetch failure logs WARNING with candidate URL, skips candidate
  AC7  – Per-fetch failure does not raise or abort the whole run call
  AC8  – CitationSynthesiser receives only surviving candidates
  AC9a – Unit test: max_fetches cap enforcement
  AC9b – Unit test: per-fetch failure skip with WARNING
  AC9c – Unit test: engine selection via config
"""
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan():
    from app.research.types import Plan
    return Plan(mechanism="test mechanism", prior="test prior")


def _make_search_results(urls):
    from app.research.types import SearchResult
    return [SearchResult(url=url, title=f"Title for {url}") for url in urls]


def _make_article_doc(url):
    from app.research.types import ArticleDocument
    return ArticleDocument(
        url=url,
        title=f"Title: {url}",
        text="This is a factual claim about something important. It contains enough content to extract.",
    )


def _make_source():
    from app.research.types import Source
    return Source(kind="article", title="T", url="http://x.com", claim="claim", citation="cit")


def _run_custom_engine_with_mocks(
    search_results_per_query,
    article_fetch_side_effect=None,
    yt_fetch_side_effect=None,
    max_fetches=10,
    queries=None,
):
    """Run _CustomEngine with mocked fetchers/planner/synthesiser.

    Returns (result, mock_article_fetcher, mock_yt_fetcher, mock_synthesiser).
    """
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import SearchQuery

    if queries is None:
        queries = [SearchQuery(query="test query 1")]

    mock_web_fetcher = MagicMock()
    mock_web_fetcher.fetch.side_effect = search_results_per_query

    mock_article_fetcher = MagicMock()
    mock_article_fetcher.fetch.side_effect = (
        article_fetch_side_effect
        if article_fetch_side_effect is not None
        else lambda url: _make_article_doc(url)
    )

    mock_yt_fetcher = MagicMock()
    if yt_fetch_side_effect is not None:
        mock_yt_fetcher.fetch.side_effect = yt_fetch_side_effect

    mock_synthesiser = MagicMock()
    mock_synthesiser.synthesise.return_value = [_make_source()]

    mock_config = MagicMock()
    mock_config.max_fetches = max_fetches

    with (
        patch("app.research.LLMQueryPlanner") as MockPlanner,
        patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher),
        patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
        patch("app.research.YouTubeTranscriptFetcher", return_value=mock_yt_fetcher),
        patch("app.research.DuckDuckGoSearchProvider"),
        patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
        patch("app.research.ResearchConfig") as MockConfig,
        patch("app.claude_cli.ClaudeCLIClient"),
    ):
        MockPlanner.return_value.plan.return_value = queries
        MockConfig.from_env.return_value = mock_config

        engine = _CustomEngine()
        result = engine.run(_make_plan())

    return result, mock_article_fetcher, mock_yt_fetcher, mock_synthesiser


# ---------------------------------------------------------------------------
# AC9c: Engine selection via config
# ---------------------------------------------------------------------------

class TestEngineSelection:
    def test_custom_engine_returned_for_custom(self):
        """make_engine('custom') returns _CustomEngine (AC9c, AC3)."""
        from app.services.research_orchestrator import make_engine, _CustomEngine
        assert isinstance(make_engine("custom"), _CustomEngine)

    def test_fallback_engine_returned_for_fallback(self):
        """make_engine('fallback') returns _FallbackEngine (AC9c, AC4)."""
        from app.services.research_orchestrator import make_engine, _FallbackEngine
        assert isinstance(make_engine("fallback"), _FallbackEngine)

    def test_fallback_engine_returns_empty(self):
        """_FallbackEngine.run returns [] without network calls (AC4)."""
        from app.services.research_orchestrator import _FallbackEngine
        assert _FallbackEngine().run(_make_plan()) == []

    def test_unknown_engine_name_defaults_to_custom(self):
        """Unrecognised engine name defaults to _CustomEngine (AC3 robustness)."""
        from app.services.research_orchestrator import make_engine, _CustomEngine
        assert isinstance(make_engine("anything_else"), _CustomEngine)


# ---------------------------------------------------------------------------
# AC9a: max_fetches cap enforcement
# ---------------------------------------------------------------------------

class TestMaxFetchesCap:
    def test_candidates_beyond_cap_not_fetched(self):
        """Only max_fetches candidates are read; the rest are silently skipped (AC5, AC9a)."""
        urls = [f"http://example.com/{i}" for i in range(5)]
        search_results = [_make_search_results(urls)]  # 5 results from 1 query

        _, mock_article, _, _ = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            max_fetches=2,
        )

        assert mock_article.fetch.call_count == 2

    def test_exactly_max_fetches_candidates_all_read(self):
        """When results == max_fetches, every candidate is fetched (AC5)."""
        urls = [f"http://example.com/{i}" for i in range(3)]
        search_results = [_make_search_results(urls)]

        _, mock_article, _, _ = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            max_fetches=3,
        )

        assert mock_article.fetch.call_count == 3

    def test_fewer_results_than_cap_all_fetched(self):
        """When results < max_fetches, every candidate is fetched (AC5)."""
        urls = ["http://example.com/1", "http://example.com/2"]
        search_results = [_make_search_results(urls)]

        _, mock_article, _, _ = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            max_fetches=10,
        )

        assert mock_article.fetch.call_count == 2


# ---------------------------------------------------------------------------
# AC9b: Per-fetch failure skip with WARNING
# ---------------------------------------------------------------------------

class TestPerFetchFailure:
    def test_fetch_failure_logs_warning_with_url(self, caplog):
        """Failed fetch logs WARNING containing the candidate URL (AC6, AC9b)."""
        from app.research.types import FetchTimeoutError

        urls = ["http://bad.example.com/fail", "http://good.example.com/ok"]
        search_results = [_make_search_results(urls)]

        def article_side_effect(url):
            if "bad" in url:
                raise FetchTimeoutError(f"Timeout fetching {url}")
            return _make_article_doc(url)

        with caplog.at_level(logging.WARNING, logger="app.services.research_orchestrator"):
            _run_custom_engine_with_mocks(
                search_results_per_query=search_results,
                article_fetch_side_effect=article_side_effect,
                max_fetches=10,
            )

        assert "http://bad.example.com/fail" in caplog.text

    def test_fetch_failure_does_not_raise(self):
        """Per-fetch failure does not propagate — run completes normally (AC7, AC9b)."""
        from app.research.types import FetchBlockedError

        urls = ["http://blocked.example.com/", "http://ok.example.com/"]
        search_results = [_make_search_results(urls)]

        def article_side_effect(url):
            if "blocked" in url:
                raise FetchBlockedError(f"HTTP 403 fetching {url}")
            return _make_article_doc(url)

        # Must not raise
        _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            article_fetch_side_effect=article_side_effect,
            max_fetches=10,
        )

    def test_surviving_candidates_only_passed_to_synthesiser(self):
        """CitationSynthesiser receives only successfully fetched candidates (AC8)."""
        from app.research.types import FetchTimeoutError

        urls = ["http://fail.example.com/", "http://ok1.example.com/", "http://ok2.example.com/"]
        search_results = [_make_search_results(urls)]

        def article_side_effect(url):
            if "fail" in url:
                raise FetchTimeoutError("timeout")
            return _make_article_doc(url)

        _, _, _, mock_synth = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            article_fetch_side_effect=article_side_effect,
            max_fetches=10,
        )

        assert mock_synth.synthesise.called
        candidates = mock_synth.synthesise.call_args[0][1]
        for c in candidates:
            assert "fail" not in c["url"]

    def test_all_fetches_fail_returns_empty_list(self):
        """If every fetch fails, returns [] and synthesiser is never called (AC7)."""
        from app.research.types import FetchTimeoutError

        urls = ["http://fail1.example.com/", "http://fail2.example.com/"]
        search_results = [_make_search_results(urls)]

        def article_side_effect(url):
            raise FetchTimeoutError("always fail")

        result, _, _, mock_synth = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            article_fetch_side_effect=article_side_effect,
            max_fetches=10,
        )

        assert result == []
        mock_synth.synthesise.assert_not_called()


# ---------------------------------------------------------------------------
# AC1 + AC2: Real fetchers wired in
# ---------------------------------------------------------------------------

class TestRealFetchersWired:
    def test_web_search_fetcher_used_for_discovery(self):
        """WebSearchFetcher.fetch called during discovery step, not StubFetcher (AC1)."""
        from app.research.types import SearchQuery

        urls = ["http://example.com/a"]
        search_results = [_make_search_results(urls)]

        mock_web_fetcher = MagicMock()
        mock_web_fetcher.fetch.side_effect = search_results

        mock_article_fetcher = MagicMock()
        mock_article_fetcher.fetch.side_effect = lambda url: _make_article_doc(url)
        mock_synthesiser = MagicMock()
        mock_synthesiser.synthesise.return_value = []
        mock_config = MagicMock()
        mock_config.max_fetches = 10

        from app.services.research_orchestrator import _CustomEngine

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher) as MockWebClass,
            patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = mock_config
            MockWebClass.return_value = mock_web_fetcher

            _CustomEngine().run(_make_plan())

        assert mock_web_fetcher.fetch.called
        assert mock_article_fetcher.fetch.called

    def test_youtube_fetcher_used_for_yt_urls(self):
        """YouTubeTranscriptFetcher.fetch called for youtube.com URLs, not ArticleReaderFetcher (AC2)."""
        from app.research.types import SearchQuery, ArticleDocument

        yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        search_results = [_make_search_results([yt_url])]

        yt_doc = ArticleDocument(
            url=yt_url,
            title="YT Video",
            text="Factual claim about research topics. This content describes important findings.",
        )

        mock_web_fetcher = MagicMock()
        mock_web_fetcher.fetch.side_effect = search_results
        mock_article_fetcher = MagicMock()
        mock_yt_fetcher = MagicMock()
        mock_yt_fetcher.fetch.return_value = yt_doc
        mock_synthesiser = MagicMock()
        mock_synthesiser.synthesise.return_value = []
        mock_config = MagicMock()
        mock_config.max_fetches = 10

        from app.services.research_orchestrator import _CustomEngine

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web_fetcher),
            patch("app.research.ArticleReaderFetcher", return_value=mock_article_fetcher),
            patch("app.research.YouTubeTranscriptFetcher", return_value=mock_yt_fetcher),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser", return_value=mock_synthesiser),
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="yt query")]
            MockConfig.from_env.return_value = mock_config

            _CustomEngine().run(_make_plan())

        mock_yt_fetcher.fetch.assert_called_once_with(yt_url)
        mock_article_fetcher.fetch.assert_not_called()

    def test_article_fetcher_used_for_non_yt_urls(self):
        """ArticleReaderFetcher.fetch called for non-YouTube URLs (AC2)."""
        from app.research.types import SearchQuery

        urls = ["http://example.com/article", "https://news.site.com/story"]
        search_results = [_make_search_results(urls)]

        _, mock_article, mock_yt, _ = _run_custom_engine_with_mocks(
            search_results_per_query=search_results,
            max_fetches=10,
        )

        assert mock_article.fetch.call_count == 2
        mock_yt.fetch.assert_not_called()
