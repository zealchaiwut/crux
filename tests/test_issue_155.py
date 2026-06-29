"""Tests for issue #155: Add source verification endpoints to sources router.

AC coverage:
  AC1  – POST /api/sources/{id}/verify accepts support_status and support_rationale,
         returns updated source object with HTTP 200
  AC2  – POST /api/sources/{id}/verify returns HTTP 404 when source does not exist
  AC3  – POST /api/sources/{id}/verify persists support_status and support_rationale to DB
  AC4  – POST /api/plans/{id}/verify-sources returns a list of updated source objects
         with HTTP 200
  AC5  – POST /api/plans/{id}/verify-sources returns HTTP 404 when plan does not exist
  AC6  – POST /api/plans/{id}/verify-sources returns empty list when plan has no sources
  AC7  – Both endpoints are in routers/sources.py and registered on the FastAPI app
  AC8  – support_status is validated against enum; invalid values return HTTP 422
  AC9  – support_rationale is optional (nullable); omitting it returns HTTP 200
  AC10 – Both endpoints appear in OpenAPI schema (GET /openapi.json)
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Shared fixtures
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


def _seed(session, *, num_sources=1, claim="test claim"):
    """Seed Case → Plan → N Sources; return (plan_id, [source_ids])."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="problem",
        stage="gather",
    )
    session.add(case)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="mechanism",
    )
    session.add(plan)
    session.flush()

    source_ids = []
    for i in range(num_sources):
        src = models.Source(
            id=str(uuid.uuid4()),
            plan_id=plan.id,
            kind="article",
            title=f"Source {i}",
            claim=claim,
            citation=f"Author {i} 2024",
        )
        session.add(src)
        source_ids.append(src.id)

    session.commit()
    return plan.id, source_ids


# ---------------------------------------------------------------------------
# AC1 — POST /api/sources/{id}/verify returns HTTP 200 with updated source
# ---------------------------------------------------------------------------

def test_verify_source_returns_200(api_client, db_session):
    """AC1: POST /api/sources/{id}/verify returns HTTP 200."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "supports", "support_rationale": "Directly cited in section 3."},
    )
    assert r.status_code == 200, r.text


def test_verify_source_response_includes_support_status(api_client, db_session):
    """AC1: Response body includes support_status."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "supports", "support_rationale": "Evidence."},
    )
    assert r.status_code == 200
    data = r.json()
    assert "support_status" in data
    assert data["support_status"] == "supports"


def test_verify_source_response_includes_support_rationale(api_client, db_session):
    """AC1: Response body includes support_rationale matching what was sent."""
    plan_id, [src_id] = _seed(db_session)
    rationale = "Directly cited in section 3."
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "supports", "support_rationale": rationale},
    )
    assert r.status_code == 200
    data = r.json()
    assert "support_rationale" in data
    assert data["support_rationale"] == rationale


def test_verify_source_response_is_source_object(api_client, db_session):
    """AC1: Response is the updated source object (includes id, plan_id, kind, etc.)."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "partial", "support_rationale": "Partially supported."},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == src_id
    assert data.get("plan_id") == plan_id
    assert "kind" in data


# ---------------------------------------------------------------------------
# AC2 — 404 when source does not exist
# ---------------------------------------------------------------------------

def test_verify_source_404_for_missing_source(api_client):
    """AC2: POST /api/sources/{id}/verify returns 404 when source does not exist."""
    r = api_client.post(
        "/api/sources/nonexistent-id-99999/verify",
        json={"support_status": "supports"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AC3 — Persists support_status and support_rationale to DB
# ---------------------------------------------------------------------------

def test_verify_source_persists_support_status(api_client, db_session):
    """AC3: support_status is saved to the database."""
    plan_id, [src_id] = _seed(db_session)
    api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "contradicts", "support_rationale": "Refutes claim."},
    )
    db_session.expire_all()
    from app import models
    src = db_session.query(models.Source).filter(models.Source.id == src_id).first()
    assert src.support_status == "contradicts"


def test_verify_source_persists_support_rationale(api_client, db_session):
    """AC3: support_rationale is saved to the database."""
    plan_id, [src_id] = _seed(db_session)
    rationale = "Primary peer-reviewed study confirmed the claim."
    api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "supports", "support_rationale": rationale},
    )
    db_session.expire_all()
    from app import models
    src = db_session.query(models.Source).filter(models.Source.id == src_id).first()
    assert src.support_rationale == rationale


# ---------------------------------------------------------------------------
# AC4 — POST /api/plans/{id}/verify-sources returns list of source objects
# ---------------------------------------------------------------------------

def test_batch_verify_returns_200(api_client, db_session):
    """AC4: POST /api/plans/{id}/verify-sources returns HTTP 200."""
    plan_id, _ = _seed(db_session, num_sources=2)
    r = api_client.post(f"/api/plans/{plan_id}/verify-sources")
    assert r.status_code == 200, r.text


def test_batch_verify_returns_list(api_client, db_session):
    """AC4: Response is a JSON list (not a dict)."""
    plan_id, _ = _seed(db_session, num_sources=3)
    r = api_client.post(f"/api/plans/{plan_id}/verify-sources")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"


def test_batch_verify_returns_all_sources(api_client, db_session):
    """AC4: List contains one entry per source linked to the plan."""
    plan_id, src_ids = _seed(db_session, num_sources=3)
    r = api_client.post(f"/api/plans/{plan_id}/verify-sources")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3, f"Expected 3 source objects, got {len(data)}"


def test_batch_verify_list_items_are_source_objects(api_client, db_session):
    """AC4: Each item in the list is a source object with id, support_status, support_rationale."""
    plan_id, src_ids = _seed(db_session, num_sources=2)
    r = api_client.post(f"/api/plans/{plan_id}/verify-sources")
    assert r.status_code == 200
    data = r.json()
    returned_ids = {item["id"] for item in data}
    assert returned_ids == set(src_ids)
    for item in data:
        assert "support_status" in item
        assert "support_rationale" in item


# ---------------------------------------------------------------------------
# AC5 — 404 when plan does not exist
# ---------------------------------------------------------------------------

def test_batch_verify_404_for_missing_plan(api_client):
    """AC5: POST /api/plans/{id}/verify-sources returns 404 when plan does not exist."""
    r = api_client.post("/api/plans/nonexistent-plan-99999/verify-sources")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AC6 — Empty list when plan has no sources
# ---------------------------------------------------------------------------

def test_batch_verify_empty_list_for_plan_with_no_sources(api_client, db_session):
    """AC6: Returns [] (not an error) when plan has 0 sources."""
    plan_id, _ = _seed(db_session, num_sources=0)
    r = api_client.post(f"/api/plans/{plan_id}/verify-sources")
    assert r.status_code == 200
    data = r.json()
    assert data == [], f"Expected empty list, got {data!r}"


# ---------------------------------------------------------------------------
# AC7 — Endpoints registered on the main FastAPI app
# ---------------------------------------------------------------------------

def test_verify_source_endpoint_registered_on_app():
    """AC7: POST /api/sources/{id}/verify is registered on the FastAPI app."""
    from app.main import app
    routes = {r.path: list(r.methods) for r in app.routes if hasattr(r, "methods")}
    assert "/api/sources/{source_id}/verify" in routes, (
        "POST /api/sources/{source_id}/verify must be registered on the app"
    )
    assert "POST" in routes["/api/sources/{source_id}/verify"]


def test_batch_verify_endpoint_registered_on_app():
    """AC7: POST /api/plans/{id}/verify-sources is registered on the FastAPI app."""
    from app.main import app
    routes = {r.path: list(r.methods) for r in app.routes if hasattr(r, "methods")}
    assert "/api/plans/{plan_id}/verify-sources" in routes, (
        "POST /api/plans/{plan_id}/verify-sources must be registered on the app"
    )
    assert "POST" in routes["/api/plans/{plan_id}/verify-sources"]


def test_endpoints_defined_in_sources_router():
    """AC7: Both endpoints are defined in app/routers/sources.py."""
    import inspect
    from app.routers import sources
    src = inspect.getsource(sources)
    assert "/sources/{source_id}/verify" in src or "sources/{source_id}/verify" in src, (
        "verify endpoint must be defined in app/routers/sources.py"
    )
    assert "/plans/{plan_id}/verify-sources" in src or "plans/{plan_id}/verify-sources" in src, (
        "verify-sources endpoint must be defined in app/routers/sources.py"
    )


# ---------------------------------------------------------------------------
# AC8 — support_status validated against enum; invalid values return 422
# ---------------------------------------------------------------------------

def test_invalid_support_status_returns_422(api_client, db_session):
    """AC8: Invalid support_status returns HTTP 422."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "INVALID_STATUS"},
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("status", ["supports", "partial", "contradicts", "unverified"])
def test_all_valid_support_status_values_accepted(api_client, db_session, status):
    """AC8: All four canonical enum values are accepted."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": status},
    )
    assert r.status_code == 200, f"status '{status}' should be accepted: {r.text}"
    assert r.json()["support_status"] == status


# ---------------------------------------------------------------------------
# AC9 — support_rationale is optional (nullable)
# ---------------------------------------------------------------------------

def test_verify_source_without_rationale_returns_200(api_client, db_session):
    """AC9: Omitting support_rationale returns HTTP 200 (it's optional)."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "unverified"},
    )
    assert r.status_code == 200, r.text


def test_verify_source_without_rationale_stores_null(api_client, db_session):
    """AC9: Omitting support_rationale stores NULL in the database."""
    plan_id, [src_id] = _seed(db_session)
    api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "partial"},
    )
    db_session.expire_all()
    from app import models
    src = db_session.query(models.Source).filter(models.Source.id == src_id).first()
    assert src.support_rationale is None


def test_verify_source_with_null_rationale_field_returns_200(api_client, db_session):
    """AC9: Explicitly sending null support_rationale returns HTTP 200."""
    plan_id, [src_id] = _seed(db_session)
    r = api_client.post(
        f"/api/sources/{src_id}/verify",
        json={"support_status": "supports", "support_rationale": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["support_rationale"] is None


# ---------------------------------------------------------------------------
# AC10 — OpenAPI schema reflects both endpoints
# ---------------------------------------------------------------------------

def test_openapi_includes_verify_source_endpoint(api_client):
    """AC10: GET /openapi.json lists POST /api/sources/{source_id}/verify."""
    r = api_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema.get("paths", {})
    assert "/api/sources/{source_id}/verify" in paths, (
        "OpenAPI schema must include /api/sources/{source_id}/verify"
    )
    assert "post" in paths["/api/sources/{source_id}/verify"]


def test_openapi_includes_batch_verify_sources_endpoint(api_client):
    """AC10: GET /openapi.json lists POST /api/plans/{plan_id}/verify-sources."""
    r = api_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema.get("paths", {})
    assert "/api/plans/{plan_id}/verify-sources" in paths, (
        "OpenAPI schema must include /api/plans/{plan_id}/verify-sources"
    )
    assert "post" in paths["/api/plans/{plan_id}/verify-sources"]
