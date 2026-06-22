"""Tests for issue #83: Add POST /api/sources/batch to attach multiple sources.

AC coverage:
  AC1  – POST /api/sources/batch accepts plan_id + non-empty sources array
  AC2  – Each item validated same as POST /api/sources (kind, title, claim, citation, url)
  AC3  – All rows inserted in single transaction; any failure rolls back all rows → 422 with per-item errors
  AC4  – Success returns HTTP 201 with array of created Source rows
  AC5  – Empty sources array → 422
  AC6  – Unknown plan_id → 404
  AC7  – Validation errors identify offending index (e.g. sources[2].kind is invalid)
  AC8  – Existing POST /api/sources behaviour unchanged
  AC9  – Unit tests: happy path, partial validation failure, unknown plan
  AC9b – Integration test: single-transaction rollback behaviour
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# DB + client fixtures
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
        sharpened="Sharpened test",
        stage="gather",
    )
    session.add(case)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label=label,
        name=f"Plan {label}",
        mechanism="Some mechanism.",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return plan


def _valid_source(overrides=None):
    base = {
        "kind": "article",
        "title": "Test Article",
        "url": "https://example.com/article",
        "claim": "Supports hypothesis",
        "citation": "Smith 2024",
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# AC4 + AC1: Happy path — 201 with array of created rows
# ---------------------------------------------------------------------------

def test_batch_create_happy_path(api_client, db_session):
    """AC4: POST /api/sources/batch returns 201 with array of created Source rows."""
    plan = _seed_plan(db_session)
    sources = [
        _valid_source({"kind": "article", "title": "First"}),
        _valid_source({"kind": "book", "title": "Second"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 201, r.text
    data = r.json()
    assert isinstance(data, list), "Response must be a list"
    assert len(data) == 2, f"Expected 2 sources, got {len(data)}"


def test_batch_create_response_fields(api_client, db_session):
    """AC4: Each row in response has id, plan_id, kind, title, url, claim, citation."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources/batch", json={
        "plan_id": plan.id,
        "sources": [_valid_source()],
    })
    assert r.status_code == 201, r.text
    row = r.json()[0]
    for field in ("id", "plan_id", "kind", "title", "url", "claim", "citation"):
        assert field in row, f"Response row must include '{field}'"
    assert row["plan_id"] == plan.id


def test_batch_create_persists_to_db(api_client, db_session):
    """AC4: Created rows actually exist in the database after successful batch."""
    from app import models

    plan = _seed_plan(db_session)
    sources = [
        _valid_source({"title": "Row One"}),
        _valid_source({"title": "Row Two", "kind": "book"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 201, r.text

    rows = db_session.query(models.Source).filter_by(plan_id=plan.id).all()
    assert len(rows) == 2
    titles = {row.title for row in rows}
    assert titles == {"Row One", "Row Two"}


# ---------------------------------------------------------------------------
# AC6: Unknown plan_id → 404
# ---------------------------------------------------------------------------

def test_batch_unknown_plan_returns_404(api_client):
    """AC6: POST /api/sources/batch with non-existent plan_id returns 404."""
    r = api_client.post("/api/sources/batch", json={
        "plan_id": str(uuid.uuid4()),
        "sources": [_valid_source()],
    })
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC5: Empty sources array → 422
# ---------------------------------------------------------------------------

def test_batch_empty_sources_returns_422(api_client, db_session):
    """AC5: POST /api/sources/batch with empty sources array returns 422."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": []})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC2 + AC7: Per-item validation with index in error message
# ---------------------------------------------------------------------------

def test_batch_invalid_kind_at_index_1(api_client, db_session):
    """AC2 + AC7: Invalid kind on second item → 422 mentioning sources[1]."""
    plan = _seed_plan(db_session)
    sources = [
        _valid_source(),
        _valid_source({"kind": "not-valid"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 422, r.text
    body = r.text
    assert "sources[1]" in body, f"Error must reference sources[1], got: {body}"


def test_batch_empty_title_at_index_0(api_client, db_session):
    """AC2 + AC7: Empty title on first item → 422 mentioning sources[0]."""
    plan = _seed_plan(db_session)
    sources = [
        _valid_source({"title": ""}),
        _valid_source(),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 422, r.text
    body = r.text
    assert "sources[0]" in body, f"Error must reference sources[0], got: {body}"


def test_batch_invalid_url_at_index_2(api_client, db_session):
    """AC2 + AC7: Malformed URL on third item → 422 mentioning sources[2]."""
    plan = _seed_plan(db_session)
    sources = [
        _valid_source(),
        _valid_source(),
        _valid_source({"url": "not-a-url"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 422, r.text
    body = r.text
    assert "sources[2]" in body, f"Error must reference sources[2], got: {body}"


def test_batch_empty_claim_error_message(api_client, db_session):
    """AC2 + AC7: Empty claim → 422 mentioning sources[0] and claim."""
    plan = _seed_plan(db_session)
    sources = [_valid_source({"claim": "   "})]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 422, r.text
    body = r.text
    assert "sources[0]" in body, f"Error must reference sources[0], got: {body}"


# ---------------------------------------------------------------------------
# AC3: Single-transaction rollback — no rows written on partial failure
# ---------------------------------------------------------------------------

def test_batch_transaction_rollback_on_validation_failure(api_client, db_session):
    """AC3 + AC9b: Partial validation failure → zero rows in DB (transaction rollback)."""
    from app import models

    plan = _seed_plan(db_session)
    sources = [
        _valid_source({"title": "Good Row"}),
        _valid_source({"kind": "invalid-kind"}),
    ]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 422, r.text

    count = db_session.query(models.Source).filter_by(plan_id=plan.id).count()
    assert count == 0, f"No sources must be written on validation failure, got {count}"


def test_batch_transaction_rollback_all_valid_but_db_isolation(api_client, db_session):
    """AC3: Successful batch writes ALL rows atomically, not partially."""
    from app import models

    plan = _seed_plan(db_session)
    sources = [_valid_source({"title": f"Source {i}"}) for i in range(3)]
    r = api_client.post("/api/sources/batch", json={"plan_id": plan.id, "sources": sources})
    assert r.status_code == 201, r.text

    count = db_session.query(models.Source).filter_by(plan_id=plan.id).count()
    assert count == 3, f"All 3 rows must be written, got {count}"


# ---------------------------------------------------------------------------
# AC8: Existing POST /api/sources unchanged
# ---------------------------------------------------------------------------

def test_single_source_endpoint_still_works(api_client, db_session):
    """AC8: POST /api/sources (single) still returns 201 and persists correctly."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources", json={
        "plan_id": plan.id,
        "kind": "book",
        "title": "Single Source",
        "url": None,
        "claim": "Still works",
        "citation": "Unchanged 2024",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert data["title"] == "Single Source"


def test_single_source_endpoint_not_affected_by_batch(api_client, db_session):
    """AC8: Single endpoint unchanged — invalid kind still returns 422."""
    plan = _seed_plan(db_session)
    r = api_client.post("/api/sources", json={
        "plan_id": plan.id,
        "kind": "not-valid",
        "title": "Bad",
        "url": None,
        "claim": "A claim",
        "citation": "X 2024",
    })
    assert r.status_code == 422, r.text
