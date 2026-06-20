"""Tests for issue #18: web-search and article-reader fetchers."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared HTML fixtures
# ---------------------------------------------------------------------------

ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Article Title</title></head>
<body>
<nav>Navigation menu — skip me</nav>
<main>
<h1>Main Heading</h1>
<p>This is the main content of the article. It has more than one hundred
characters of substantial body text to pass the minimum content threshold.</p>
<p>Second paragraph with additional information to confirm multi-paragraph
extraction works correctly.</p>
</main>
<footer>Footer boilerplate — skip me</footer>
</body>
</html>"""

WHITESPACE_HTML = """<!DOCTYPE html>
<html>
<head><title>Whitespace Test</title></head>
<body>
<p>  First paragraph with surrounding whitespace and enough content to pass the minimum threshold.  </p>

<p></p>

<p></p>

<p>Second paragraph comes after multiple blank lines with additional text to exceed one hundred characters total.</p>
</body>
</html>"""

THIN_HTML = """<!DOCTYPE html>
<html>
<head><title>Thin Page</title></head>
<body><p>Hi.</p></body>
</html>"""


# ---------------------------------------------------------------------------
# AC1: WebSearchFetcher returns ordered list of {url, title}
# ---------------------------------------------------------------------------

def test_web_search_fetcher_returns_search_results():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import SearchResult

    provider = MagicMock()
    provider.search.return_value = [
        SearchResult(url="https://example.com/1", title="Result One"),
        SearchResult(url="https://example.com/2", title="Result Two"),
    ]

    fetcher = WebSearchFetcher(provider=provider, budget=5)
    results = fetcher.fetch("test query")

    assert len(results) == 2
    assert all(isinstance(r, SearchResult) for r in results)
    assert results[0].url == "https://example.com/1"
    assert results[0].title == "Result One"


def test_web_search_fetcher_preserves_result_order():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import SearchResult

    expected = [
        SearchResult(url=f"https://example.com/{i}", title=f"Result {i}")
        for i in range(5)
    ]
    provider = MagicMock()
    provider.search.return_value = expected

    fetcher = WebSearchFetcher(provider=provider, budget=5)
    results = fetcher.fetch("ordering test")

    assert [r.url for r in results] == [r.url for r in expected]


def test_web_search_fetcher_passes_query_to_provider():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import SearchResult

    provider = MagicMock()
    provider.search.return_value = [SearchResult(url="https://x.com", title="X")]

    fetcher = WebSearchFetcher(provider=provider, budget=5)
    fetcher.fetch("my exact query")

    provider.search.assert_called_once()
    call_args = provider.search.call_args
    assert call_args[0][0] == "my exact query"


# ---------------------------------------------------------------------------
# AC2: ArticleReaderFetcher returns {url, title, text}
# ---------------------------------------------------------------------------

def test_article_reader_returns_document():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import ArticleDocument

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ARTICLE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    doc = fetcher.fetch("https://example.com/article")

    assert isinstance(doc, ArticleDocument)
    assert doc.url == "https://example.com/article"
    assert "Test Article Title" in doc.title or len(doc.title) > 0
    assert len(doc.text) >= 100


def test_article_reader_returns_non_empty_title():
    from app.research.fetchers import ArticleReaderFetcher

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ARTICLE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    doc = fetcher.fetch("https://example.com/article")

    assert doc.title.strip() != ""


# ---------------------------------------------------------------------------
# AC3: Both implement ResearchFetcher interface
# ---------------------------------------------------------------------------

def test_web_search_fetcher_implements_research_fetcher():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import ResearchFetcher

    provider = MagicMock()
    provider.search.return_value = []
    fetcher = WebSearchFetcher(provider=provider, budget=3)

    assert isinstance(fetcher, ResearchFetcher)
    assert hasattr(fetcher, "budget")


def test_article_reader_fetcher_implements_research_fetcher():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import ResearchFetcher

    fetcher = ArticleReaderFetcher(budget=3)

    assert isinstance(fetcher, ResearchFetcher)
    assert hasattr(fetcher, "budget")


# ---------------------------------------------------------------------------
# AC4: Timeout raises FetchTimeoutError (default 10 s)
# ---------------------------------------------------------------------------

def test_web_search_fetcher_raises_timeout_error():
    import httpx
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import FetchTimeoutError

    provider = MagicMock()
    provider.search.side_effect = FetchTimeoutError("search timed out")

    fetcher = WebSearchFetcher(provider=provider, budget=5)
    with pytest.raises(FetchTimeoutError):
        fetcher.fetch("slow query")


def test_article_reader_raises_timeout_error():
    import httpx
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchTimeoutError

    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("read timeout")

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchTimeoutError):
        fetcher.fetch("https://slow.example.com")


def test_fetcher_default_timeout_is_ten_seconds():
    from app.research.fetchers import ArticleReaderFetcher

    fetcher = ArticleReaderFetcher(budget=5)
    assert fetcher.timeout == 10.0


# ---------------------------------------------------------------------------
# AC5: Non-2xx / blocked status codes raise FetchBlockedError
# ---------------------------------------------------------------------------

def test_article_reader_raises_blocked_on_403():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchBlockedError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchBlockedError):
        fetcher.fetch("https://blocked.example.com")


def test_article_reader_raises_blocked_on_429():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchBlockedError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchBlockedError):
        fetcher.fetch("https://ratelimited.example.com")


def test_article_reader_raises_blocked_on_500():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchBlockedError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchBlockedError):
        fetcher.fetch("https://error.example.com")


def test_web_search_fetcher_propagates_blocked_error():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import FetchBlockedError

    provider = MagicMock()
    provider.search.side_effect = FetchBlockedError("search blocked")

    fetcher = WebSearchFetcher(provider=provider, budget=5)
    with pytest.raises(FetchBlockedError):
        fetcher.fetch("blocked query")


# ---------------------------------------------------------------------------
# AC6: Empty / near-empty bodies raise FetchEmptyContentError
# ---------------------------------------------------------------------------

def test_article_reader_raises_empty_content_on_short_text():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchEmptyContentError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = THIN_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchEmptyContentError):
        fetcher.fetch("https://thin.example.com")


def test_article_reader_raises_empty_content_on_blank_body():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchEmptyContentError

    blank_html = "<html><head><title>Blank</title></head><body></body></html>"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = blank_html
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    with pytest.raises(FetchEmptyContentError):
        fetcher.fetch("https://empty.example.com")


def test_empty_content_threshold_is_100_characters():
    from app.research.types import EMPTY_CONTENT_THRESHOLD
    assert EMPTY_CONTENT_THRESHOLD == 100


# ---------------------------------------------------------------------------
# AC7: Budget decrements on every attempt; BudgetExhaustedError at zero
# ---------------------------------------------------------------------------

def test_web_search_budget_decrements_on_success():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import SearchResult

    provider = MagicMock()
    provider.search.return_value = [SearchResult(url="https://x.com", title="X")]

    fetcher = WebSearchFetcher(provider=provider, budget=3)
    fetcher.fetch("q1")
    assert fetcher.budget == 2
    fetcher.fetch("q2")
    assert fetcher.budget == 1


def test_web_search_budget_decrements_on_timeout_failure():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import FetchTimeoutError

    provider = MagicMock()
    provider.search.side_effect = FetchTimeoutError("timeout")

    fetcher = WebSearchFetcher(provider=provider, budget=3)
    with pytest.raises(FetchTimeoutError):
        fetcher.fetch("q1")

    assert fetcher.budget == 2


def test_web_search_raises_budget_exhausted_at_zero():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import BudgetExhaustedError

    provider = MagicMock()
    fetcher = WebSearchFetcher(provider=provider, budget=0)

    with pytest.raises(BudgetExhaustedError):
        fetcher.fetch("any query")

    provider.search.assert_not_called()


def test_web_search_no_network_call_when_budget_zero():
    from app.research.fetchers import WebSearchFetcher
    from app.research.types import BudgetExhaustedError, SearchResult

    provider = MagicMock()
    provider.search.return_value = [SearchResult(url="https://x.com", title="X")]

    fetcher = WebSearchFetcher(provider=provider, budget=1)
    fetcher.fetch("first")          # consumes budget
    assert fetcher.budget == 0

    with pytest.raises(BudgetExhaustedError):
        fetcher.fetch("second")     # must not call provider

    assert provider.search.call_count == 1  # only the first call went through


def test_article_reader_budget_decrements_on_success():
    from app.research.fetchers import ArticleReaderFetcher

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ARTICLE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=3, http_client=mock_client)
    fetcher.fetch("https://example.com/a")
    assert fetcher.budget == 2


def test_article_reader_budget_decrements_on_failure():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import FetchBlockedError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=3, http_client=mock_client)
    with pytest.raises(FetchBlockedError):
        fetcher.fetch("https://blocked.example.com")

    assert fetcher.budget == 2


def test_article_reader_raises_budget_exhausted_at_zero():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import BudgetExhaustedError

    mock_client = MagicMock()
    fetcher = ArticleReaderFetcher(budget=0, http_client=mock_client)

    with pytest.raises(BudgetExhaustedError):
        fetcher.fetch("https://example.com")

    mock_client.get.assert_not_called()


def test_article_reader_no_network_call_when_budget_zero():
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import BudgetExhaustedError

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ARTICLE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=1, http_client=mock_client)
    fetcher.fetch("https://example.com/a")  # consumes budget
    assert fetcher.budget == 0

    with pytest.raises(BudgetExhaustedError):
        fetcher.fetch("https://example.com/b")

    assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# AC8: Errors caught at loop level without crashing
# ---------------------------------------------------------------------------

def test_loop_continues_after_fetch_blocked_error():
    from app.research.loop import runResearchLoop
    from app.research.config import ResearchConfig
    from app.research.types import Plan, SearchQuery, FetchResult, FetchBlockedError
    from app.research.planner import LLMQueryPlanner

    call_count = 0

    class _ErrorThenOkFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FetchBlockedError("blocked on first")
            return FetchResult(query=query, content="ok content")

    planner = LLMQueryPlanner(llm=lambda _: "q1\nq2")
    result = runResearchLoop(
        Plan(mechanism="m", prior="p"),
        ResearchConfig(max_fetches=5),
        planner=planner,
        fetcher=_ErrorThenOkFetcher(),
    )
    assert call_count == 2
    assert len(result["results"]) == 1


def test_loop_continues_after_fetch_timeout_error():
    from app.research.loop import runResearchLoop
    from app.research.config import ResearchConfig
    from app.research.types import Plan, SearchQuery, FetchResult, FetchTimeoutError
    from app.research.planner import LLMQueryPlanner

    call_count = 0

    class _TimeoutThenOkFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FetchTimeoutError("timed out on first call")
            return FetchResult(query=query, content="ok on second call")

    planner = LLMQueryPlanner(llm=lambda _: "q1\nq2")
    result = runResearchLoop(
        Plan(mechanism="m", prior="p"),
        ResearchConfig(max_fetches=5),
        planner=planner,
        fetcher=_TimeoutThenOkFetcher(),
    )
    assert call_count == 2
    assert len(result["results"]) == 1


def test_loop_continues_after_fetch_empty_content_error():
    from app.research.loop import runResearchLoop
    from app.research.config import ResearchConfig
    from app.research.types import Plan, SearchQuery, FetchResult, FetchEmptyContentError
    from app.research.planner import LLMQueryPlanner

    class _EmptyThenOkFetcher:
        def __init__(self):
            self._calls = 0

        def fetch(self, query: SearchQuery) -> FetchResult:
            self._calls += 1
            if self._calls == 1:
                raise FetchEmptyContentError("empty")
            return FetchResult(query=query, content="substantial content here")

    planner = LLMQueryPlanner(llm=lambda _: "q1\nq2")
    result = runResearchLoop(
        Plan(mechanism="m", prior="p"),
        ResearchConfig(max_fetches=5),
        planner=planner,
        fetcher=_EmptyThenOkFetcher(),
    )
    assert len(result["results"]) == 1


def test_loop_stops_on_budget_exhausted_error():
    from app.research.loop import runResearchLoop
    from app.research.config import ResearchConfig
    from app.research.types import Plan, SearchQuery, FetchResult, BudgetExhaustedError
    from app.research.planner import LLMQueryPlanner

    call_count = 0

    class _BudgetExhaustedFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FetchResult(query=query, content="first ok")
            raise BudgetExhaustedError("budget gone")

    planner = LLMQueryPlanner(llm=lambda _: "q1\nq2\nq3")
    result = runResearchLoop(
        Plan(mechanism="m", prior="p"),
        ResearchConfig(max_fetches=5),
        planner=planner,
        fetcher=_BudgetExhaustedFetcher(),
    )
    assert call_count == 2
    assert len(result["results"]) == 1  # only first succeeded


# ---------------------------------------------------------------------------
# AC9: Text normalization — trimmed whitespace, collapsed blank lines
# ---------------------------------------------------------------------------

def test_article_text_has_no_leading_trailing_whitespace():
    from app.research.fetchers import ArticleReaderFetcher

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = WHITESPACE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    doc = fetcher.fetch("https://example.com/ws")

    assert doc.text == doc.text.strip()


def test_article_text_has_no_consecutive_blank_lines():
    from app.research.fetchers import ArticleReaderFetcher

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = WHITESPACE_HTML
    mock_client.get.return_value = mock_response

    fetcher = ArticleReaderFetcher(budget=5, http_client=mock_client)
    doc = fetcher.fetch("https://example.com/ws")

    assert "\n\n\n" not in doc.text


def test_normalize_text_utility():
    from app.research.fetchers import _normalize_text

    raw = "  hello  \n\n\n\n  world  \n\n\n"
    result = _normalize_text(raw)

    assert not result.startswith(" ")
    assert not result.endswith(" ")
    assert not result.endswith("\n")
    assert "\n\n\n" not in result
