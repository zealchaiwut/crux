"""Tests for issue #94: AI-powered Case Summary generator.

AC coverage:
  AC1  – app/summary.py module exists with all summary-generation logic
  AC2  – POST /api/cases/{id}/summary endpoint is reachable
  AC3  – Returns 403 if case stage is earlier than probe
  AC4  – Generated summary includes all four sections
  AC5  – Summary persisted to summary column on cases table
  AC6  – Subsequent calls without ?force=true return cached summary (no Claude call)
  AC7  – ?force=true discards cached value, calls Claude, stores new result
  AC8  – Returns 404 when case ID does not exist
  AC9  – Case at stage probe with no verdict succeeds
  AC10 – Tests cover: cache hit, cache miss, forced regeneration, stage gate rejection
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_db()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api_client(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case(session, stage: str = "probe", with_verdict: bool = False, with_sources: bool = False):
    from app import models
    from datetime import datetime, timezone

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why did our retention drop?",
        sharpened="User retention dropped 20% after the pricing change.",
        not_investigating=json.dumps([]),
        stage=stage,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()

    plan_a = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Price sensitivity",
        mechanism="Users left because the new price exceeded their perceived value.",
        prior="0.60",
        current_rank=1,
    )
    plan_b = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="B",
        name="Feature gap",
        mechanism="Users left because a competitor now offers a missing feature.",
        prior="0.30",
        current_rank=2,
    )
    plan_c = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="C",
        name="Communication failure",
        mechanism="Users were confused by how the pricing change was communicated.",
        prior="0.10",
        current_rank=3,
    )
    session.add_all([plan_a, plan_b, plan_c])
    session.flush()

    if with_sources:
        source = models.Source(
            id=str(uuid.uuid4()),
            plan_id=plan_a.id,
            kind="article",
            title="Price elasticity study Q1",
            url="https://example.com/study",
            claim="60% of churned users cited price as the primary reason.",
            citation="Price Elasticity Study Q1 2026",
        )
        session.add(source)

    if with_verdict:
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric="churn rate",
            status="confirmed",
        )
        session.add(probe)
        session.flush()
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Price was the main driver.",
        )
        session.add(verdict)

    session.commit()
    return c


_MOCK_SUMMARY = json.dumps({
    "problem_statement": "User retention dropped 20% after the pricing change.",
    "option_ranking": (
        "A (Price sensitivity, rank 1): Most likely cause. "
        "Supported by Price Elasticity Study Q1 (source id: src-1). "
        "B (Feature gap, rank 2): Possible but less evidence. "
        "C (Communication failure, rank 3): Least likely."
    ),
    "recommended_plan": "Investigate price sensitivity through a targeted survey.",
    "probe_plan": "Run a 2-week A/B test offering a discount to churned users.",
})


# ---------------------------------------------------------------------------
# AC1: app/summary.py module exists
# ---------------------------------------------------------------------------

def test_summary_module_exists():
    """AC1: app/summary.py must exist and be importable."""
    import importlib
    mod = importlib.import_module("app.summary")
    assert hasattr(mod, "generate_summary"), (
        "app/summary.py must export generate_summary"
    )
    assert hasattr(mod, "SummaryError"), (
        "app/summary.py must export SummaryError"
    )


# ---------------------------------------------------------------------------
# AC2: Endpoint is reachable
# ---------------------------------------------------------------------------

def test_summary_endpoint_reachable(api_client, db_session):
    """AC2: POST /api/cases/{id}/summary must be a registered route."""
    c = _seed_case(db_session, stage="probe")
    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY):
        r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code != 404 or r.json().get("detail") != "Not Found", (
        "Endpoint /api/cases/{id}/summary must be registered (not 404 Not Found)"
    )
    assert r.status_code == 200, (
        f"Expected 200 for a valid probe-stage case; got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# AC3: Stage gate — 403 when stage is earlier than probe (AC10: stage gate)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", ["sharpened", "bake_off", "gather", "weigh"])
def test_stage_gate_rejects_pre_probe_stages(api_client, db_session, stage):
    """AC3 / AC10: Must return 403 for any stage earlier than probe."""
    c = _seed_case(db_session, stage=stage)
    r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code in (403, 409), (
        f"Expected 403 or 409 for stage={stage!r}; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "detail" in body, "Stage-gate error response must include a 'detail' message"
    detail = body["detail"].lower()
    assert "probe" in detail or "stage" in detail, (
        f"Error message must mention the stage requirement; got: {body['detail']!r}"
    )


# ---------------------------------------------------------------------------
# AC4: Summary includes all four required sections
# ---------------------------------------------------------------------------

def test_summary_contains_four_sections(api_client, db_session):
    """AC4: Summary must include problem_statement, option_ranking, recommended_plan, probe_plan."""
    c = _seed_case(db_session, stage="probe", with_sources=True)
    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY):
        r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code == 200, f"Expected 200; got {r.status_code}: {r.text}"
    data = r.json()
    for field in ("problem_statement", "option_ranking", "recommended_plan", "probe_plan"):
        assert field in data, f"Response must include '{field}' section; got keys: {list(data)}"
        assert data[field], f"'{field}' must be non-empty"


# ---------------------------------------------------------------------------
# AC5: Summary persisted to the summary column (AC10: cache miss path)
# ---------------------------------------------------------------------------

def test_summary_persisted_to_db(api_client, db_session):
    """AC5 / AC10 (cache miss): Summary must be stored in the case row after generation."""
    c = _seed_case(db_session, stage="probe")
    call_count = 0

    async def _mock_generate(case_data):
        nonlocal call_count
        call_count += 1
        return _MOCK_SUMMARY

    with patch("app.routers.cases.generate_summary", side_effect=_mock_generate):
        r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code == 200, f"Expected 200; got {r.status_code}: {r.text}"
    assert call_count == 1, "Claude must be called exactly once on a cache miss"

    db_session.expire_all()
    from app import models
    updated = db_session.get(models.Case, c.id)
    assert updated.summary is not None, "case.summary must be non-null after generation"
    assert updated.summary.strip(), "case.summary must not be blank"


# ---------------------------------------------------------------------------
# AC6: Cache hit — no Claude call on second request (AC10: cache hit)
# ---------------------------------------------------------------------------

def test_cache_hit_does_not_call_claude(api_client, db_session):
    """AC6 / AC10 (cache hit): Second POST without force must return cached value."""
    c = _seed_case(db_session, stage="probe")
    call_count = 0

    async def _mock_generate(case_data):
        nonlocal call_count
        call_count += 1
        return _MOCK_SUMMARY

    with patch("app.routers.cases.generate_summary", side_effect=_mock_generate):
        r1 = api_client.post(f"/api/cases/{c.id}/summary")
        r2 = api_client.post(f"/api/cases/{c.id}/summary")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert call_count == 1, (
        f"Claude must be called only once; called {call_count} times"
    )
    assert r1.json() == r2.json(), "Cached response must match first response"


# ---------------------------------------------------------------------------
# AC7: force=true discards cache and calls Claude again (AC10: forced regeneration)
# ---------------------------------------------------------------------------

def test_force_true_regenerates_summary(api_client, db_session):
    """AC7 / AC10 (forced regen): ?force=true must discard cache and call Claude again."""
    c = _seed_case(db_session, stage="probe")
    call_count = 0

    async def _mock_generate(case_data):
        nonlocal call_count
        call_count += 1
        return _MOCK_SUMMARY

    with patch("app.routers.cases.generate_summary", side_effect=_mock_generate):
        r1 = api_client.post(f"/api/cases/{c.id}/summary")
        r2 = api_client.post(f"/api/cases/{c.id}/summary?force=true")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert call_count == 2, (
        f"Claude must be called twice when force=true is used on second call; "
        f"called {call_count} times"
    )


def test_force_false_after_force_true_uses_new_cache(api_client, db_session):
    """AC7: After force=true, subsequent non-forced calls return the new cached value."""
    c = _seed_case(db_session, stage="probe")
    call_sequence = []
    results = [_MOCK_SUMMARY, json.dumps({
        "problem_statement": "Updated problem statement after source attachment.",
        "option_ranking": "A: Updated with new source. B: Same. C: Same.",
        "recommended_plan": "Updated recommended plan.",
        "probe_plan": "Updated probe plan with new citation.",
    })]

    async def _mock_generate(case_data):
        r = results[len(call_sequence)]
        call_sequence.append(r)
        return r

    with patch("app.routers.cases.generate_summary", side_effect=_mock_generate):
        api_client.post(f"/api/cases/{c.id}/summary")
        r_forced = api_client.post(f"/api/cases/{c.id}/summary?force=true")
        r_cached = api_client.post(f"/api/cases/{c.id}/summary")

    assert len(call_sequence) == 2, "Claude called twice: initial + forced"
    assert r_forced.json() == r_cached.json(), (
        "Non-forced call after force=true must return the newly cached value"
    )


# ---------------------------------------------------------------------------
# AC8: 404 for non-existent case
# ---------------------------------------------------------------------------

def test_returns_404_for_nonexistent_case(api_client):
    """AC8: Must return 404 when the case ID does not exist."""
    r = api_client.post(f"/api/cases/{uuid.uuid4()}/summary")
    assert r.status_code == 404, (
        f"Expected 404 for non-existent case; got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# AC9: probe stage with no verdict succeeds
# ---------------------------------------------------------------------------

def test_probe_stage_no_verdict_succeeds(api_client, db_session):
    """AC9: A case at stage probe with no verdict must generate a summary successfully."""
    c = _seed_case(db_session, stage="probe", with_verdict=False)
    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY):
        r = api_client.post(f"/api/cases/{c.id}/summary")
    assert r.status_code == 200, (
        f"Case at probe stage with no verdict must return 200; got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# AC5 (migration): summary column exists on the Case model
# ---------------------------------------------------------------------------

def test_case_model_has_summary_column():
    """AC5: Case ORM model must have a summary column."""
    from app.models import Case
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(Case)
    col_names = [c.key for c in mapper.columns]
    assert "summary" in col_names, (
        f"Case model must have a 'summary' column; found: {col_names}"
    )


def test_summary_column_nullable_by_default(db_session):
    """AC5: Newly created case has summary=None until a summary is generated."""
    c = _seed_case(db_session, stage="probe")
    db_session.expire_all()
    from app import models
    fresh = db_session.get(models.Case, c.id)
    assert fresh.summary is None, (
        f"Newly created case must have summary=None; got: {fresh.summary!r}"
    )
