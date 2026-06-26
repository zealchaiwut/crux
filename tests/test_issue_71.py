"""Tests for issue #71: _VALID_VERDICT_PARAMS constant must be used in validation.

The constant was defined but never referenced — the inline literal
{"confirmed", "killed", "inconclusive"} bypassed it. Fix: add a 400 guard for
invalid verdict params (mirroring the existing stage guard) using the constant.

AC coverage:
  AC1 – Invalid ?verdict value returns 400 with a descriptive error message
  AC2 – Valid verdict values (confirmed, killed, inconclusive, open) still work correctly
  AC3 – _VALID_VERDICT_PARAMS constant is actually referenced in cases.py (not dead code)
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


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


def _seed_case(session, sharpened="A hypothesis", stage="sharpened", verdict_outcome=None):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened=sharpened,
        stage=stage,
    )
    session.add(c)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        mechanism="default mechanism",
        current_rank=1,
    )
    session.add(plan)
    if verdict_outcome:
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            status=verdict_outcome,
        )
        session.add(probe)
        session.flush()
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome=verdict_outcome,
            notes="test notes",
        )
        session.add(verdict)
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: Invalid ?verdict value returns 400
# ---------------------------------------------------------------------------

def test_invalid_verdict_returns_400(api_client):
    """AC1: ?verdict=blah returns 400, not 200 with empty results."""
    r = api_client.get("/api/cases?verdict=blah")
    assert r.status_code == 400


def test_invalid_verdict_error_mentions_valid_values(api_client):
    """AC1: 400 response body describes valid verdict values."""
    r = api_client.get("/api/cases?verdict=invalid_verdict_xyz")
    assert r.status_code == 400
    detail = r.json()["detail"]
    # Must mention at least one valid value so clients know what to use
    assert any(v in detail for v in ("confirmed", "killed", "inconclusive", "open")), (
        f"400 detail must mention valid verdict values, got: {detail!r}"
    )


def test_invalid_verdict_mentions_the_bad_value(api_client):
    """AC1: 400 detail echoes back the bad value so it's clear what was rejected."""
    r = api_client.get("/api/cases?verdict=nonsense")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "nonsense" in detail, f"Expected bad value in detail, got: {detail!r}"


# ---------------------------------------------------------------------------
# AC2: All four valid verdict values still work correctly
# ---------------------------------------------------------------------------

def test_verdict_confirmed_still_works(api_client, db_session):
    """AC2: ?verdict=confirmed returns 200 and filters correctly after the guard."""
    _seed_case(db_session, verdict_outcome="confirmed")
    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


def test_verdict_killed_still_works(api_client, db_session):
    """AC2: ?verdict=killed returns 200 and filters correctly."""
    _seed_case(db_session, verdict_outcome="killed")
    r = api_client.get("/api/cases?verdict=killed")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


def test_verdict_inconclusive_still_works(api_client, db_session):
    """AC2: ?verdict=inconclusive returns 200 and filters correctly."""
    _seed_case(db_session, verdict_outcome="inconclusive")
    r = api_client.get("/api/cases?verdict=inconclusive")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


def test_verdict_open_still_works(api_client, db_session):
    """AC2: ?verdict=open returns 200 and returns cases with no logged verdict."""
    _seed_case(db_session)  # no verdict = open
    _seed_case(db_session, verdict_outcome="confirmed")  # has verdict, excluded
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


# ---------------------------------------------------------------------------
# AC3: _VALID_VERDICT_PARAMS is referenced in the source file (not dead code)
# ---------------------------------------------------------------------------

def test_valid_verdict_params_constant_is_referenced():
    """AC3: _VALID_VERDICT_PARAMS appears more than once in cases.py — i.e., it is
    both defined and used, not merely declared and ignored."""
    import inspect
    from app.routers import cases
    source = inspect.getsource(cases)
    count = source.count("_VALID_VERDICT_PARAMS")
    assert count >= 2, (
        f"_VALID_VERDICT_PARAMS should appear at least twice (definition + use), "
        f"but found {count} occurrence(s)"
    )
