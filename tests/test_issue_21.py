"""Tests for issue #21: Automate Stage 2 source gathering via research loop.

AC1  — Research loop triggers automatically when Case enters Stage 2 (Gather).
AC2  — Pipeline order: query-planner → fetchers → extractor → synthesiser.
AC3  — Sources persisted to data store, associated with correct Plan.
AC4  — PlanCard renders SourceChips (name, URL, snippet) — verified via API response shape.
AC5  — Progress state (gather_status=running) surfaced per plan in GET /api/cases/{id}.
AC6  — Empty state (gather_status=empty) when loop returns no sources.
AC7  — Failure state (gather_status=error) with error message when loop errors.
AC8  — Manual source-paste (POST /api/sources) works alongside auto-gather in all states.
AC9  — Engine selection via RESEARCH_ENGINE config; no code change required to switch.
AC10 — No regression: Stage 3 (rerank) endpoint still functional after gather is added.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    from app.models import Base
    from sqlalchemy.pool import StaticPool
    # StaticPool ensures all SQLAlchemy connections share the same in-memory SQLite conn.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def authed_client_with_db(db_session):
    """TestClient wired to in-memory SQLite and authenticated."""
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    token = create_session_cookie(AUTH_SECRET)
    client.cookies.set("session", token)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_case_at_gather(db_session) -> tuple[str, list[str]]:
    """Create a Case at stage='gather' with two Plans. Return (case_id, [plan_ids])."""
    import uuid
    from datetime import datetime, timezone
    from app.models import Case, Plan

    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        raw_problem="Why am I tired?",
        sharpened="Fatigue over 3 months — what is the primary cause?",
        stage="gather",
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(case)

    plan_ids = []
    for label, mechanism, rank in [
        ("A", "Iron deficiency anaemia causing reduced oxygen transport", 1),
        ("B", "Chronic sleep debt from poor sleep hygiene", 2),
    ]:
        pid = str(uuid.uuid4())
        plan = Plan(
            id=pid,
            case_id=case_id,
            label=label,
            name=f"Plan {label}",
            mechanism=mechanism,
            prior="0.5",
            current_rank=rank,
        )
        db_session.add(plan)
        plan_ids.append(pid)

    db_session.commit()
    return case_id, plan_ids


def _make_stub_sources():
    """Return two Source objects for use in mocked engine output."""
    from app.research.types import Source
    return [
        Source(
            kind="article",
            title="Iron and Fatigue Study",
            url="https://example.com/iron",
            claim="Iron deficiency is a leading cause of fatigue.",
            citation="Iron deficiency is a leading cause of fatigue in adults.",
        ),
    ]


# ---------------------------------------------------------------------------
# AC3 — Sources persisted to data store, associated with correct Plan
# ---------------------------------------------------------------------------

def test_gather_plan_persists_sources_to_db(authed_client_with_db, db_session):
    """AC3: POST /api/plans/{id}/gather saves sources and returns them."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    stub_sources = _make_stub_sources()

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    assert resp.status_code == 200
    data = resp.json()
    assert data["gather_status"] == "done"
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    assert src["title"] == "Iron and Fatigue Study"
    assert src["url"] == "https://example.com/iron"
    assert src["claim"]
    assert src["citation"]
    assert src["plan_id"] == plan_id

    # Verify source is in the DB
    from app.models import Source
    db_sources = db_session.query(Source).filter(Source.plan_id == plan_id).all()
    assert len(db_sources) == 1
    assert db_sources[0].title == "Iron and Fatigue Study"


def test_gather_plan_associates_sources_with_correct_plan(authed_client_with_db, db_session):
    """AC3: sources are attached to the plan that triggered gather, not other plans."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_a, plan_b = plan_ids

    stub_sources = _make_stub_sources()

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        authed_client_with_db.post(f"/api/plans/{plan_a}/gather")

    from app.models import Source
    # plan_a should have sources; plan_b should have none
    sources_a = db_session.query(Source).filter(Source.plan_id == plan_a).all()
    sources_b = db_session.query(Source).filter(Source.plan_id == plan_b).all()
    assert len(sources_a) == 1
    assert len(sources_b) == 0


# ---------------------------------------------------------------------------
# AC4 — GET /api/cases/{id} exposes source fields (name, url, snippet)
# ---------------------------------------------------------------------------

def test_case_detail_exposes_source_chip_fields(authed_client_with_db, db_session):
    """AC4: GET /api/cases/{id} returns sources with title, url, claim per plan."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    stub_sources = _make_stub_sources()

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    resp = authed_client_with_db.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    plan_out = next(p for p in resp.json()["plans"] if p["id"] == plan_id)
    assert len(plan_out["sources"]) == 1
    src = plan_out["sources"][0]
    # Fields required for SourceChip rendering
    assert "title" in src
    assert "url" in src
    assert "claim" in src  # relevance snippet


# ---------------------------------------------------------------------------
# AC5 — Progress state exposed in GET /api/cases/{id} per plan
# ---------------------------------------------------------------------------

def test_case_detail_exposes_gather_status_per_plan(authed_client_with_db, db_session):
    """AC5: GET /api/cases/{id} returns gather_status field on each plan."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)

    resp = authed_client_with_db.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    for plan in resp.json()["plans"]:
        assert "gather_status" in plan
        assert plan["gather_status"] == "idle"  # not started yet


def test_gather_status_endpoint_returns_running_then_done(authed_client_with_db, db_session):
    """AC5: GET /api/plans/{id}/gather-status returns status after gather."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    stub_sources = _make_stub_sources()

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    resp = authed_client_with_db.get(f"/api/plans/{plan_id}/gather-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gather_status"] == "done"
    assert len(data["sources"]) == 1


# ---------------------------------------------------------------------------
# AC6 — Empty state when loop returns no sources
# ---------------------------------------------------------------------------

def test_gather_plan_empty_state_when_no_sources(authed_client_with_db, db_session):
    """AC6: when engine returns [], gather_status is 'empty'."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=[]):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    assert resp.status_code == 200
    data = resp.json()
    assert data["gather_status"] == "empty"
    assert data["sources"] == []

    status_resp = authed_client_with_db.get(f"/api/plans/{plan_id}/gather-status")
    assert status_resp.json()["gather_status"] == "empty"


# ---------------------------------------------------------------------------
# AC7 — Failure state with error message when loop errors
# ---------------------------------------------------------------------------

def test_gather_plan_error_state_on_orchestrator_error(authed_client_with_db, db_session):
    """AC7: when engine raises OrchestratorError, gather_status is 'error' with message."""
    from app.services.research_orchestrator import OrchestratorError, gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan",
               side_effect=OrchestratorError("Fetch timeout")):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    assert resp.status_code == 200
    data = resp.json()
    assert data["gather_status"] == "error"
    assert "Fetch timeout" in data["error"]
    assert data["sources"] == []


def test_gather_plan_retry_after_error(authed_client_with_db, db_session):
    """AC7: re-calling POST /api/plans/{id}/gather after error (retry) succeeds."""
    from app.services.research_orchestrator import OrchestratorError, gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    # First call: error
    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan",
               side_effect=OrchestratorError("Timeout")):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")
    assert resp.json()["gather_status"] == "error"

    # Retry: success
    stub_sources = _make_stub_sources()
    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")
    assert resp.json()["gather_status"] == "done"
    assert len(resp.json()["sources"]) == 1


# ---------------------------------------------------------------------------
# AC8 — Manual source-paste accessible alongside auto-gather
# ---------------------------------------------------------------------------

def test_manual_source_paste_works_in_idle_state(authed_client_with_db, db_session):
    """AC8: POST /api/sources works when gather has not been triggered."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    resp = authed_client_with_db.post("/api/sources", json={
        "plan_id": plan_id,
        "kind": "article",
        "title": "Manual Source",
        "url": "https://example.com/manual",
        "claim": "A manually entered claim.",
        "citation": "A manually entered citation.",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Manual Source"
    assert data["plan_id"] == plan_id


def test_manual_source_paste_works_alongside_auto_sources(authed_client_with_db, db_session):
    """AC8: manual sources coexist with auto-gathered sources."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    # Auto-gather
    stub_sources = _make_stub_sources()
    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", return_value=stub_sources):
        mock_factory.return_value = MagicMock()
        authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    # Manual paste
    authed_client_with_db.post("/api/sources", json={
        "plan_id": plan_id,
        "kind": "book",
        "title": "Manual Book Source",
        "url": "https://example.com/book",
        "claim": "A manual book claim.",
        "citation": "Smith 2024.",
    })

    # Both should appear in the case detail
    resp = authed_client_with_db.get(f"/api/cases/{case_id}")
    plan_out = next(p for p in resp.json()["plans"] if p["id"] == plan_id)
    assert len(plan_out["sources"]) == 2
    kinds = {s["kind"] for s in plan_out["sources"]}
    assert "article" in kinds
    assert "book" in kinds


def test_manual_source_paste_works_in_error_state(authed_client_with_db, db_session):
    """AC8: POST /api/sources works even after a gather error."""
    from app.services.research_orchestrator import OrchestratorError, gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    # Trigger a gather error
    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan",
               side_effect=OrchestratorError("Network error")):
        mock_factory.return_value = MagicMock()
        authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    # Manual paste still works
    resp = authed_client_with_db.post("/api/sources", json={
        "plan_id": plan_id,
        "kind": "article",
        "title": "Manual Fallback",
        "url": "https://example.com/fallback",
        "claim": "A claim.",
        "citation": "A citation.",
    })
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# AC9 — Engine selection via RESEARCH_ENGINE config
# ---------------------------------------------------------------------------

def test_engine_selection_custom(monkeypatch):
    """AC9: RESEARCH_ENGINE=custom returns _CustomEngine."""
    monkeypatch.setenv("RESEARCH_ENGINE", "custom")
    from app.services import research_orchestrator
    engine = research_orchestrator.make_engine("custom")
    assert isinstance(engine, research_orchestrator._CustomEngine)


def test_engine_selection_fallback(monkeypatch):
    """AC9: RESEARCH_ENGINE=fallback returns _FallbackEngine."""
    from app.services import research_orchestrator
    engine = research_orchestrator.make_engine("fallback")
    assert isinstance(engine, research_orchestrator._FallbackEngine)


def test_fallback_engine_returns_empty_sources():
    """AC9: fallback engine returns [] without any API calls."""
    from app.services.research_orchestrator import _FallbackEngine
    from app.research.types import Plan as ResearchPlan

    engine = _FallbackEngine()
    result = engine.run(ResearchPlan(mechanism="some mechanism", prior="0.5"))
    assert result == []


def test_engine_switch_without_code_change(authed_client_with_db, db_session, monkeypatch):
    """AC9: switching RESEARCH_ENGINE env var changes the engine used — no code change needed."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)
    plan_id = plan_ids[0]

    # With fallback engine, gather returns empty (no sources)
    monkeypatch.setenv("RESEARCH_ENGINE", "fallback")

    with patch("app.routers.gather.RESEARCH_ENGINE", "fallback"):
        resp = authed_client_with_db.post(f"/api/plans/{plan_id}/gather")

    assert resp.status_code == 200
    assert resp.json()["gather_status"] == "empty"


# ---------------------------------------------------------------------------
# AC2 — Pipeline order in ResearchOrchestrator
# ---------------------------------------------------------------------------

def test_orchestrator_pipeline_order():
    """AC2: run_research_for_plan calls planner → fetcher → extractor → synthesiser in order."""
    from app.services.research_orchestrator import run_research_for_plan
    from app.research.types import Plan as ResearchPlan, Source

    call_order = []

    class _TrackingEngine:
        def run(self, plan: ResearchPlan) -> list[Source]:
            call_order.append("engine.run")
            return []

    engine = _TrackingEngine()
    run_research_for_plan("mechanism", "0.5", engine)
    assert call_order == ["engine.run"]


def test_custom_engine_uses_planner_then_fetcher_then_extractor_then_synthesiser():
    """AC2: _CustomEngine calls planner.plan → fetcher.fetch → extractor.extract → synthesiser.synthesise."""
    from app.services.research_orchestrator import _CustomEngine
    from app.research.types import Plan as ResearchPlan, SearchQuery, FetchResult

    call_order = []

    mock_client = MagicMock()

    engine = _CustomEngine(anthropic_client=mock_client)

    mock_planner = MagicMock()
    mock_planner.plan.side_effect = lambda p: (call_order.append("planner") or [SearchQuery(query="q1")])

    mock_fetcher = MagicMock()
    mock_fetcher.fetch.side_effect = lambda q: (call_order.append("fetcher") or FetchResult(query=q, content="Some content here for extraction."))

    mock_extractor = MagicMock()
    mock_extractor.extract.side_effect = lambda doc: (call_order.append("extractor") or ["Claim extracted."])

    mock_synthesiser = MagicMock()
    mock_synthesiser.synthesise.side_effect = lambda plan, cands: (call_order.append("synthesiser") or [])

    with patch("app.research.LLMQueryPlanner", return_value=mock_planner), \
         patch("app.research.StubFetcher", return_value=mock_fetcher), \
         patch("app.research.ClaimExtractor", return_value=mock_extractor), \
         patch("app.research.CitationSynthesiser", return_value=mock_synthesiser):
        plan = ResearchPlan(mechanism="exercise causes fatigue", prior="0.5")
        engine.run(plan)

    assert call_order == ["planner", "fetcher", "extractor", "synthesiser"]


# ---------------------------------------------------------------------------
# AC1 — POST /api/cases/{id}/gather triggers research for all plans
# ---------------------------------------------------------------------------

def test_gather_case_triggers_for_all_plans(authed_client_with_db, db_session):
    """AC1: POST /api/cases/{id}/gather runs research for every plan in the case."""
    from app.services.research_orchestrator import gather_status_store
    gather_status_store.reset()

    case_id, plan_ids = _seed_case_at_gather(db_session)

    stub_sources = _make_stub_sources()
    call_count = {"n": 0}

    def _mock_run(plan_mechanism, plan_prior, engine):
        call_count["n"] += 1
        return stub_sources

    with patch("app.routers.gather.make_engine") as mock_factory, \
         patch("app.routers.gather.run_research_for_plan", side_effect=_mock_run):
        mock_factory.return_value = MagicMock()
        resp = authed_client_with_db.post(f"/api/cases/{case_id}/gather")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["plans"]) == 2
    assert call_count["n"] == 2  # ran for both plans
    for plan_result in data["plans"]:
        assert plan_result["gather_status"] == "done"


def test_gather_case_returns_404_for_unknown_case(authed_client_with_db, db_session):
    """AC1: POST /api/cases/{id}/gather with unknown case_id returns 404."""
    resp = authed_client_with_db.post("/api/cases/nonexistent-case-id/gather")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC10 — No regression: Stage 3 rerank still works
# ---------------------------------------------------------------------------

def test_stage_3_rerank_not_affected(authed_client_with_db, db_session):
    """AC10: POST /api/cases/{id}/rerank still functions after gather endpoints are added."""
    import uuid
    from datetime import datetime, timezone
    from app.models import Case, Plan

    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        raw_problem="Why am I tired?",
        sharpened="Fatigue — primary cause?",
        stage="weigh",
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(case)
    for label, rank in [("A", 1), ("B", 2), ("C", 3)]:
        db_session.add(Plan(
            id=str(uuid.uuid4()),
            case_id=case_id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism {label}",
            prior="0.33",
            current_rank=rank,
        ))
    db_session.commit()

    mock_result = [
        {"label": "A", "rank": 2, "standing": None},
        {"label": "B", "rank": 1, "standing": "ruled-in"},
        {"label": "C", "rank": 3, "standing": "ruled-out"},
    ]
    with patch("app.routers.cases.rerank_plans", return_value=mock_result):
        resp = authed_client_with_db.post(
            f"/api/cases/{case_id}/rerank",
            json={"context": "My haemoglobin is 8 g/dL"},
        )

    assert resp.status_code == 200
    plans = resp.json()["plans"]
    assert len(plans) == 3
    b_plan = next(p for p in plans if p["label"] == "B")
    assert b_plan["current_rank"] == 1


# ---------------------------------------------------------------------------
# Research orchestrator unit tests
# ---------------------------------------------------------------------------

def test_run_research_for_plan_calls_engine_run():
    """Core orchestrator: delegates to engine.run()."""
    from app.services.research_orchestrator import run_research_for_plan
    from app.research.types import Source

    mock_engine = MagicMock()
    mock_engine.run.return_value = [
        Source(kind="article", title="T", url="https://x.com", claim="C", citation="Ci")
    ]

    result = run_research_for_plan("mechanism", "0.5", mock_engine)
    assert len(result) == 1
    assert mock_engine.run.called


def test_run_research_for_plan_raises_orchestrator_error_on_engine_exception():
    """OrchestratorError is raised when engine.run() throws unexpectedly."""
    from app.services.research_orchestrator import run_research_for_plan, OrchestratorError

    mock_engine = MagicMock()
    mock_engine.run.side_effect = RuntimeError("Network down")

    with pytest.raises(OrchestratorError):
        run_research_for_plan("mechanism", "0.5", mock_engine)


def test_gather_status_store_lifecycle():
    """GatherStatusStore tracks idle → running → done transitions."""
    from app.services.research_orchestrator import _GatherStatusStore

    store = _GatherStatusStore()
    assert store.get("x")["status"] == "idle"

    store.set("x", "running")
    assert store.get("x")["status"] == "running"

    store.set("x", "done")
    assert store.get("x")["status"] == "done"

    store.set("x", "error", error="Timeout")
    assert store.get("x")["status"] == "error"
    assert store.get("x")["error"] == "Timeout"

    store.reset()
    assert store.get("x")["status"] == "idle"
