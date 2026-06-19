from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Protocol

import httpx

from .types import (
    EMPTY_CONTENT_THRESHOLD,
    ArticleDocument,
    BudgetExhaustedError,
    FetchBlockedError,
    FetchEmptyContentError,
    FetchResult,
    FetchTimeoutError,
    SearchQuery,
    SearchResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML content extraction helpers
# ---------------------------------------------------------------------------

_SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "aside"})


class _ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self._text_parts: list[str] = []
        self._skip_depth: int = 0
        self._in_title: bool = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self.title = stripped
        elif self._skip_depth == 0:
            self._text_parts.append(stripped)

    @property
    def text(self) -> str:
        return "\n".join(self._text_parts)


def _extract_article_content(html: str) -> tuple[str, str]:
    parser = _ArticleHTMLParser()
    parser.feed(html)
    return parser.title, parser.text


def _normalize_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ---------------------------------------------------------------------------
# SearchProvider protocol
# ---------------------------------------------------------------------------

class SearchProvider(Protocol):
    def search(self, query: str, timeout: float) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# Stub fetcher (from issue #17)
# ---------------------------------------------------------------------------

class StubFetcher:
    """Deterministic stub fetcher that returns fixed fake results without network calls."""

    def fetch(self, query: SearchQuery) -> FetchResult:
        return FetchResult(query=query, content=f"[stub] result for: {query.query}")


# ---------------------------------------------------------------------------
# Base class with budget management
# ---------------------------------------------------------------------------

class ResearchFetcherBase:
    def __init__(self, budget: int, timeout: float = 10.0) -> None:
        self.budget = budget
        self.timeout = timeout

    def _consume_budget(self) -> None:
        if self.budget <= 0:
            raise BudgetExhaustedError("Fetch budget exhausted")
        self.budget -= 1


# ---------------------------------------------------------------------------
# WebSearchFetcher
# ---------------------------------------------------------------------------

class WebSearchFetcher(ResearchFetcherBase):
    """Fetcher that resolves a query string into a list of {url, title} results."""

    def __init__(self, provider: SearchProvider, budget: int, timeout: float = 10.0) -> None:
        super().__init__(budget, timeout)
        self._provider = provider

    def fetch(self, query: str) -> list[SearchResult]:
        self._consume_budget()
        return self._provider.search(query, self.timeout)


# ---------------------------------------------------------------------------
# ArticleReaderFetcher
# ---------------------------------------------------------------------------

class ArticleReaderFetcher(ResearchFetcherBase):
    """Fetcher that retrieves a URL and extracts its readable main text and title."""

    def __init__(
        self,
        budget: int,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(budget, timeout)
        self._http = http_client

    def fetch(self, url: str) -> ArticleDocument:
        self._consume_budget()
        client = self._http or httpx.Client()
        try:
            response = client.get(url, timeout=self.timeout, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise FetchTimeoutError(f"Timeout fetching {url}: {exc}") from exc

        if response.status_code >= 400:
            raise FetchBlockedError(
                f"HTTP {response.status_code} fetching {url}"
            )

        title, raw_text = _extract_article_content(response.text)
        normalized = _normalize_text(raw_text)

        if len(normalized) < EMPTY_CONTENT_THRESHOLD:
            raise FetchEmptyContentError(
                f"Insufficient content at {url} ({len(normalized)} chars)"
            )

        return ArticleDocument(url=url, title=title, text=normalized)


# ---------------------------------------------------------------------------
# DuckDuckGo search provider (production implementation)
# ---------------------------------------------------------------------------

class DuckDuckGoSearchProvider:
    """Search provider using DuckDuckGo Lite HTML endpoint (no API key required)."""

    _DDG_URL = "https://lite.duckduckgo.com/lite/"

    def search(self, query: str, timeout: float) -> list[SearchResult]:
        try:
            response = httpx.get(
                self._DDG_URL,
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; crux-research/1.0)"},
                timeout=timeout,
                follow_redirects=True,
            )
        except httpx.TimeoutException as exc:
            raise FetchTimeoutError(f"DDG search timed out: {exc}") from exc

        if response.status_code >= 400:
            raise FetchBlockedError(f"DDG returned HTTP {response.status_code}")

        return _parse_ddg_lite_results(response.text)


def _parse_ddg_lite_results(html: str) -> list[SearchResult]:
    results: list[SearchResult] = []

    class _DDGParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._current_url: str | None = None
            self._current_title_parts: list[str] = []
            self._in_result_link: bool = False

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag != "a":
                return
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            cls = attrs_dict.get("class", "")
            if href.startswith("http") and "result-link" in cls:
                self._current_url = href
                self._current_title_parts = []
                self._in_result_link = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "a" and self._in_result_link:
                if self._current_url:
                    title = " ".join(self._current_title_parts).strip()
                    results.append(SearchResult(url=self._current_url, title=title))
                self._in_result_link = False
                self._current_url = None

        def handle_data(self, data: str) -> None:
            if self._in_result_link and data.strip():
                self._current_title_parts.append(data.strip())

    parser = _DDGParser()
    parser.feed(html)
    return results
