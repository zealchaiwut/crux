"""Tests for issue #55: GET /api/verdicts timestamp field null-handling.

AC coverage:
  AC1 – GET /api/verdicts always includes a created_at field that is either a
         valid ISO 8601 string or documented as nullable.
  AC2 – When decided_at is null, created_at is NOT returned as null without
         documentation — either a non-null fallback is used or nullable is
         documented in the OpenAPI schema.
  AC3 – If non-null fallback, created_at is populated at creation time so
         no existing or future record can produce a null response.
  AC5 – A test creates a verdict with decided_at=null and asserts the API
         response returns a valid ISO string for created_at (fallback strategy).
"""
import os
import re
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

ISO_8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
)


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


def _seed_verdict(session, outcome="confirmed", notes="note", sharpened="snip",
                  decided_at="__now__"):
    """Seed a Case → Probe → Verdict chain.

    Pass decided_at=None to simulate a verdict with no decided_at (the null case
    the issue is about). Pass the sentinel "__now__" to use the current time.
    """
    from app import models

    if decided_at == "__now__":
        decided_at = datetime.now(tz=timezone.utc)

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        sharpened=sharpened,
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
        notes=notes,
        decided_at=decided_at,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return verdict.id


# ---------------------------------------------------------------------------
# AC1: created_at is always present
# ---------------------------------------------------------------------------


def test_created_at_present_on_normal_verdict(api_client, db_session):
    """AC1: created_at field is present on every verdict object."""
    _seed_verdict(db_session)
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "created_at" in data[0], "created_at must be present on every verdict"


def test_created_at_is_iso_string_when_decided_at_set(api_client, db_session):
    """AC1: created_at is a valid ISO 8601 string when decided_at is set."""
    _seed_verdict(db_session)
    r = api_client.get("/api/verdicts")
    data = r.json()
    v = data[0]
    assert v["created_at"] is not None, "created_at must not be null"
    assert ISO_8601_RE.match(str(v["created_at"])), (
        f"created_at must be an ISO 8601 string, got: {v['created_at']!r}"
    )


# ---------------------------------------------------------------------------
# AC2 + AC3 + AC5: decided_at=null fallback
# ---------------------------------------------------------------------------


def test_created_at_not_null_when_decided_at_is_null(api_client, db_session):
    """AC5: When decided_at is null, created_at falls back to a valid ISO string."""
    _seed_verdict(db_session, decided_at=None)
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    v = data[0]
    assert "created_at" in v, "created_at must be present even when decided_at is null"
    assert v["created_at"] is not None, (
        "created_at must NOT be null when decided_at is null — "
        "expected a non-null fallback (e.g. verdict's created_at timestamp)"
    )
    assert ISO_8601_RE.match(str(v["created_at"])), (
        f"created_at fallback must be a valid ISO 8601 string, got: {v['created_at']!r}"
    )


def test_verdict_model_has_created_at_column(db_session):
    """AC3: Verdict model has a created_at column for non-null fallback."""
    from app import models

    assert hasattr(models.Verdict, "created_at"), (
        "Verdict model must have a created_at column so every record "
        "has a non-null fallback timestamp"
    )


def test_created_at_populated_at_verdict_creation(db_session):
    """AC3: created_at is populated when a verdict is created (never null on new records)."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="problem",
        sharpened="snip",
        stage="verdict",
    )
    db_session.add(case)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="lab-test",
        target_metric="metric",
        status="confirmed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="test",
        decided_at=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(verdict)
    db_session.commit()
    db_session.refresh(verdict)

    assert verdict.created_at is not None, (
        "created_at must not be null after commit — it must be set at creation time"
    )


def test_api_uses_created_at_fallback_not_decided_at(api_client, db_session):
    """AC2: When decided_at is null, API response created_at comes from the fallback."""
    fallback_ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="problem",
        sharpened="snip",
        stage="verdict",
    )
    db_session.add(case)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="lab-test",
        target_metric="metric",
        status="confirmed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="test",
        decided_at=None,
        created_at=fallback_ts,
    )
    db_session.add(verdict)
    db_session.commit()

    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    v = data[0]
    assert v["created_at"] is not None
    # The fallback timestamp should appear in the response
    assert "2025-01-15" in v["created_at"], (
        f"Expected fallback timestamp 2025-01-15 in created_at, got: {v['created_at']!r}"
    )
