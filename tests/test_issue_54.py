"""Tests for issue #54: GET /api/verdicts keyword search should filter at database layer.

AC coverage:
  AC1 – When `keyword` query param is provided, SQL LIKE filter is used (not Python post-filter).
  AC2 – Filter applies to both `notes` (Verdict) and `sharpened` (Case), case-insensitive OR.
  AC3 – No in-memory list comprehension filtering on keyword remains in app/routers/verdicts.py.
  AC4 – GET /api/verdicts?keyword=<term> returns the same result set as before the refactor.
  AC5 – GET /api/verdicts with no keyword returns all verdicts unfiltered.
  AC6 – Endpoint remains compatible with outcome, ordering when keyword is also present.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


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


def _seed_verdict(session, outcome, notes, sharpened, probe_type="lab-test",
                  target_metric="metric", decided_at=None):
    from app import models

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
        type=probe_type,
        target_metric=target_metric,
        status=outcome,
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes=notes,
        decided_at=decided_at or datetime.now(tz=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return verdict.id, case.id, probe.id


# ---------------------------------------------------------------------------
# AC3: No in-memory list comprehension filtering on keyword in verdicts.py
# ---------------------------------------------------------------------------


def test_no_in_memory_keyword_list_comprehension():
    """AC3: No list comprehension over fetched verdicts for keyword filtering."""
    import pathlib

    # Read from disk to avoid stale module cache.
    source = pathlib.Path("app/routers/verdicts.py").read_text()
    # The old in-memory filter used patterns like:
    #   keyword in v.notes.lower()
    #   keyword in v.probe.case.sharpened.lower()
    # These must be gone after the SQL-layer refactor.
    assert "keyword in v.notes.lower()" not in source, (
        "In-memory notes keyword filter still present — must be a SQL LIKE predicate."
    )
    assert "keyword in v.probe" not in source, (
        "In-memory sharpened keyword filter still present — must be a SQL LIKE predicate."
    )


# ---------------------------------------------------------------------------
# AC1 + AC4: GET /api/verdicts?keyword=<term> returns correct results
# ---------------------------------------------------------------------------


def test_keyword_param_filters_by_notes(api_client, db_session):
    """AC1/AC4: ?keyword= filters verdicts whose notes contain the term."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "unrelated snippet")
    _seed_verdict(db_session, "confirmed", "no match here", "another snippet")

    r = api_client.get("/api/verdicts?keyword=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "revenue" in data[0]["notes"].lower()


def test_keyword_param_filters_by_sharpened(api_client, db_session):
    """AC1/AC4: ?keyword= filters verdicts whose case sharpened field contains the term."""
    _seed_verdict(db_session, "confirmed", "some note", "revenue dropped 20%")
    _seed_verdict(db_session, "confirmed", "other note", "unrelated snippet")

    r = api_client.get("/api/verdicts?keyword=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "revenue" in data[0]["case"]["sharpened_snippet"].lower()


def test_keyword_matches_either_notes_or_sharpened(api_client, db_session):
    """AC2: A verdict matches if the keyword is in notes OR sharpened (OR logic)."""
    _seed_verdict(db_session, "confirmed", "revenue in notes", "unrelated")
    _seed_verdict(db_session, "confirmed", "unrelated note", "revenue in sharpened")
    _seed_verdict(db_session, "killed", "no match", "no match")

    r = api_client.get("/api/verdicts?keyword=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


def test_keyword_only_sharpened_match(api_client, db_session):
    """AC2/UAT5: Verdict with keyword only in case sharpened (not notes) is returned."""
    _seed_verdict(db_session, "confirmed", "notes do not mention it", "only here: alpha")
    _seed_verdict(db_session, "killed", "nothing relevant", "nothing relevant either")

    r = api_client.get("/api/verdicts?keyword=alpha")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "alpha" in data[0]["case"]["sharpened_snippet"].lower()


# ---------------------------------------------------------------------------
# AC2: Case-insensitive matching
# ---------------------------------------------------------------------------


def test_keyword_lowercase_matches(api_client, db_session):
    """AC2: Lowercase keyword matches mixed-case stored value."""
    _seed_verdict(db_session, "confirmed", "Revenue Confirmed", "snippet")

    r = api_client.get("/api/verdicts?keyword=revenue")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_keyword_uppercase_matches(api_client, db_session):
    """AC2/UAT2: Uppercase keyword returns same records as lowercase."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "snippet")

    r_lower = api_client.get("/api/verdicts?keyword=revenue")
    r_upper = api_client.get("/api/verdicts?keyword=REVENUE")

    assert r_lower.status_code == 200
    assert r_upper.status_code == 200
    assert len(r_lower.json()) == 1
    assert len(r_upper.json()) == 1
    assert r_lower.json()[0]["id"] == r_upper.json()[0]["id"]


def test_keyword_mixed_case_matches(api_client, db_session):
    """AC2: Mixed-case keyword matches correctly."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "snippet")

    r = api_client.get("/api/verdicts?keyword=ReVeNuE")
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# AC4: Non-matching keyword returns empty array
# ---------------------------------------------------------------------------


def test_keyword_no_match_returns_empty(api_client, db_session):
    """AC4: Keyword with no matching records returns 200 with []."""
    _seed_verdict(db_session, "confirmed", "note", "snippet")

    r = api_client.get("/api/verdicts?keyword=zzznomatch")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# AC5: No keyword returns all verdicts
# ---------------------------------------------------------------------------


def test_no_keyword_returns_all_verdicts(api_client, db_session):
    """AC5: Omitting keyword returns all verdicts unfiltered."""
    _seed_verdict(db_session, "confirmed", "note1", "snip1")
    _seed_verdict(db_session, "killed", "note2", "snip2")
    _seed_verdict(db_session, "inconclusive", "note3", "snip3")

    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# AC6: keyword + outcome combined (AND logic)
# ---------------------------------------------------------------------------


def test_keyword_combined_with_outcome(api_client, db_session):
    """AC6: ?keyword=<term>&outcome=confirmed returns only confirmed verdicts matching keyword."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "snip1")
    _seed_verdict(db_session, "confirmed", "no keyword here", "snip2")
    _seed_verdict(db_session, "killed", "revenue killed", "snip3")

    r = api_client.get("/api/verdicts?keyword=revenue&outcome=confirmed")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "confirmed"
    assert "revenue" in data[0]["notes"].lower()


def test_keyword_with_outcome_and_logic(api_client, db_session):
    """AC6: Both keyword and outcome must match (AND, not OR)."""
    _seed_verdict(db_session, "killed", "revenue note", "snip")

    r = api_client.get("/api/verdicts?keyword=revenue&outcome=confirmed")
    assert r.status_code == 200
    assert r.json() == []


def test_keyword_ordering_preserved(api_client, db_session):
    """AC6: keyword filter preserves newest-first ordering."""
    now = datetime.now(tz=timezone.utc)
    older_id, _, _ = _seed_verdict(
        db_session, "confirmed", "revenue older", "snip",
        decided_at=now - timedelta(hours=2)
    )
    newer_id, _, _ = _seed_verdict(
        db_session, "confirmed", "revenue newer", "snip",
        decided_at=now
    )

    r = api_client.get("/api/verdicts?keyword=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["id"] == newer_id, "Newest result must come first"
    assert data[1]["id"] == older_id


def test_keyword_invalid_outcome_still_400(api_client):
    """AC6: ?keyword=<term>&outcome=<invalid> still returns HTTP 400."""
    r = api_client.get("/api/verdicts?keyword=revenue&outcome=notvalid")
    assert r.status_code == 400
