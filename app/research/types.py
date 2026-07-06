from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

SourceKind = Literal["book", "article", "youtube", "podcast"]

EMPTY_CONTENT_THRESHOLD = 100


@dataclass
class Plan:
    mechanism: str
    prior: str


@dataclass
class SearchQuery:
    query: str


@dataclass
class FetchResult:
    query: SearchQuery
    content: str


@dataclass
class SearchResult:
    url: str
    title: str


@dataclass
class ArticleDocument:
    url: str
    title: str
    text: str


@dataclass
class SourceDocument:
    """A fetched document with its metadata, ready for claim extraction."""

    kind: SourceKind
    title: str
    url: str
    text: str


@dataclass
class Source:
    """A single evidence row matching the `source` DB table schema."""

    kind: SourceKind
    title: str
    url: str
    claim: str
    citation: str


class FetchTimeoutError(Exception):
    pass


class FetchBlockedError(Exception):
    pass


class FetchRateLimitError(Exception):
    pass


class FetchEmptyContentError(Exception):
    pass


class BudgetExhaustedError(Exception):
    pass


@runtime_checkable
class ResearchFetcher(Protocol):
    budget: int


@runtime_checkable
class QueryPlanner(Protocol):
    def plan(self, plan: Plan) -> list[SearchQuery]: ...


@runtime_checkable
class Fetcher(Protocol):
    def fetch(self, query: SearchQuery) -> FetchResult: ...


@runtime_checkable
class Extractor(Protocol):
    def extract(self, result: FetchResult) -> str: ...


@runtime_checkable
class Synthesiser(Protocol):
    def synthesise(self, extracts: list[str]) -> str: ...
