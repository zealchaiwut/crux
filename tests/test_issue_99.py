"""Tests for issue #99: Add source verification endpoints (single & batch).

AC coverage:
  AC1  – POST /api/sources/{id}/verify accepts support_status + rationale
  AC2  – Single endpoint returns updated source (200) or 404
  AC3  – POST /api/plans/{id}/verify-sources returns batch summary
  AC4  – Batch summary: { total, verified, failed, results }
  AC5  – Batch returns 404 for unknown plan; partial success on source failures
  AC6  – support_status and rationale persisted; re-verify overwrites prior result
  AC7  – Both endpoints defined in routers/sources.py
  AC8  – Both endpoints require auth (same scheme as existing sources)
  AC9  – Invalid enum → 422 with field-level detail
  AC10 – Missing rationale → 422 with field-level detail
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_engine():
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
    engine = _make_engine()
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


def _seed_plan(session, label="A"):
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened",
        stage="gather",
    )
    session.add(case)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label=label,
        name=f"Plan {label}",
        mechanism="Mechanism.",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return plan


def _seed_source(session, plan_id):
    from app import models

    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan_id,
        kind="article",
        title="Test Source",
        url=None,
        claim="Supports hypothesis",
        citation="Smith 2024",
    )
    session.add(source)
    session.commit()
    return source


# ---------------------------------------------------------------------------
# AC1 + AC2: POST /api/sources/{id}/verify — single verify
# ---------------------------------------------------------------------------

def test_verify_source_success(api_client, db_session):
    """AC1+AC2: POST /api/sources/{id}/verify returns 200 with updated source."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "supports", "rationale": "Directly cites the statistic."},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == source.id
    assert data["support_status"] == "supports"
    assert data["rationale"] == "Directly cites the statistic."


def test_verify_source_returns_full_source_object(api_client, db_session):
    """AC2: Response includes all source fields."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "partial", "rationale": "Not directly related."},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for field in ("id", "plan_id", "kind", "title", "url", "claim", "citation", "support_status", "rationale"):
        assert field in data, f"Response must include '{field}'"


def test_verify_source_404_unknown(api_client):
    """AC2: POST /api/sources/99999/verify → 404."""
    r = api_client.post(
        f"/api/sources/{uuid.uuid4()}/verify",
        json={"support_status": "supports", "rationale": "test"},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC6: Idempotent — re-verify overwrites prior result
# ---------------------------------------------------------------------------

def test_verify_source_overwrites_prior(api_client, db_session):
    """AC6: Re-verifying a source overwrites the previous support_status and rationale."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "supports", "rationale": "Initial rationale."},
    )
    r2 = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "contradicts", "rationale": "Updated rationale."},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["support_status"] == "contradicts"
    assert r2.json()["rationale"] == "Updated rationale."


def test_verify_source_persisted_to_db(api_client, db_session):
    """AC6: support_status and rationale are persisted in the database."""
    from app import models

    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "unverified", "rationale": "Ambiguous results."},
    )
    db_session.expire_all()
    src = db_session.query(models.Source).filter_by(id=source.id).first()
    assert src.support_status == "unverified"
    assert src.rationale == "Ambiguous results."


# ---------------------------------------------------------------------------
# AC9: Invalid enum → 422
# ---------------------------------------------------------------------------

def test_verify_source_invalid_enum(api_client, db_session):
    """AC9: Invalid support_status value returns 422 with field-level detail."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "unknown", "rationale": "test"},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC10: Missing rationale → 422
# ---------------------------------------------------------------------------

def test_verify_source_missing_rationale(api_client, db_session):
    """AC10: Missing rationale returns 422."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "neutral"},
    )
    assert r.status_code == 422, r.text


def test_verify_source_empty_rationale(api_client, db_session):
    """AC10: Empty rationale (length < 1) returns 422."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "neutral", "rationale": ""},
    )
    assert r.status_code == 422, r.text


def test_verify_source_rationale_too_long(api_client, db_session):
    """AC10: Rationale exceeding 2000 chars returns 422."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    r = api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "neutral", "rationale": "x" * 2001},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC8: Auth required on single verify endpoint
# ---------------------------------------------------------------------------

def test_verify_source_requires_auth(db_session):
    """AC8: Unauthenticated request to verify is redirected (302) or 401."""
    from app.main import app
    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app, follow_redirects=False)
    r = tc.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "supports", "rationale": "test"},
    )
    app.dependency_overrides.pop(get_db, None)
    assert r.status_code in (302, 401, 403), f"Expected auth redirect, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC3 + AC4: POST /api/plans/{id}/verify-sources — batch
# ---------------------------------------------------------------------------

def test_batch_verify_returns_summary(api_client, db_session):
    """AC3+AC4: Batch endpoint returns { total, verified, failed, results }."""
    plan = _seed_plan(db_session)
    _seed_source(db_session, plan.id)
    _seed_source(db_session, plan.id)

    r = api_client.post(f"/api/plans/{plan.id}/verify-sources")
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("total", "verified", "failed", "results"):
        assert key in data, f"Batch response must include '{key}'"


def test_batch_verify_total_matches_source_count(api_client, db_session):
    """AC4: total in summary equals number of sources linked to plan."""
    plan = _seed_plan(db_session)
    _seed_source(db_session, plan.id)
    _seed_source(db_session, plan.id)
    _seed_source(db_session, plan.id)

    r = api_client.post(f"/api/plans/{plan.id}/verify-sources")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3


def test_batch_verify_results_contain_per_source_info(api_client, db_session):
    """AC4: Each result contains source_id and verification fields."""
    plan = _seed_plan(db_session)
    source = _seed_source(db_session, plan.id)

    # Pre-verify the source via single endpoint
    api_client.post(
        f"/api/sources/{source.id}/verify",
        json={"support_status": "supports", "rationale": "Good evidence."},
    )

    r = api_client.post(f"/api/plans/{plan.id}/verify-sources")
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 1
    result = results[0]
    assert result["source_id"] == source.id
    assert result["support_status"] == "supports"
    assert result["rationale"] == "Good evidence."


def test_batch_verify_verified_count_reflects_status(api_client, db_session):
    """AC4: verified count equals number of sources with support_status set."""
    plan = _seed_plan(db_session)
    s1 = _seed_source(db_session, plan.id)
    _seed_source(db_session, plan.id)  # unverified

    # Only verify one source
    api_client.post(
        f"/api/sources/{s1.id}/verify",
        json={"support_status": "contradicts", "rationale": "Contradicts claim."},
    )

    r = api_client.post(f"/api/plans/{plan.id}/verify-sources")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert data["verified"] == 1
    assert data["failed"] == 0


def test_batch_verify_zero_sources(api_client, db_session):
    """AC5 (UAT step 8): Plan with no sources → { total:0, verified:0, failed:0, results:[] }."""
    plan = _seed_plan(db_session)

    r = api_client.post(f"/api/plans/{plan.id}/verify-sources")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {"total": 0, "verified": 0, "failed": 0, "results": []}


# ---------------------------------------------------------------------------
# AC5: Batch returns 404 for unknown plan
# ---------------------------------------------------------------------------

def test_batch_verify_404_unknown_plan(api_client):
    """AC5: POST /api/plans/99999/verify-sources → 404."""
    r = api_client.post(f"/api/plans/{uuid.uuid4()}/verify-sources")
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC8: Auth required on batch endpoint
# ---------------------------------------------------------------------------

def test_batch_verify_requires_auth(db_session):
    """AC8: Unauthenticated request to batch verify is redirected."""
    from app.main import app
    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    plan = _seed_plan(db_session)

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app, follow_redirects=False)
    r = tc.post(f"/api/plans/{plan.id}/verify-sources")
    app.dependency_overrides.pop(get_db, None)
    assert r.status_code in (302, 401, 403), f"Expected auth redirect, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC7: Both endpoints are in routers/sources.py
# ---------------------------------------------------------------------------

def test_endpoints_defined_in_sources_router():
    """AC7: Verify endpoint paths are registered in the sources router module."""
    import inspect
    import app.routers.sources as sources_module

    source = inspect.getsource(sources_module)
    assert "/sources/{" in source and "verify" in source, \
        "sources.py must define the single verify endpoint"
    assert "verify-sources" in source, \
        "sources.py must define the batch verify-sources endpoint"
