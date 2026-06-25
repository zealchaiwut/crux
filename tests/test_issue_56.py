"""Tests for issue #56: GET /api/verdicts inconsistent empty-string vs None defaults.

AC coverage:
  AC1 – When probe is absent, target_metric and type both default to None
         (same type for both).
  AC2 – The chosen default (None) is consistently applied across all
         probe-absent code paths in app/routers/verdicts.py lines 157-161.
  AC3 – GET /api/verdicts returns 2xx when probe data is absent, with no
         null/empty-string mismatch between target_metric and type.
  AC4 – Verdicts with a probe present still return actual target_metric and
         type values, unaffected by this change.
  AC5 – Unit/integration test asserts both fields share the same type (None)
         when probe is absent.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

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


def _seed_verdict_with_probe(session, probe_type="lab-test",
                              target_metric="weight kg"):
    """Seed a full Case → Probe → Verdict chain."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        sharpened="snip",
        stage="verdict",
    )
    session.add(case)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type=probe_type,
        target_metric=target_metric,
        status="confirmed",
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="note",
        decided_at=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return verdict.id


def _make_mock_verdict_with_no_probe():
    """Return a mock Verdict-like object whose .probe relationship is None.

    probe_id is NOT NULL in the schema, so this can only occur via a mock —
    the defensive `if probe else` guard in verdicts.py is the code path we
    are testing here.
    """
    v = MagicMock()
    v.id = "mock-verdict-id"
    v.outcome = "confirmed"
    v.notes = "note"
    v.decided_at = datetime.now(tz=timezone.utc)
    v.created_at = datetime.now(tz=timezone.utc)
    v.probe = None
    return v


def _make_mock_db(verdicts):
    """Return a mock Session whose query chain returns `verdicts`."""
    mock_db = MagicMock()
    mock_q = MagicMock()
    mock_db.query.return_value = mock_q
    mock_q.options.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.all.return_value = verdicts
    return mock_db


# ---------------------------------------------------------------------------
# AC1 + AC5: Both probe fields are the same type (None) when probe is absent
# ---------------------------------------------------------------------------


def _call_list_verdicts(mock_db):
    """Call list_verdicts directly, bypassing FastAPI Query descriptor defaults."""
    from app.routers.verdicts import list_verdicts
    return list_verdicts(outcome=None, q=None, keyword=None, db=mock_db)


def test_probe_absent_both_fields_are_none():
    """AC1+AC5: When probe relationship is None, both target_metric and type are None."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)

    assert len(result) == 1
    probe_obj = result[0]["probe"]
    assert probe_obj["type"] is None, (
        f"probe.type must be None when probe is absent, got {probe_obj['type']!r}"
    )
    assert probe_obj["target_metric"] is None, (
        f"probe.target_metric must be None when probe is absent, "
        f"got {probe_obj['target_metric']!r}"
    )


def test_probe_absent_both_fields_same_python_type():
    """AC5: Both fields share exactly the same Python type when probe is absent."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)
    probe_obj = result[0]["probe"]
    assert type(probe_obj["type"]) == type(probe_obj["target_metric"]), (
        f"type and target_metric must share the same Python type when probe "
        f"is absent; got type={type(probe_obj['type'])}, "
        f"target_metric={type(probe_obj['target_metric'])}"
    )


# ---------------------------------------------------------------------------
# AC2: No empty string used as default when probe is absent
# ---------------------------------------------------------------------------


def test_probe_absent_no_empty_string_for_target_metric():
    """AC2: target_metric must not default to '' when probe is absent."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)
    probe_obj = result[0]["probe"]
    assert probe_obj["target_metric"] != "", (
        "target_metric must not default to '' when probe is absent; "
        f"got {probe_obj['target_metric']!r}"
    )


def test_probe_absent_no_empty_string_for_type():
    """AC2: type must not default to '' when probe is absent."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)
    probe_obj = result[0]["probe"]
    assert probe_obj["type"] != "", (
        "type must not default to '' when probe is absent; "
        f"got {probe_obj['type']!r}"
    )


# ---------------------------------------------------------------------------
# AC3: Route returns valid response (no crash) when probe is absent
# ---------------------------------------------------------------------------


def test_probe_absent_route_does_not_raise():
    """AC3: list_verdicts does not raise when probe relationship is None."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)
    assert isinstance(result, list)
    assert len(result) == 1


def test_probe_absent_no_null_empty_string_mismatch():
    """AC3: No null/empty-string mismatch between type and target_metric."""
    mock_db = _make_mock_db([_make_mock_verdict_with_no_probe()])
    result = _call_list_verdicts(mock_db)
    probe_obj = result[0]["probe"]
    t = probe_obj["type"]
    tm = probe_obj["target_metric"]
    mismatch = (t is None and tm == "") or (t == "" and tm is None)
    assert not mismatch, (
        f"Null/empty-string mismatch: type={t!r} vs target_metric={tm!r}; "
        "both must be the same sentinel value"
    )


# ---------------------------------------------------------------------------
# AC4: Verdicts with a probe present are unaffected
# ---------------------------------------------------------------------------


def test_probe_present_returns_actual_type(api_client, db_session):
    """AC4: When probe is present, type returns its actual stored value."""
    _seed_verdict_with_probe(db_session, probe_type="measurement",
                             target_metric="weight kg")
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    probe_obj = r.json()[0]["probe"]
    assert probe_obj["type"] == "measurement", (
        f"Expected probe.type='measurement', got {probe_obj['type']!r}"
    )


def test_probe_present_returns_actual_target_metric(api_client, db_session):
    """AC4: When probe is present, target_metric returns its actual stored value."""
    _seed_verdict_with_probe(db_session, probe_type="lab-test",
                             target_metric="revenue per user")
    r = api_client.get("/api/verdicts")
    probe_obj = r.json()[0]["probe"]
    assert probe_obj["target_metric"] == "revenue per user", (
        f"Expected target_metric='revenue per user', "
        f"got {probe_obj['target_metric']!r}"
    )


def test_probe_present_200_response(api_client, db_session):
    """AC3+AC4: GET /api/verdicts returns 200 when probe is present."""
    _seed_verdict_with_probe(db_session)
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
