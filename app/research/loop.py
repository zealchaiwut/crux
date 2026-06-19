from __future__ import annotations

from .config import ResearchConfig
from .types import Extractor, FetchResult, Fetcher, Plan, QueryPlanner, SearchQuery, Synthesiser


class _NoopExtractor:
    def extract(self, result: FetchResult) -> str:
        return result.content


class _NoopSynthesiser:
    def synthesise(self, extracts: list[str]) -> str:
        return "\n".join(extracts)


def runResearchLoop(
    plan: Plan,
    config: ResearchConfig,
    *,
    planner: QueryPlanner,
    fetcher: Fetcher,
    extractor: Extractor | None = None,
    synthesiser: Synthesiser | None = None,
) -> dict:
    """Execute query-planner → fetchers (extractor and synthesiser are no-ops by default)."""
    _extractor = extractor or _NoopExtractor()
    _synthesiser = synthesiser or _NoopSynthesiser()

    queries = planner.plan(plan)
    results: list[FetchResult] = []

    for query in queries[: config.max_fetches]:
        result = fetcher.fetch(query)
        results.append(result)

    extracts = [_extractor.extract(r) for r in results]
    synthesis = _synthesiser.synthesise(extracts)

    return {
        "queries": queries,
        "results": results,
        "extracts": extracts,
        "synthesis": synthesis,
    }
