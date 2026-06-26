"""Tests for issue #55: GET /api/verdicts timestamp field null-handling.

UAT-level checks that run against the FastAPI TestClient (no live server required).

AC coverage:
  AC1 – GET /api/verdicts returns 200 and includes a created_at field
  AC2 – Endpoint accepts outcome and keyword filters; invalid outcome → 400
  AC3 – Response structure matches expected shape
  AC4 – OpenAPI docs (/docs and /openapi.json) are accessible
"""
import os
import uuid
from datetime import datetime, timezone

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
def client(db_session):
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


def _seed_verdict(session, outcome="confirmed", decided_at="__now__"):
    """Seed a Case → Probe → Verdict chain for testing."""
    from app import models

    if decided_at == "__now__":
        decided_at = datetime.now(tz=timezone.utc)

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        sharpened="test sharpened",
        stage="verdict",
    )
    session.add(case)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="lab-test",
        target_metric="metric",
        status=outcome,
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes="test notes",
        decided_at=decided_at,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return verdict.id


# ---------------------------------------------------------------------------
# AC1: endpoint exists and returns 200
# ---------------------------------------------------------------------------

def test_verdicts_endpoint_exists__ac1(client):
    """AC1: GET /api/verdicts endpoint exists and returns 200."""
    r = client.get("/api/verdicts")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert isinstance(r.json(), list), f"Expected list response, got {type(r.json())}"


def test_created_at_field_present_in_response__ac1(client, db_session):
    """AC1: Response objects include a created_at field."""
    _seed_verdict(db_session)
    r = client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert "created_at" in data[0], "created_at must be present on every verdict"

    # Also verify the endpoint is documented in OpenAPI
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    verdicts_path = spec.get("paths", {}).get("/api/verdicts", {})
    assert verdicts_path, "GET /api/verdicts must be documented in OpenAPI"
    assert "get" in verdicts_path, "GET method must be documented"


# ---------------------------------------------------------------------------
# AC2: filters work correctly
# ---------------------------------------------------------------------------

def test_endpoint_accepts_outcome_filter__ac2(client):
    """AC2: Endpoint accepts outcome parameter; invalid value returns 400."""
    r = client.get("/api/verdicts?outcome=confirmed")
    assert r.status_code == 200, f"Expected 200 with outcome filter, got {r.status_code}"

    r = client.get("/api/verdicts?outcome=invalid_outcome")
    assert r.status_code == 400, "Invalid outcome should return 400"


def test_endpoint_accepts_keyword_filter__ac2(client):
    """AC2: Endpoint accepts keyword/q parameter for search."""
    r = client.get("/api/verdicts?keyword=test")
    assert r.status_code == 200, f"Expected 200 with keyword filter, got {r.status_code}"

    r = client.get("/api/verdicts?q=test")
    assert r.status_code == 200, f"Expected 200 with q parameter, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC3: response structure
# ---------------------------------------------------------------------------

def test_api_response_structure__ac3(client, db_session):
    """AC3: Response objects have the expected fields including non-null created_at."""
    _seed_verdict(db_session)
    r = client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    for verdict in data:
        assert isinstance(verdict, dict), "Each verdict must be a dict"
        assert "id" in verdict, "Each verdict must have an id"
        assert "created_at" in verdict, "Each verdict must have a created_at field"
        assert "outcome" in verdict, "Each verdict must have an outcome field"
        assert verdict["created_at"] is not None, "created_at must not be null"


# ---------------------------------------------------------------------------
# AC4: OpenAPI docs accessible
# ---------------------------------------------------------------------------

def test_openapi_docs_accessible__ac4(client):
    """AC4: OpenAPI schema docs are accessible at /docs and /openapi.json."""
    r = client.get("/docs")
    assert r.status_code == 200, "Swagger UI docs should be accessible at /docs"

    r = client.get("/openapi.json")
    assert r.status_code == 200, "OpenAPI spec should be accessible at /openapi.json"
    spec = r.json()
    assert "paths" in spec, "OpenAPI spec must include paths"
    responses = spec.get("paths", {}).get("/api/verdicts", {}).get("get", {}).get("responses", {})
    assert "200" in responses, "Endpoint must document 200 response"
