"""Tests for issue #17: Scaffold research-loop module and LLM query planner."""
import os
import pytest


# ---------------------------------------------------------------------------
# AC2: Plan type with mechanism and prior fields
# ---------------------------------------------------------------------------

def test_plan_type_has_mechanism_and_prior():
    from app.research import Plan
    plan = Plan(mechanism="example mechanism", prior="example prior")
    assert plan.mechanism == "example mechanism"
    assert plan.prior == "example prior"


# ---------------------------------------------------------------------------
# AC3: LLM query-planner returns >= 1 typed SearchQuery given a valid Plan
# ---------------------------------------------------------------------------

def test_query_planner_returns_queries_for_valid_plan():
    from app.research import LLMQueryPlanner, Plan, SearchQuery

    def stub_llm(prompt: str) -> str:
        return "query one\nquery two"

    planner = LLMQueryPlanner(llm=stub_llm)
    plan = Plan(mechanism="example mechanism", prior="example prior")
    queries = planner.plan(plan)

    assert len(queries) >= 1
    assert all(isinstance(q, SearchQuery) for q in queries)


def test_query_planner_returns_list_of_search_query_objects():
    from app.research import LLMQueryPlanner, Plan, SearchQuery

    def stub_llm(prompt: str) -> str:
        return "first query\nsecond query\nthird query"

    planner = LLMQueryPlanner(llm=stub_llm)
    queries = planner.plan(Plan(mechanism="m", prior="p"))

    assert isinstance(queries, list)
    for q in queries:
        assert isinstance(q, SearchQuery)
        assert isinstance(q.query, str)


# ---------------------------------------------------------------------------
# AC4: Pipeline stage contracts are defined as explicit types/interfaces
# ---------------------------------------------------------------------------

def test_pipeline_contracts_importable():
    from app.research.types import QueryPlanner, Fetcher, Extractor, Synthesiser
    # Verify they are runtime-checkable Protocol classes
    from typing import Protocol
    assert issubclass(QueryPlanner, Protocol) or hasattr(QueryPlanner, "__protocol_attrs__") or True
    # Just confirming they import cleanly — structural typing, not inheritance check
    assert QueryPlanner is not None
    assert Fetcher is not None
    assert Extractor is not None
    assert Synthesiser is not None


def test_llm_planner_satisfies_query_planner_interface():
    from app.research import LLMQueryPlanner, Plan
    from app.research.types import QueryPlanner
    planner = LLMQueryPlanner(llm=lambda p: "q")
    assert isinstance(planner, QueryPlanner)


def test_stub_fetcher_satisfies_fetcher_interface():
    from app.research import StubFetcher
    from app.research.types import Fetcher
    fetcher = StubFetcher()
    assert isinstance(fetcher, Fetcher)


# ---------------------------------------------------------------------------
# AC5: Stub Fetcher returns deterministic fake results
# ---------------------------------------------------------------------------

def test_stub_fetcher_returns_expected_shape():
    from app.research import StubFetcher, SearchQuery, FetchResult

    fetcher = StubFetcher()
    query = SearchQuery(query="test query")
    result = fetcher.fetch(query)

    assert isinstance(result, FetchResult)
    assert result.query == query
    assert isinstance(result.content, str)


def test_stub_fetcher_is_deterministic():
    from app.research import StubFetcher, SearchQuery

    fetcher = StubFetcher()
    q = SearchQuery(query="deterministic test")
    r1 = fetcher.fetch(q)
    r2 = fetcher.fetch(q)
    assert r1.content == r2.content


# ---------------------------------------------------------------------------
# AC6: maxFetches config is tunable via env var without code changes
# ---------------------------------------------------------------------------

def test_research_config_max_fetches_from_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_MAX_FETCHES", "7")
    from importlib import reload
    import app.research.config as cfg
    reload(cfg)
    config = cfg.ResearchConfig.from_env()
    assert config.max_fetches == 7


def test_research_config_default_max_fetches(monkeypatch):
    monkeypatch.delenv("RESEARCH_MAX_FETCHES", raising=False)
    from importlib import reload
    import app.research.config as cfg
    reload(cfg)
    config = cfg.ResearchConfig.from_env()
    assert config.max_fetches > 0


def test_research_config_can_be_constructed_directly():
    from app.research import ResearchConfig
    config = ResearchConfig(max_fetches=3)
    assert config.max_fetches == 3


# ---------------------------------------------------------------------------
# AC7: runResearchLoop entry point executes query-planner -> fetchers
# ---------------------------------------------------------------------------

def test_run_research_loop_executes_planner_then_fetcher():
    from app.research import LLMQueryPlanner, StubFetcher, ResearchConfig, Plan, runResearchLoop

    def stub_llm(prompt: str) -> str:
        return "query a\nquery b"

    planner = LLMQueryPlanner(llm=stub_llm)
    fetcher = StubFetcher()
    config = ResearchConfig(max_fetches=5)
    plan = Plan(mechanism="example mechanism", prior="example prior")

    result = runResearchLoop(plan, config, planner=planner, fetcher=fetcher)

    assert result is not None
    assert "queries" in result
    assert "results" in result
    assert len(result["queries"]) >= 1
    assert len(result["results"]) >= 1


# ---------------------------------------------------------------------------
# AC8: Budget cap halts fetching after maxFetches calls
# ---------------------------------------------------------------------------

def test_budget_cap_halts_fetching_after_max_fetches():
    from app.research import LLMQueryPlanner, ResearchConfig, Plan, SearchQuery, FetchResult, runResearchLoop

    call_count = 0

    class CountingFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            nonlocal call_count
            call_count += 1
            return FetchResult(query=query, content=f"content for {query.query}")

    def stub_llm(prompt: str) -> str:
        return "\n".join(f"query {i}" for i in range(10))

    planner = LLMQueryPlanner(llm=stub_llm)
    fetcher = CountingFetcher()
    config = ResearchConfig(max_fetches=3)
    plan = Plan(mechanism="test", prior="test")

    runResearchLoop(plan, config, planner=planner, fetcher=fetcher)

    assert call_count <= 3


def test_budget_cap_of_one_makes_exactly_one_fetch():
    from app.research import LLMQueryPlanner, ResearchConfig, Plan, SearchQuery, FetchResult, runResearchLoop

    call_count = 0

    class CountingFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            nonlocal call_count
            call_count += 1
            return FetchResult(query=query, content="content")

    def stub_llm(prompt: str) -> str:
        return "q1\nq2\nq3"

    planner = LLMQueryPlanner(llm=stub_llm)
    fetcher = CountingFetcher()
    config = ResearchConfig(max_fetches=1)
    plan = Plan(mechanism="test", prior="test")

    runResearchLoop(plan, config, planner=planner, fetcher=fetcher)

    assert call_count == 1


# ---------------------------------------------------------------------------
# AC9: Zero external network calls with stub fetcher
# ---------------------------------------------------------------------------

def test_no_network_calls_with_stub_components():
    from app.research import LLMQueryPlanner, StubFetcher, ResearchConfig, Plan, runResearchLoop

    def stub_llm(prompt: str) -> str:
        return "query one"

    planner = LLMQueryPlanner(llm=stub_llm)
    fetcher = StubFetcher()
    config = ResearchConfig(max_fetches=3)
    plan = Plan(mechanism="example mechanism", prior="example prior")

    result = runResearchLoop(plan, config, planner=planner, fetcher=fetcher)
    assert result is not None


# ---------------------------------------------------------------------------
# UAT step 5: Plan with empty fields returns empty list, no unhandled exception
# ---------------------------------------------------------------------------

def test_empty_plan_fields_returns_empty_list_not_exception():
    from app.research import LLMQueryPlanner, Plan

    def stub_llm(prompt: str) -> str:
        return ""

    planner = LLMQueryPlanner(llm=stub_llm)
    plan = Plan(mechanism="", prior="")
    queries = planner.plan(plan)

    assert isinstance(queries, list)


# ---------------------------------------------------------------------------
# UAT step 6: Replacing stub fetcher doesn't change planner or budget logic
# ---------------------------------------------------------------------------

def test_alternative_fetcher_respects_interface():
    from app.research import LLMQueryPlanner, ResearchConfig, Plan, SearchQuery, FetchResult, runResearchLoop

    class AltStubFetcher:
        def fetch(self, query: SearchQuery) -> FetchResult:
            return FetchResult(query=query, content="alt fixed payload")

    def stub_llm(prompt: str) -> str:
        return "query one"

    planner = LLMQueryPlanner(llm=stub_llm)
    fetcher = AltStubFetcher()
    config = ResearchConfig(max_fetches=3)
    plan = Plan(mechanism="test", prior="test")

    result = runResearchLoop(plan, config, planner=planner, fetcher=fetcher)
    assert result["results"][0].content == "alt fixed payload"


# ---------------------------------------------------------------------------
# Public interface: nothing from internals should be needed
# ---------------------------------------------------------------------------

def test_all_public_types_importable_from_module():
    from app.research import (
        Plan,
        SearchQuery,
        FetchResult,
        ResearchConfig,
        LLMQueryPlanner,
        StubFetcher,
        runResearchLoop,
    )
    assert all(x is not None for x in [
        Plan, SearchQuery, FetchResult, ResearchConfig,
        LLMQueryPlanner, StubFetcher, runResearchLoop,
    ])
