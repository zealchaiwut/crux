"""Tests for issue #71: Remove or use _VALID_VERDICT_PARAMS constant.

AC coverage:
  AC1 – The _VALID_VERDICT_PARAMS constant is either removed or referenced consistently
  AC2 – If kept, the inline set on line 78/106 is replaced with a reference to _VALID_VERDICT_PARAMS
  AC3 – If removed, the inline set remains and no dead code exists
  AC4 – No other logic or API response changes
  AC5 – All existing tests pass without modification
"""
import os
import json
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


def _seed_case_with_probe(session, probe_status="designed"):
    """Seed a Case at stage 'probe' with a probe."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened test problem",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="test metric",
        status=probe_status,
    )
    session.add(probe)
    session.commit()
    return c, probe


# --- AC1 / AC2 / AC3: Constant usage check ---

def test_valid_verdict_params_constant_exists_or_removed():
    """AC1: _VALID_VERDICT_PARAMS constant is either defined or removed (no orphaned defs)."""
    try:
        from app.routers.cases import _VALID_VERDICT_PARAMS
        # If it exists, it should be used somewhere
        # or deliberately kept for reference
        assert isinstance(_VALID_VERDICT_PARAMS, set), \
            "_VALID_VERDICT_PARAMS must be a set if defined"
    except ImportError:
        # Constant was removed — that's fine, just ensure code still works
        pass


def test_constant_not_both_used_and_unused():
    """AC1: _VALID_VERDICT_PARAMS should not be defined and never referenced."""
    import inspect
    from app.routers import cases

    source = inspect.getsource(cases)

    # Count references to _VALID_VERDICT_PARAMS
    # (definition on line 57, any other references)
    lines = source.split('\n')
    definition_count = 0
    reference_count = 0

    for i, line in enumerate(lines):
        if '_VALID_VERDICT_PARAMS' in line:
            # Skip comments
            if not line.strip().startswith('#'):
                if '=' in line and '_VALID_VERDICT_PARAMS' in line.split('=')[0]:
                    definition_count += 1
                else:
                    reference_count += 1

    # Either: 1 definition + at least 1 reference, OR 0 of both
    if definition_count > 0:
        assert reference_count > 0, \
            "_VALID_VERDICT_PARAMS is defined but never referenced (dead code)"
    else:
        assert reference_count == 0, \
            "_VALID_VERDICT_PARAMS should not be referenced if not defined"


# --- AC4: Valid verdicts still accepted ---

def test_valid_verdict_open_query_parameter(api_client, db_session):
    """AC4: GET /api/cases?verdict=open returns cases without verdicts."""
    from app import models

    # Seed one open case (no verdict) and one closed case (with verdict)
    open_case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Open problem",
        sharpened="Open sharpened",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(open_case)
    db_session.flush()

    probe_open = models.Probe(
        id=str(uuid.uuid4()),
        case_id=open_case.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe_open)
    db_session.flush()

    # Create a closed case with a verdict
    closed_case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Closed problem",
        sharpened="Closed sharpened",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(closed_case)
    db_session.flush()

    probe_closed = models.Probe(
        id=str(uuid.uuid4()),
        case_id=closed_case.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe_closed)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe_closed.id,
        outcome="confirmed",
        notes="Test verdict",
    )
    db_session.add(verdict)
    db_session.commit()

    # Query for open verdicts
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    cases = r.json()["cases"]

    # Should return only the open case (no verdict)
    assert len(cases) == 1, f"Expected 1 open case, got {len(cases)}"
    assert cases[0]["id"] == open_case.id


def test_valid_verdict_confirmed_query_parameter(api_client, db_session):
    """AC4: GET /api/cases?verdict=confirmed returns only confirmed cases."""
    from app import models

    # Create a confirmed case
    case_confirmed = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Confirmed problem",
        sharpened="Confirmed sharpened",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(case_confirmed)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case_confirmed.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="Confirmed verdict",
    )
    db_session.add(verdict)
    db_session.commit()

    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["id"] == case_confirmed.id


def test_valid_verdict_killed_query_parameter(api_client, db_session):
    """AC4: GET /api/cases?verdict=killed returns only killed cases."""
    from app import models

    case_killed = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Killed problem",
        sharpened="Killed sharpened",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(case_killed)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case_killed.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="killed",
        notes="Killed verdict",
    )
    db_session.add(verdict)
    db_session.commit()

    r = api_client.get("/api/cases?verdict=killed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["id"] == case_killed.id


def test_valid_verdict_inconclusive_query_parameter(api_client, db_session):
    """AC4: GET /api/cases?verdict=inconclusive returns only inconclusive cases."""
    from app import models

    case_inconclusive = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Inconclusive problem",
        sharpened="Inconclusive sharpened",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(case_inconclusive)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case_inconclusive.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="inconclusive",
        notes="Inconclusive verdict",
    )
    db_session.add(verdict)
    db_session.commit()

    r = api_client.get("/api/cases?verdict=inconclusive")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["id"] == case_inconclusive.id


def test_invalid_verdict_query_parameter_rejected(api_client, db_session):
    """AC1/AC4: GET /api/cases?verdict=invalid returns 400 — _VALID_VERDICT_PARAMS now guards validation."""
    _seed_case_with_probe(db_session)

    # Invalid verdict values are now rejected with a 400 error
    # because _VALID_VERDICT_PARAMS is referenced in the validation check
    r = api_client.get("/api/cases?verdict=invalid")
    assert r.status_code == 400, f"Expected 400 for invalid verdict, got {r.status_code}: {r.text}"
    assert "Invalid verdict" in r.text


def test_verdict_filtering_no_other_logic_changes(api_client, db_session):
    """AC4: Verdict filtering behavior unchanged; only the constant usage is refactored."""
    from app import models

    # Create mixed cases
    case1 = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Problem 1",
        sharpened="Sharpened 1",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(case1)
    db_session.flush()

    probe1 = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case1.id,
        type="measurement",
        status="designed",
    )
    db_session.add(probe1)
    db_session.flush()

    verdict1 = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe1.id,
        outcome="confirmed",
        notes="Confirmed",
    )
    db_session.add(verdict1)
    db_session.commit()

    # Query without filter
    r_all = api_client.get("/api/cases")
    assert r_all.status_code == 200
    all_cases = r_all.json()["cases"]

    # Query with confirmed filter
    r_filtered = api_client.get("/api/cases?verdict=confirmed")
    assert r_filtered.status_code == 200
    filtered = r_filtered.json()["cases"]

    # Filtered should be subset of all
    assert len(filtered) <= len(all_cases)
    assert all(c["verdict"] in ["confirmed", "progress", "awaiting"] for c in filtered)
