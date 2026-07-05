"""Tests for issue #124: Centralize verdict validation logic.

The stage and verdict query-parameter validation blocks share the same pattern.
A shared helper function should be extracted so the logic lives in one place.

AC coverage:
  AC1 – A shared helper function exists in app/routers/cases.py that accepts a
         param name, value, and valid-values set and raises HTTPException(400)
         for invalid values with a descriptive message.
  AC2 – The helper is used for both stage and verdict validation (no inline
         duplication — each validation site calls the helper rather than repeating
         the raise-HTTPException block).
  AC3 – Existing behavior is unchanged: invalid stage returns 400, invalid verdict
         returns 400, valid values return 200 with correct filtering.
  AC4 – The error messages produced by the helper match the format already tested
         by the existing test_issue_71.py suite (value echoed, valid values listed).
"""
import inspect
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers
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


def _seed_case(session, stage="sharpened", verdict_outcome=None):
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened="A hypothesis",
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
# AC1: Helper function exists and raises HTTPException(400) for invalid values
# ---------------------------------------------------------------------------

def test_validation_helper_exists_in_cases_module():
    """AC1: A validation helper callable is importable from app.routers.cases."""
    from app.routers import cases
    # The helper may be named _validate_query_param or similar.
    # We search for a callable whose source contains HTTPException logic for
    # invalid values — without hard-coding a specific name.
    helpers = [
        name for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    assert helpers, (
        "No validation helper function found in app.routers.cases. "
        "Expected a function whose name starts with '_validate' to centralize "
        "query-parameter validation."
    )


def test_validation_helper_raises_400_for_invalid_value():
    """AC1: The helper raises HTTPException(400) when value is not in valid set."""
    from fastapi import HTTPException
    from app.routers import cases

    helpers = [
        obj for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    assert helpers, "No _validate* helper found"
    helper = helpers[0]

    with pytest.raises(HTTPException) as exc_info:
        helper("myfield", "bad_value", {"good", "values"})
    assert exc_info.value.status_code == 400


def test_validation_helper_does_not_raise_for_valid_value():
    """AC1: The helper is a no-op when value is in the valid set."""
    from fastapi import HTTPException
    from app.routers import cases

    helpers = [
        obj for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    helper = helpers[0]

    # Should not raise
    helper("myfield", "good", {"good", "values"})


def test_validation_helper_does_not_raise_for_none_value():
    """AC1: The helper is a no-op when value is None (param omitted)."""
    from app.routers import cases

    helpers = [
        obj for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    helper = helpers[0]

    # Should not raise
    helper("myfield", None, {"good", "values"})


def test_validation_helper_error_message_includes_bad_value():
    """AC4: Error detail echoes the invalid value back to the caller."""
    from fastapi import HTTPException
    from app.routers import cases

    helpers = [
        obj for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    helper = helpers[0]

    with pytest.raises(HTTPException) as exc_info:
        helper("myfield", "oops", {"a", "b"})
    assert "oops" in exc_info.value.detail


def test_validation_helper_error_message_lists_valid_values():
    """AC4: Error detail lists the valid values so the client knows what to use."""
    from fastapi import HTTPException
    from app.routers import cases

    helpers = [
        obj for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    helper = helpers[0]

    with pytest.raises(HTTPException) as exc_info:
        helper("myfield", "oops", {"alpha", "beta"})
    detail = exc_info.value.detail
    assert "alpha" in detail or "beta" in detail, (
        f"Expected valid values in error detail, got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# AC2: Helper is used at both validation sites (no inline duplication)
# ---------------------------------------------------------------------------

def test_helper_called_at_both_validation_sites():
    """AC2: The source of list_cases references the helper for both stage and verdict."""
    from app.routers import cases

    helpers = [
        name for name, obj in inspect.getmembers(cases, inspect.isfunction)
        if name.startswith("_validate")
    ]
    assert helpers, "No _validate* helper found"
    helper_name = helpers[0]

    source = inspect.getsource(cases.list_cases)
    call_count = source.count(helper_name)
    assert call_count >= 2, (
        f"Expected the helper '{helper_name}' to be called at least twice in "
        f"list_cases (once for stage, once for verdict), but found {call_count} call(s)."
    )


def test_no_inline_raise_httpexception_for_invalid_params_in_list_cases():
    """AC2: list_cases should not contain inline raise HTTPException for invalid
    stage/verdict — those must go through the shared helper."""
    from app.routers import cases

    source = inspect.getsource(cases.list_cases)
    # Count raw HTTPException raises inside list_cases (not counting the helper itself)
    raw_raises = [
        line for line in source.splitlines()
        if "raise HTTPException" in line and "400" in line
    ]
    # All 400 raises should have been moved into the helper
    assert len(raw_raises) == 0, (
        f"Found inline 'raise HTTPException(status_code=400, ...)' in list_cases. "
        f"These should be delegated to the shared helper. Lines:\n"
        + "\n".join(raw_raises)
    )


# ---------------------------------------------------------------------------
# AC3: Existing behavior unchanged
# ---------------------------------------------------------------------------

def test_invalid_stage_still_returns_400(api_client):
    """AC3: ?stage=bogus still returns 400 after the refactor."""
    r = api_client.get("/api/cases?stage=bogus")
    assert r.status_code == 400
    assert "bogus" in r.json()["detail"]


def test_invalid_verdict_still_returns_400(api_client):
    """AC3: ?verdict=bogus still returns 400 after the refactor."""
    r = api_client.get("/api/cases?verdict=bogus")
    assert r.status_code == 400
    assert "bogus" in r.json()["detail"]


def test_valid_stage_returns_200(api_client, db_session):
    """AC3: Valid stage values still work."""
    _seed_case(db_session, stage="sharpened")
    r = api_client.get("/api/cases?stage=sharpened")
    assert r.status_code == 200


def test_valid_verdict_returns_200(api_client, db_session):
    """AC3: Valid verdict values still work."""
    _seed_case(db_session, verdict_outcome="confirmed")
    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


def test_no_params_returns_200(api_client, db_session):
    """AC3: Omitting both params still returns all cases."""
    _seed_case(db_session)
    r = api_client.get("/api/cases")
    assert r.status_code == 200
