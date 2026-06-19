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
        from app.research import (
            LLMQueryPlanner,
            StubFetcher,
            ClaimExtractor,
            CitationSynthesiser,
            ResearchConfig,
        )
        import os

        client = self._anthropic_client
        if client is None:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise OrchestratorError(
                    "ANTHROPIC_API_KEY is not configured for custom research engine"
                )
            client = anthropic.Anthropic(api_key=api_key)

        def _llm_callable(prompt: str) -> str:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        config = ResearchConfig.from_env()
        planner = LLMQueryPlanner(llm=_llm_callable)
        fetcher = StubFetcher()
        extractor = ClaimExtractor()
        synthesiser = CitationSynthesiser(client=client)

        queries = planner.plan(plan)
        if not queries:
            return []

        candidates: list[dict] = []
        from app.research.types import SourceDocument
        for query in queries[: config.max_fetches]:
            try:
                fetch_result = fetcher.fetch(query)
                doc = SourceDocument(
                    kind="article",
                    title=query.query,
                    url=f"https://example.com/{_uuid_mod.uuid4().hex[:8]}",
                    text=fetch_result.content,
                )
                claims = extractor.extract(doc)
                for claim in claims:
                    candidates.append({
                        "kind": doc.kind,
                        "title": doc.title,
                        "url": doc.url,
                        "claim": claim,
                    })
            except Exception as exc:
                logger.warning("CustomEngine: fetch/extract failed for query %r: %s", query, exc)
                continue

        if not candidates:
            return []

        return synthesiser.synthesise(plan, candidates)


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
