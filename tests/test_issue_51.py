"""Tests for issue #51: Add GET /api/verdicts list endpoint.

AC coverage:
  AC1  – GET /api/verdicts returns HTTP 200 with JSON array, ordered newest-first.
  AC2  – Each verdict includes id, outcome, notes, created_at; probe.type,
          probe.target_metric; case.id, case.sharpened_snippet.
  AC3  – ?outcome=confirmed filters to confirmed verdicts only.
  AC4  – ?outcome=killed filters to killed verdicts only.
  AC5  – ?outcome=inconclusive filters to inconclusive verdicts only.
  AC6  – ?outcome=<invalid> returns HTTP 400 with descriptive error.
  AC7  – ?q=<keyword> returns only verdicts matching keyword in sharpened_snippet or notes (case-insensitive).
  AC8  – ?outcome and ?q can be combined (AND logic).
  AC9  – No matching verdicts returns HTTP 200 with empty array.
  AC10 – Omitting all query params returns all verdicts unfiltered.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

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


def _seed_verdict(session, outcome, notes, sharpened, probe_type="lab-test",
                  target_metric="metric", decided_at=None):
    """Seed a Case → Probe → Verdict chain and return the verdict id."""
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
# AC1 + AC10: GET /api/verdicts returns 200 with array of all verdicts
# ---------------------------------------------------------------------------


def test_verdicts_list_returns_200(api_client):
    """AC1: GET /api/verdicts returns HTTP 200."""
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200


def test_verdicts_list_returns_array(api_client):
    """AC1/AC10: Response is a JSON array."""
    r = api_client.get("/api/verdicts")
    data = r.json()
    assert isinstance(data, list)


def test_verdicts_list_returns_all_unfiltered(api_client, db_session):
    """AC10: Omitting all query params returns all verdicts."""
    _seed_verdict(db_session, "confirmed", "note1", "snip1")
    _seed_verdict(db_session, "killed", "note2", "snip2")
    _seed_verdict(db_session, "inconclusive", "note3", "snip3")

    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3


def test_verdicts_list_ordered_newest_first(api_client, db_session):
    """AC1: Results are ordered newest-first by creation timestamp."""
    now = datetime.now(tz=timezone.utc)
    older_id, _, _ = _seed_verdict(db_session, "confirmed", "older", "snip",
                                    decided_at=now - timedelta(hours=2))
    newer_id, _, _ = _seed_verdict(db_session, "confirmed", "newer", "snip",
                                    decided_at=now)

    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["id"] == newer_id, "Newest verdict must come first"
    assert data[1]["id"] == older_id


# ---------------------------------------------------------------------------
# AC2: Each verdict object has the required fields
# ---------------------------------------------------------------------------


def test_verdict_object_has_required_top_level_fields(api_client, db_session):
    """AC2: Each verdict includes id, outcome, notes, created_at."""
    _seed_verdict(db_session, "confirmed", "a note", "a snippet")
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    v = data[0]
    for field in ("id", "outcome", "notes", "created_at"):
        assert field in v, f"Verdict must include field: {field}"


def test_verdict_object_has_nested_probe(api_client, db_session):
    """AC2: Each verdict includes nested probe with type and target_metric."""
    _seed_verdict(db_session, "confirmed", "note", "snip",
                  probe_type="measurement", target_metric="weight kg")
    r = api_client.get("/api/verdicts")
    v = r.json()[0]
    assert "probe" in v, "Verdict must include nested 'probe' object"
    assert "type" in v["probe"]
    assert "target_metric" in v["probe"]
    assert v["probe"]["type"] == "measurement"
    assert v["probe"]["target_metric"] == "weight kg"


def test_verdict_object_has_nested_case(api_client, db_session):
    """AC2: Each verdict includes nested case with id and sharpened_snippet."""
    v_id, case_id, _ = _seed_verdict(db_session, "confirmed", "note", "my snip")
    r = api_client.get("/api/verdicts")
    v = r.json()[0]
    assert "case" in v, "Verdict must include nested 'case' object"
    assert "id" in v["case"]
    assert "sharpened_snippet" in v["case"]
    assert v["case"]["id"] == case_id
    assert v["case"]["sharpened_snippet"] == "my snip"


def test_verdict_outcome_and_notes_values(api_client, db_session):
    """AC2: outcome and notes values are returned correctly."""
    _seed_verdict(db_session, "killed", "hypothesis refuted", "some snippet")
    r = api_client.get("/api/verdicts")
    v = r.json()[0]
    assert v["outcome"] == "killed"
    assert v["notes"] == "hypothesis refuted"


# ---------------------------------------------------------------------------
# AC3: ?outcome=confirmed filter
# ---------------------------------------------------------------------------


def test_outcome_filter_confirmed(api_client, db_session):
    """AC3: ?outcome=confirmed returns only confirmed verdicts."""
    _seed_verdict(db_session, "confirmed", "note1", "snip1")
    _seed_verdict(db_session, "killed", "note2", "snip2")
    _seed_verdict(db_session, "inconclusive", "note3", "snip3")

    r = api_client.get("/api/verdicts?outcome=confirmed")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "confirmed"


# ---------------------------------------------------------------------------
# AC4: ?outcome=killed filter
# ---------------------------------------------------------------------------


def test_outcome_filter_killed(api_client, db_session):
    """AC4: ?outcome=killed returns only killed verdicts."""
    _seed_verdict(db_session, "confirmed", "note1", "snip1")
    _seed_verdict(db_session, "killed", "note2", "snip2")
    _seed_verdict(db_session, "inconclusive", "note3", "snip3")

    r = api_client.get("/api/verdicts?outcome=killed")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "killed"


# ---------------------------------------------------------------------------
# AC5: ?outcome=inconclusive filter
# ---------------------------------------------------------------------------


def test_outcome_filter_inconclusive(api_client, db_session):
    """AC5: ?outcome=inconclusive returns only inconclusive verdicts."""
    _seed_verdict(db_session, "confirmed", "note1", "snip1")
    _seed_verdict(db_session, "killed", "note2", "snip2")
    _seed_verdict(db_session, "inconclusive", "note3", "snip3")

    r = api_client.get("/api/verdicts?outcome=inconclusive")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "inconclusive"


# ---------------------------------------------------------------------------
# AC6: ?outcome=<invalid> returns HTTP 400
# ---------------------------------------------------------------------------


def test_invalid_outcome_returns_400(api_client):
    """AC6: ?outcome=<invalid> returns HTTP 400."""
    r = api_client.get("/api/verdicts?outcome=invalid_value")
    assert r.status_code == 400


def test_invalid_outcome_has_error_message(api_client):
    """AC6: HTTP 400 response includes a descriptive error message."""
    r = api_client.get("/api/verdicts?outcome=maybe")
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body or "error" in body or "message" in body


# ---------------------------------------------------------------------------
# AC7: ?q= keyword search (case-insensitive, sharpened_snippet OR notes)
# ---------------------------------------------------------------------------


def test_q_filter_matches_sharpened_snippet(api_client, db_session):
    """AC7: ?q= matches keyword in case's sharpened_snippet."""
    _seed_verdict(db_session, "confirmed", "some note", "revenue dropped 20%")
    _seed_verdict(db_session, "confirmed", "other note", "unrelated snippet")

    r = api_client.get("/api/verdicts?q=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "revenue" in data[0]["case"]["sharpened_snippet"].lower()


def test_q_filter_matches_notes(api_client, db_session):
    """AC7: ?q= matches keyword in verdict's notes."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "some snippet")
    _seed_verdict(db_session, "confirmed", "unrelated note", "another snippet")

    r = api_client.get("/api/verdicts?q=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert "revenue" in data[0]["notes"].lower()


def test_q_filter_is_case_insensitive(api_client, db_session):
    """AC7: ?q= search is case-insensitive."""
    _seed_verdict(db_session, "confirmed", "Revenue dropped", "some snippet")

    r_lower = api_client.get("/api/verdicts?q=revenue")
    r_upper = api_client.get("/api/verdicts?q=REVENUE")
    r_mixed = api_client.get("/api/verdicts?q=ReVeNuE")

    assert r_lower.status_code == 200
    assert r_upper.status_code == 200
    assert r_mixed.status_code == 200
    assert len(r_lower.json()) == 1
    assert len(r_upper.json()) == 1
    assert len(r_mixed.json()) == 1


def test_q_filter_matches_either_field(api_client, db_session):
    """AC7: ?q= matches if keyword appears in either sharpened_snippet OR notes."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "unrelated")
    _seed_verdict(db_session, "confirmed", "unrelated note", "revenue dropped")
    _seed_verdict(db_session, "killed", "no match", "no match")

    r = api_client.get("/api/verdicts?q=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# AC8: ?outcome and ?q can be combined (AND logic)
# ---------------------------------------------------------------------------


def test_combined_outcome_and_q_filters(api_client, db_session):
    """AC8: ?outcome=confirmed&q=revenue returns only confirmed verdicts matching keyword."""
    _seed_verdict(db_session, "confirmed", "revenue confirmed", "snip1")
    _seed_verdict(db_session, "confirmed", "no keyword here", "snip2")
    _seed_verdict(db_session, "killed", "revenue killed", "snip3")

    r = api_client.get("/api/verdicts?outcome=confirmed&q=revenue")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "confirmed"
    assert "revenue" in data[0]["notes"].lower()


def test_combined_filters_and_logic(api_client, db_session):
    """AC8: Both filters must match (AND, not OR)."""
    _seed_verdict(db_session, "killed", "revenue note", "snip")

    # outcome=confirmed with q=revenue — the above verdict is killed, so no match
    r = api_client.get("/api/verdicts?outcome=confirmed&q=revenue")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# AC9: No matching verdicts → HTTP 200 with empty array
# ---------------------------------------------------------------------------


def test_no_match_returns_empty_array(api_client, db_session):
    """AC9: When no verdicts match filters, returns HTTP 200 with []."""
    _seed_verdict(db_session, "confirmed", "note", "snip")

    r = api_client.get("/api/verdicts?q=zzznomatchzzz")
    assert r.status_code == 200
    assert r.json() == []


def test_empty_db_returns_empty_array(api_client):
    """AC9: With no verdicts in the database, returns HTTP 200 with []."""
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    assert r.json() == []
