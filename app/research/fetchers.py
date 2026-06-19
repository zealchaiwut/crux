from __future__ import annotations

from .types import FetchResult, SearchQuery


class StubFetcher:
    """Deterministic stub fetcher that returns fixed fake results without network calls."""

    def fetch(self, query: SearchQuery) -> FetchResult:
        return FetchResult(query=query, content=f"[stub] result for: {query.query}")
