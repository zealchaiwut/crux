"""Tests for issue #86: Specify exception types in research_orchestrator fetch error handling.

AC coverage:
  AC1 – bare except Exception at web search step replaced with specific exception types
         covering at least timeout, HTTP block, and rate limit
  AC2 – bare except Exception at article/YT fetch step replaced with specific exception types
         covering at least timeout, HTTP block, and rate limit
  AC3 – exception types used are defined/imported (no NameError at runtime)
  AC4 – exceptions NOT in the specified set propagate unhandled (handlers don't swallow unexpected errors)
  AC5 – existing tests for research_orchestrator pass without modification (verified by running pytest)
"""
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers (shared with test_issue_81.py pattern)
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
        text="Factual claim about something. Enough content to extract here.",
    )


def _make_source():
    from app.research.types import Source
    return Source(kind="article", title="T", url="http://x.com", claim="claim", citation="cit")


def _run_custom_engine(
    search_side_effect=None,
    article_fetch_side_effect=None,
    max_fetches=10,
    queries=None,
):
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import SearchQuery

    if queries is None:
        queries = [SearchQuery(query="test query")]

    mock_web_fetcher = MagicMock()
    if search_side_effect is not None:
        mock_web_fetcher.fetch.side_effect = search_side_effect

    mock_article_fetcher = MagicMock()
    mock_article_fetcher.fetch.side_effect = (
        article_fetch_side_effect
        if article_fetch_side_effect is not None
        else lambda url: _make_article_doc(url)
    )

    mock_yt_fetcher = MagicMock()
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
        return engine, mock_web_fetcher, mock_article_fetcher, mock_synthesiser


# ---------------------------------------------------------------------------
# AC3: Exception types are importable (no NameError)
# ---------------------------------------------------------------------------

class TestExceptionTypesImportable:
    def test_fetch_rate_limit_error_importable_from_types(self):
        """FetchRateLimitError is defined in app.research.types (AC3)."""
        from app.research.types import FetchRateLimitError
        assert issubclass(FetchRateLimitError, Exception)

    def test_fetch_rate_limit_error_importable_from_research(self):
        """FetchRateLimitError is exported from app.research (AC3)."""
        from app.research import FetchRateLimitError
        assert issubclass(FetchRateLimitError, Exception)


# ---------------------------------------------------------------------------
# AC1: Web search step catches specific fetch exceptions
# ---------------------------------------------------------------------------

class TestSearchStepSpecificExceptions:
    def test_search_timeout_caught_and_continues(self):
        """FetchTimeoutError during search is caught; engine returns normally (AC1)."""
        from app.research.types import FetchTimeoutError, SearchResult

        def search_side_effect(query):
            raise FetchTimeoutError("DDG timed out")

        engine, mock_web, _, _ = _run_custom_engine(search_side_effect=search_side_effect)

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher"),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser") as MockSynth,
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            from app.research.types import SearchQuery
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            MockSynth.return_value.synthesise.return_value = []
            mock_web.fetch.side_effect = FetchTimeoutError("DDG timed out")
            result = engine.run(_make_plan())

        assert result == []

    def test_search_blocked_caught_and_continues(self):
        """FetchBlockedError during search is caught; engine returns normally (AC1)."""
        from app.research.types import FetchBlockedError

        engine, mock_web, _, _ = _run_custom_engine()

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher"),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser") as MockSynth,
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            from app.research.types import SearchQuery
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            MockSynth.return_value.synthesise.return_value = []
            mock_web.fetch.side_effect = FetchBlockedError("HTTP 403")
            result = engine.run(_make_plan())

        assert result == []

    def test_search_rate_limit_caught_and_continues(self):
        """FetchRateLimitError during search is caught; engine returns normally (AC1)."""
        from app.research.types import FetchRateLimitError

        engine, mock_web, _, _ = _run_custom_engine()

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher"),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser") as MockSynth,
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            from app.research.types import SearchQuery
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            MockSynth.return_value.synthesise.return_value = []
            mock_web.fetch.side_effect = FetchRateLimitError("Rate limited")
            result = engine.run(_make_plan())

        assert result == []


# ---------------------------------------------------------------------------
# AC2: Article/YT fetch step catches specific fetch exceptions
# ---------------------------------------------------------------------------

class TestFetchStepSpecificExceptions:
    def _run_with_article_error(self, exc):
        from app.research.types import SearchResult, SearchQuery

        urls = ["http://example.com/fail"]
        mock_web = MagicMock()
        mock_web.fetch.return_value = [SearchResult(url=u, title="T") for u in urls]
        mock_article = MagicMock()
        mock_article.fetch.side_effect = exc
        mock_synth = MagicMock()
        mock_synth.synthesise.return_value = []

        from app.services.research_orchestrator import _CustomEngine

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher", return_value=mock_article),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser", return_value=mock_synth),
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            engine = _CustomEngine()
            return engine.run(_make_plan())

    def test_fetch_timeout_caught_and_skipped(self):
        """FetchTimeoutError during article fetch is caught; result is [] (AC2)."""
        from app.research.types import FetchTimeoutError
        result = self._run_with_article_error(FetchTimeoutError("timeout"))
        assert result == []

    def test_fetch_blocked_caught_and_skipped(self):
        """FetchBlockedError during article fetch is caught; result is [] (AC2)."""
        from app.research.types import FetchBlockedError
        result = self._run_with_article_error(FetchBlockedError("HTTP 403"))
        assert result == []

    def test_fetch_rate_limit_caught_and_skipped(self):
        """FetchRateLimitError during article fetch is caught; result is [] (AC2)."""
        from app.research.types import FetchRateLimitError
        result = self._run_with_article_error(FetchRateLimitError("rate limited"))
        assert result == []

    def test_fetch_empty_content_caught_and_skipped(self):
        """FetchEmptyContentError during article fetch is caught; result is [] (AC2)."""
        from app.research.types import FetchEmptyContentError
        result = self._run_with_article_error(FetchEmptyContentError("too short"))
        assert result == []


# ---------------------------------------------------------------------------
# AC4: Unexpected exceptions propagate unhandled (not silently swallowed)
# ---------------------------------------------------------------------------

class TestUnexpectedExceptionsPropagateFromSearchStep:
    def test_value_error_in_search_step_propagates(self):
        """ValueError from the search step propagates out (not swallowed) (AC4)."""
        from app.research.types import SearchQuery
        from app.services.research_orchestrator import _CustomEngine

        mock_web = MagicMock()
        mock_web.fetch.side_effect = ValueError("unexpected programming error")

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher"),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser"),
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            engine = _CustomEngine()
            with pytest.raises(Exception):
                engine.run(_make_plan())


class TestUnexpectedExceptionsPropagateFromFetchStep:
    def test_value_error_in_fetch_step_propagates(self):
        """ValueError from the article fetch step propagates out (not swallowed) (AC4)."""
        from app.research.types import SearchResult, SearchQuery
        from app.services.research_orchestrator import _CustomEngine

        mock_web = MagicMock()
        mock_web.fetch.return_value = [SearchResult(url="http://x.com", title="X")]
        mock_article = MagicMock()
        mock_article.fetch.side_effect = ValueError("unexpected programming error")

        with (
            patch("app.research.LLMQueryPlanner") as MockPlanner,
            patch("app.research.WebSearchFetcher", return_value=mock_web),
            patch("app.research.ArticleReaderFetcher", return_value=mock_article),
            patch("app.research.YouTubeTranscriptFetcher"),
            patch("app.research.DuckDuckGoSearchProvider"),
            patch("app.research.CitationSynthesiser"),
            patch("app.research.ResearchConfig") as MockConfig,
            patch("app.claude_cli.ClaudeCLIClient"),
        ):
            MockPlanner.return_value.plan.return_value = [SearchQuery(query="q1")]
            MockConfig.from_env.return_value = MagicMock(max_fetches=10)
            engine = _CustomEngine()
            with pytest.raises(Exception):
                engine.run(_make_plan())
