"""Tests for issue #146: Add POST /api/cases/{id}/summary endpoint with caching.

AC coverage:
  AC1 – POST /api/cases/{id}/summary is registered in routers/cases.py
  AC2 – On success, summary is generated, stored on case.summary, and returned
  AC3 – If case.summary exists and ?force=true is NOT passed, cached value is returned
  AC4 – If ?force=true is passed, summary is regenerated and case.summary is overwritten
  AC5 – Returns 422 if the case has not yet reached the probe stage
  AC6 – Returns 404 if the case ID does not exist
  AC7 – A verdict is NOT required for the endpoint to succeed
  AC8 – Response includes summary text and indicates freshly generated vs cached
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

_SUMMARY_JSON = json.dumps({
    "problem_statement": "Why did retention drop?",
    "option_ranking": "Option A: pricing (rank 1). Option B: feature gap (rank 2).",
    "recommended_plan": "Run a price-sensitivity A/B test.",
    "probe_plan": "Measurement probe tracking re-subscription rate over 14 days.",
})

_SUMMARY_JSON_V2 = json.dumps({
    "problem_statement": "Retention dropped after pricing change.",
    "option_ranking": "Option A: pricing (rank 1). Option B: UX (rank 2).",
    "recommended_plan": "Deploy targeted discount.",
    "probe_plan": "Track re-subscription for 30 days.",
})


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


def _seed_case(session, stage="probe", existing_summary=None):
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is user retention dropping after the pricing change?",
        sharpened="User retention dropped 20% post-pricing change.",
        stage=stage,
        summary=existing_summary,
    )
    session.add(case)

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Price sensitivity experiment",
        mechanism="Run A/B test with discounted cohort",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return case


def _seed_case_with_probe(session, stage="probe", existing_summary=None):
    from app import models

    case = _seed_case(session, stage=stage, existing_summary=existing_summary)
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="measurement",
        target_metric="re-subscription rate",
        status="designed",
    )
    session.add(probe)
    session.commit()
    return case, probe


# ---------------------------------------------------------------------------
# AC1: endpoint is registered
# ---------------------------------------------------------------------------

def test_endpoint_registered_in_router():
    """AC1: POST /api/cases/{id}/summary route must exist in the FastAPI app."""
    from app.main import app

    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", [])}
    assert ("/api/cases/{case_id}/summary", "POST") in routes, (
        "POST /api/cases/{case_id}/summary must be registered. "
        f"Found routes: {sorted(routes)}"
    )


# ---------------------------------------------------------------------------
# AC6: 404 for non-existent case
# ---------------------------------------------------------------------------

def test_404_for_nonexistent_case(api_client):
    """AC6: Non-existent case ID must return 404."""
    resp = api_client.post("/api/cases/nonexistent-id/summary")
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# AC5: 422 for pre-probe stage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", ["sharpened", "bake_off", "gather", "weigh"])
def test_422_for_pre_probe_stages(api_client, db_session, stage):
    """AC5: Cases that have not reached probe stage must return 422."""
    case = _seed_case(db_session, stage=stage)
    resp = api_client.post(f"/api/cases/{case.id}/summary")
    assert resp.status_code == 422, (
        f"Expected 422 for stage={stage!r}, got {resp.status_code}: {resp.text}"
    )


def test_422_error_message_is_descriptive(api_client, db_session):
    """AC5: 422 response must include a descriptive error message."""
    case = _seed_case(db_session, stage="sharpened")
    resp = api_client.post(f"/api/cases/{case.id}/summary")
    assert resp.status_code == 422
    body = resp.json()
    detail = body.get("detail", "")
    assert detail, "422 response must have a non-empty detail message"
    assert "probe" in detail.lower() or "stage" in detail.lower(), (
        f"422 detail should mention 'probe' or 'stage'; got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# AC2: fresh generation stores and returns summary
# ---------------------------------------------------------------------------

def test_fresh_generation_stores_summary(api_client, db_session):
    """AC2: Summary is generated, stored in case.summary, and returned."""
    from app import models

    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    db_session.expire_all()
    db_case = db_session.query(models.Case).filter_by(id=case.id).one()
    assert db_case.summary is not None, "case.summary must be populated after generation"
    assert json.loads(db_case.summary)["problem_statement"] == "Why did retention drop?"


def test_fresh_generation_response_contains_summary_text(api_client, db_session):
    """AC2/AC8: Response must include the summary text."""
    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body, f"Response must have a 'summary' key; got keys: {list(body)}"
    summary_data = body["summary"]
    assert summary_data.get("problem_statement") == "Why did retention drop?"


def test_fresh_generation_response_indicates_not_cached(api_client, db_session):
    """AC8: Fresh generation must indicate the result was NOT served from cache."""
    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert "cached" in body, f"Response must have a 'cached' key; got keys: {list(body)}"
    assert body["cached"] is False, f"Fresh generation must have cached=false; got: {body['cached']!r}"


# ---------------------------------------------------------------------------
# AC3: cached response when summary exists and force is not set
# ---------------------------------------------------------------------------

def test_cached_response_when_summary_exists(api_client, db_session):
    """AC3: If case.summary exists and ?force=true is not passed, cached value is returned."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.summary.generate_summary", new_callable=AsyncMock) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/summary")
        mock_gen.assert_not_called()

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


def test_cached_response_indicates_cached(api_client, db_session):
    """AC3/AC8: Cached response must indicate cached=true."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.summary.generate_summary", new_callable=AsyncMock):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    body = resp.json()
    assert "cached" in body, f"Response must have a 'cached' key; got keys: {list(body)}"
    assert body["cached"] is True, f"Cached response must have cached=true; got: {body['cached']!r}"


def test_cached_response_returns_same_summary_text(api_client, db_session):
    """AC3/AC8: Cached response must include the stored summary text."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.summary.generate_summary", new_callable=AsyncMock):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    body = resp.json()
    assert "summary" in body, f"Response must have a 'summary' key; got keys: {list(body)}"
    assert body["summary"]["problem_statement"] == "Why did retention drop?"


def test_generate_summary_not_called_when_cached(api_client, db_session):
    """AC3: generate_summary() must NOT be called when a cached value exists and force is False."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock) as mock_gen:
        api_client.post(f"/api/cases/{case.id}/summary")
        mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# AC4: force=true regenerates and overwrites
# ---------------------------------------------------------------------------

def test_force_true_regenerates_summary(api_client, db_session):
    """AC4: ?force=true causes regeneration even when case.summary exists."""
    from app import models

    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON_V2):
        resp = api_client.post(f"/api/cases/{case.id}/summary?force=true")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    db_session.expire_all()
    db_case = db_session.query(models.Case).filter_by(id=case.id).one()
    stored = json.loads(db_case.summary)
    assert stored["problem_statement"] == "Retention dropped after pricing change.", (
        "case.summary must be overwritten with the new value"
    )


def test_force_true_response_indicates_not_cached(api_client, db_session):
    """AC4/AC8: ?force=true response must indicate cached=false (freshly generated)."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON_V2):
        resp = api_client.post(f"/api/cases/{case.id}/summary?force=true")

    body = resp.json()
    assert body.get("cached") is False, (
        f"Forced regeneration must have cached=false; got: {body.get('cached')!r}"
    )


def test_force_true_calls_generate_summary(api_client, db_session):
    """AC4: generate_summary() IS called when ?force=true, even with existing summary."""
    case = _seed_case(db_session, stage="probe", existing_summary=_SUMMARY_JSON)

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON_V2) as mock_gen:
        api_client.post(f"/api/cases/{case.id}/summary?force=true")
        mock_gen.assert_called_once()


# ---------------------------------------------------------------------------
# AC7: verdict not required
# ---------------------------------------------------------------------------

def test_summary_succeeds_without_verdict(api_client, db_session):
    """AC7: Endpoint must succeed for a probe-stage case with no verdict."""
    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200, (
        f"Endpoint must succeed without a verdict; got {resp.status_code}: {resp.text}"
    )


def test_summary_succeeds_at_verdict_stage(api_client, db_session):
    """AC7: Endpoint must also succeed for cases at the verdict stage."""
    case = _seed_case(db_session, stage="verdict")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200, (
        f"Endpoint must succeed at verdict stage; got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# AC8: response shape completeness
# ---------------------------------------------------------------------------

def test_response_shape_has_required_keys(api_client, db_session):
    """AC8: Response body must have both 'summary' and 'cached' keys."""
    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body, f"'summary' key missing; got: {list(body)}"
    assert "cached" in body, f"'cached' key missing; got: {list(body)}"


def test_summary_key_contains_four_sections(api_client, db_session):
    """AC8: The 'summary' object must include all four summary sections."""
    case = _seed_case(db_session, stage="probe")

    with patch("app.routers.cases.generate_summary", new_callable=AsyncMock, return_value=_SUMMARY_JSON):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    body = resp.json()
    summary = body.get("summary", {})
    for key in ("problem_statement", "option_ranking", "recommended_plan", "probe_plan"):
        assert key in summary, f"summary must contain '{key}'; got keys: {list(summary)}"
