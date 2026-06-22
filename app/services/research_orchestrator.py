"""Research orchestrator: runs the full research pipeline for a single Plan.

Pipeline: query-planner → fetchers → extractor → synthesiser.
Engine selection is controlled by RESEARCH_ENGINE config (§11):
  "custom"   — LLMQueryPlanner + WebSearchFetcher + ClaimExtractor + CitationSynthesiser
  "fallback" — StubFetcher-based engine that returns no sources (graceful no-op)
"""
from __future__ import annotations

import logging
import uuid as _uuid_mod
from typing import Protocol, runtime_checkable

from app.research.types import Plan as ResearchPlan, Source

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Raised when the research pipeline fails for a plan."""


@runtime_checkable
class ResearchEngine(Protocol):
    def run(self, plan: ResearchPlan) -> list[Source]: ...


# ---------------------------------------------------------------------------
# Fallback engine — returns an empty source list without touching external APIs
# ---------------------------------------------------------------------------

class _FallbackEngine:
    """Borrowed/fallback engine: returns empty results transparently (§11)."""

    def run(self, plan: ResearchPlan) -> list[Source]:
        logger.info(
            "FallbackEngine: no sources produced for plan mechanism=%r", plan.mechanism
        )
        return []


# ---------------------------------------------------------------------------
# Custom engine — full LLM+web pipeline
# ---------------------------------------------------------------------------

class _CustomEngine:
    """Custom research engine: query-planner → fetchers → extractor → synthesiser."""

    def __init__(self, anthropic_client=None) -> None:
        self._anthropic_client = anthropic_client

    def run(self, plan: ResearchPlan) -> list[Source]:
        import re as _re
        from app.research import (
            LLMQueryPlanner,
            WebSearchFetcher,
            ArticleReaderFetcher,
            YouTubeTranscriptFetcher,
            DuckDuckGoSearchProvider,
            ClaimExtractor,
            CitationSynthesiser,
            ResearchConfig,
        )
        from app.research.types import SourceDocument

        client = self._anthropic_client
        if client is None:
            from app.claude_cli import ClaudeCLIClient
            client = ClaudeCLIClient()

        def _llm_callable(prompt: str) -> str:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        config = ResearchConfig.from_env()
        planner = LLMQueryPlanner(llm=_llm_callable)
        extractor = ClaimExtractor()
        synthesiser = CitationSynthesiser(client=client)

        queries = planner.plan(plan)
        if not queries:
            return []

        search_fetcher = WebSearchFetcher(
            provider=DuckDuckGoSearchProvider(),
            budget=len(queries),
            timeout=10.0,
        )
        article_fetcher = ArticleReaderFetcher(budget=config.max_fetches, timeout=10.0)
        yt_fetcher = YouTubeTranscriptFetcher(budget=config.max_fetches, timeout=10.0)

        _YT_RE = _re.compile(r"(?:youtube\.com|youtu\.be)")

        # Discovery: web-search each query to get candidate URLs
        all_candidates = []
        for query in queries:
            try:
                results = search_fetcher.fetch(query.query)
                all_candidates.extend(results)
            except Exception as exc:
                logger.warning("CustomEngine: search failed for query %r: %s", query.query, exc)

        # Cap total read-fetches by config
        candidates_to_read = all_candidates[: config.max_fetches]

        # Read step: fetch each candidate; skip on failure
        fetched_candidates: list[dict] = []
        for candidate in candidates_to_read:
            url = candidate.url
            is_yt = bool(_YT_RE.search(url))
            try:
                if is_yt:
                    doc = yt_fetcher.fetch(url)
                    if doc is None:
                        logger.warning("CustomEngine: transcript unavailable for %s", url)
                        continue
                else:
                    doc = article_fetcher.fetch(url)

                src_doc = SourceDocument(
                    kind="youtube" if is_yt else "article",
                    title=doc.title or candidate.title,
                    url=doc.url,
                    text=doc.text,
                )
                claims = extractor.extract(src_doc)
                for claim in claims:
                    fetched_candidates.append({
                        "kind": src_doc.kind,
                        "title": src_doc.title,
                        "url": src_doc.url,
                        "claim": claim,
                    })
            except Exception as exc:
                logger.warning("CustomEngine: fetch failed for %s: %s", url, exc)
                continue

        if not fetched_candidates:
            return []

        return synthesiser.synthesise(plan, fetched_candidates)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def make_engine(engine_name: str, anthropic_client=None) -> ResearchEngine:
    """Return the appropriate research engine for the given config name (§11)."""
    if engine_name == "fallback":
        return _FallbackEngine()
    return _CustomEngine(anthropic_client=anthropic_client)


def run_research_for_plan(
    plan_mechanism: str,
    plan_prior: str,
    engine: ResearchEngine,
) -> list[Source]:
    """Run the research pipeline for one plan and return Source objects.

    Raises OrchestratorError on unrecoverable failure.
    """
    research_plan = ResearchPlan(
        mechanism=plan_mechanism or "",
        prior=plan_prior or "",
    )
    try:
        return engine.run(research_plan)
    except OrchestratorError:
        raise
    except Exception as exc:
        raise OrchestratorError(f"Research pipeline failed: {exc}") from exc


# ---------------------------------------------------------------------------
# In-memory gather status store (single-user app — no persistence needed)
# ---------------------------------------------------------------------------

GatherStatus = str  # "idle" | "running" | "done" | "empty" | "error"


class _GatherStatusStore:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def set(self, plan_id: str, status: GatherStatus, error: str = "") -> None:
        self._data[plan_id] = {"status": status, "error": error}

    def get(self, plan_id: str) -> dict:
        return self._data.get(plan_id, {"status": "idle", "error": ""})

    def clear(self, plan_id: str) -> None:
        self._data.pop(plan_id, None)

    def reset(self) -> None:
        self._data.clear()


gather_status_store = _GatherStatusStore()
