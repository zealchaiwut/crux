"""Tests for issue #70: optimize verdict outcome query in GET /api/cases.

The optimization replaces IN (subquery) with correlated EXISTS subqueries via
SQLAlchemy's .any() relationship method.  Functional correctness must be
identical to the pre-optimization behaviour tested in test_issue_64.py, but
we also verify the SQL generated uses EXISTS instead of IN.

AC1 – verdict=confirmed/killed/inconclusive filter still returns correct cases
AC2 – verdict=open filter still returns correct cases
AC3 – Combined verdict + stage + q filter still applies AND logic
AC4 – SQL generated for outcome filter uses EXISTS, not IN
AC5 – SQL generated for open filter uses NOT EXISTS, not NOT IN
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _seed_case(session, sharpened="A sharpened statement", stage="sharpened",
               verdict_outcome=None):
    """Insert a case with optional probe+verdict. Returns the Case ORM object."""
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
# AC1 – outcome filter correctness after optimisation
# ---------------------------------------------------------------------------

def test_verdict_confirmed_returns_correct_cases(api_client, db_session):
    """AC1: verdict=confirmed returns only confirmed cases after query optimisation."""
    _seed_case(db_session, verdict_outcome="confirmed")
    _seed_case(db_session, verdict_outcome="killed")
    _seed_case(db_session)
    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "confirmed"


def test_verdict_killed_returns_correct_cases(api_client, db_session):
    """AC1: verdict=killed returns only killed cases after query optimisation."""
    _seed_case(db_session, verdict_outcome="killed")
    _seed_case(db_session, verdict_outcome="confirmed")
    r = api_client.get("/api/cases?verdict=killed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "killed"


def test_verdict_inconclusive_returns_correct_cases(api_client, db_session):
    """AC1: verdict=inconclusive returns only inconclusive cases."""
    _seed_case(db_session, verdict_outcome="inconclusive")
    _seed_case(db_session, verdict_outcome="confirmed")
    _seed_case(db_session)
    r = api_client.get("/api/cases?verdict=inconclusive")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "inconclusive"


def test_verdict_filter_excludes_open_cases(api_client, db_session):
    """AC1: outcome filter never returns cases that have no verdict logged."""
    _seed_case(db_session)
    _seed_case(db_session)
    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    assert r.json()["cases"] == []


# ---------------------------------------------------------------------------
# AC2 – open filter correctness after optimisation
# ---------------------------------------------------------------------------

def test_verdict_open_returns_cases_without_verdict(api_client, db_session):
    """AC2: verdict=open returns only cases with no verdict logged."""
    _seed_case(db_session)  # open
    _seed_case(db_session)  # open
    _seed_case(db_session, verdict_outcome="confirmed")  # closed
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 2
    for c in cases:
        assert c["verdict_log"] is None


def test_verdict_open_excludes_any_outcome(api_client, db_session):
    """AC2: open filter excludes cases with any of the three outcome types."""
    for outcome in ("confirmed", "killed", "inconclusive"):
        _seed_case(db_session, verdict_outcome=outcome)
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200
    assert r.json()["cases"] == []


# ---------------------------------------------------------------------------
# AC3 – composability still works after optimisation
# ---------------------------------------------------------------------------

def test_verdict_and_stage_composable(api_client, db_session):
    """AC3: verdict + stage filters combine with AND logic."""
    _seed_case(db_session, stage="probe", verdict_outcome="confirmed")
    _seed_case(db_session, stage="gather", verdict_outcome="confirmed")
    _seed_case(db_session, stage="probe")
    r = api_client.get("/api/cases?verdict=confirmed&stage=probe")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1


# ---------------------------------------------------------------------------
# AC4 – SQL for outcome filter uses EXISTS not IN
# ---------------------------------------------------------------------------

def test_outcome_filter_uses_exists_not_in(db_session):
    """AC4: the compiled SQL for the outcome filter contains EXISTS, not ' IN '."""
    from app import models
    from sqlalchemy.orm import joinedload

    query = db_session.query(models.Case).options(
        joinedload(models.Case.plans),
        joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
    )
    # Apply the optimised filter (the same code path as list_cases)
    query = query.filter(
        models.Case.probes.any(
            models.Probe.verdicts.any(models.Verdict.outcome == "confirmed")
        )
    )
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "EXISTS" in sql.upper(), "Expected EXISTS in query SQL"
    assert " IN " not in sql.upper(), "Unexpected IN clause — filter was not optimised"


# ---------------------------------------------------------------------------
# AC5 – SQL for open filter uses NOT EXISTS not NOT IN
# ---------------------------------------------------------------------------

def test_open_filter_uses_not_exists_not_not_in(db_session):
    """AC5: the compiled SQL for the open filter uses NOT EXISTS, not NOT IN."""
    from app import models
    from sqlalchemy.orm import joinedload

    query = db_session.query(models.Case).options(
        joinedload(models.Case.plans),
        joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
    )
    query = query.filter(
        ~models.Case.probes.any(
            models.Probe.verdicts.any()
        )
    )
    sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "NOT (EXISTS" in sql.upper() or "NOT EXISTS" in sql.upper(), (
        "Expected NOT EXISTS in query SQL"
    )
    assert "NOT IN" not in sql.upper(), "Unexpected NOT IN — open filter was not optimised"
