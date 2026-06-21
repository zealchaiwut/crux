"""Tests for issue #64: search and filter params on GET /api/cases.

AC coverage:
  AC1 – ?q=<keyword> returns cases where sharpened OR plan mechanisms contain keyword (case-insensitive)
  AC2 – ?stage=<stage_enum> returns only cases at that stage; invalid stage → 400
  AC3 – ?verdict=confirmed|killed|inconclusive returns cases with matching logged verdict
  AC4 – ?verdict=open returns cases with no logged verdict
  AC5 – All params optional; omitting any applies no filter
  AC6 – All three params composable (AND logic)
  AC7 – Empty result returns 200 with empty array
  AC8 – No params: existing behaviour unchanged
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Fixtures / helpers (mirror test_cases_list__5.py pattern)
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
               mechanisms=None, verdict_outcome=None):
    """Insert a case with optional plans and verdict. Returns the Case ORM object."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened=sharpened,
        stage=stage,
    )
    session.add(c)
    session.flush()

    if mechanisms:
        for i, mech in enumerate(mechanisms, start=1):
            label = ["A", "B", "C"][i - 1]
            plan = models.Plan(
                id=str(uuid.uuid4()),
                case_id=c.id,
                label=label,
                mechanism=mech,
                current_rank=i,
            )
            session.add(plan)
    else:
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
# AC1: ?q keyword search in sharpened statement and plan mechanisms
# ---------------------------------------------------------------------------

def test_q_matches_sharpened(api_client, db_session):
    """AC1: ?q matches keyword in sharpened statement."""
    _seed_case(db_session, sharpened="Pricing drives retention")
    _seed_case(db_session, sharpened="Unrelated topic")
    r = api_client.get("/api/cases?q=pricing")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert "Pricing" in cases[0]["title"]


def test_q_case_insensitive(api_client, db_session):
    """AC1: keyword search is case-insensitive."""
    _seed_case(db_session, sharpened="GROWTH through referrals")
    r = api_client.get("/api/cases?q=growth")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 1


def test_q_matches_plan_mechanism(api_client, db_session):
    """AC1: ?q matches keyword in plan mechanism."""
    _seed_case(db_session, sharpened="Unrelated sharpened",
               mechanisms=["viral loop drives acquisition"])
    _seed_case(db_session, sharpened="Another case")
    r = api_client.get("/api/cases?q=viral")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1


def test_q_no_match_returns_empty(api_client, db_session):
    """AC1/AC7: ?q with no matching case returns 200 with empty array."""
    _seed_case(db_session, sharpened="Pricing study")
    r = api_client.get("/api/cases?q=zzznomatch")
    assert r.status_code == 200
    assert r.json()["cases"] == []


def test_q_matches_sharpened_or_mechanism(api_client, db_session):
    """AC1: ?q is OR across sharpened and mechanisms — both cases returned."""
    _seed_case(db_session, sharpened="retention is key")
    _seed_case(db_session, sharpened="unrelated", mechanisms=["retention loop mechanism"])
    r = api_client.get("/api/cases?q=retention")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 2


# ---------------------------------------------------------------------------
# AC2: ?stage filter + invalid stage → 400
# ---------------------------------------------------------------------------

def test_stage_filter_returns_matching(api_client, db_session):
    """AC2: ?stage=gather returns only cases at gather stage."""
    _seed_case(db_session, stage="gather")
    _seed_case(db_session, stage="sharpened")
    r = api_client.get("/api/cases?stage=gather")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1


def test_stage_filter_all_valid_stages(api_client, db_session):
    """AC2: Each valid stage enum value filters correctly."""
    valid_stages = ["sharpened", "bake_off", "gather", "weigh", "probe", "verdict"]
    for stage in valid_stages:
        _seed_case(db_session, stage=stage)

    for stage in valid_stages:
        r = api_client.get(f"/api/cases?stage={stage}")
        assert r.status_code == 200, f"stage={stage} should return 200"
        cases = r.json()["cases"]
        assert len(cases) == 1, f"stage={stage} should return exactly 1 case"


def test_stage_invalid_returns_400(api_client, db_session):
    """AC2: ?stage=invalid_stage returns 400 with descriptive error."""
    r = api_client.get("/api/cases?stage=invalid_stage")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "stage" in detail.lower() or any(
        s in detail for s in ["sharpened", "bake_off", "gather"]
    ), "400 error must mention valid stage values"


def test_stage_empty_result_200(api_client, db_session):
    """AC2/AC7: ?stage=verdict with no verdict-stage cases returns 200 empty array."""
    _seed_case(db_session, stage="sharpened")
    r = api_client.get("/api/cases?stage=verdict")
    assert r.status_code == 200
    assert r.json()["cases"] == []


# ---------------------------------------------------------------------------
# AC3: ?verdict=confirmed|killed|inconclusive
# ---------------------------------------------------------------------------

def test_verdict_confirmed_filter(api_client, db_session):
    """AC3: ?verdict=confirmed returns only confirmed cases."""
    _seed_case(db_session, verdict_outcome="confirmed")
    _seed_case(db_session, verdict_outcome="killed")
    _seed_case(db_session)  # no verdict
    r = api_client.get("/api/cases?verdict=confirmed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "confirmed"


def test_verdict_killed_filter(api_client, db_session):
    """AC3: ?verdict=killed returns only killed cases."""
    _seed_case(db_session, verdict_outcome="confirmed")
    _seed_case(db_session, verdict_outcome="killed")
    r = api_client.get("/api/cases?verdict=killed")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "killed"


def test_verdict_inconclusive_filter(api_client, db_session):
    """AC3: ?verdict=inconclusive returns only inconclusive cases."""
    _seed_case(db_session, verdict_outcome="inconclusive")
    _seed_case(db_session, verdict_outcome="confirmed")
    r = api_client.get("/api/cases?verdict=inconclusive")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "inconclusive"


# ---------------------------------------------------------------------------
# AC4: ?verdict=open returns cases with no logged verdict
# ---------------------------------------------------------------------------

def test_verdict_open_filter(api_client, db_session):
    """AC4: ?verdict=open returns only cases with no verdict logged."""
    _seed_case(db_session)  # no verdict (open)
    _seed_case(db_session)  # no verdict (open)
    _seed_case(db_session, verdict_outcome="confirmed")  # has verdict (closed)
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 2
    for c in cases:
        assert c["verdict_log"] is None


def test_verdict_open_empty_result(api_client, db_session):
    """AC4/AC7: ?verdict=open with all cases having verdicts returns 200 empty array."""
    _seed_case(db_session, verdict_outcome="confirmed")
    r = api_client.get("/api/cases?verdict=open")
    assert r.status_code == 200
    assert r.json()["cases"] == []


# ---------------------------------------------------------------------------
# AC5: Params optional; omitting applies no filter
# ---------------------------------------------------------------------------

def test_no_params_returns_all(api_client, db_session):
    """AC5/AC8: No params returns all cases unchanged."""
    _seed_case(db_session, stage="sharpened")
    _seed_case(db_session, stage="gather", verdict_outcome="confirmed")
    r = api_client.get("/api/cases")
    assert r.status_code == 200
    assert len(r.json()["cases"]) == 2


# ---------------------------------------------------------------------------
# AC6: All three params composable (AND logic)
# ---------------------------------------------------------------------------

def test_q_and_stage_composable(api_client, db_session):
    """AC6: ?q and ?stage combined apply AND logic."""
    _seed_case(db_session, sharpened="pricing retention", stage="gather")
    _seed_case(db_session, sharpened="pricing conversion", stage="sharpened")
    _seed_case(db_session, sharpened="unrelated", stage="gather")
    r = api_client.get("/api/cases?q=pricing&stage=gather")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert "pricing" in cases[0]["title"].lower()


def test_q_and_verdict_composable(api_client, db_session):
    """AC6: ?q and ?verdict=open combined apply AND logic."""
    _seed_case(db_session, sharpened="growth hypothesis")  # open + matches q
    _seed_case(db_session, sharpened="growth plan", verdict_outcome="confirmed")  # not open
    _seed_case(db_session, sharpened="churn analysis")  # open but no q match
    r = api_client.get("/api/cases?q=growth&verdict=open")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert "growth" in cases[0]["title"].lower()


def test_all_three_params_composable(api_client, db_session):
    """AC6: ?q + ?stage + ?verdict=inconclusive all applied simultaneously (AND)."""
    # Matches all three
    _seed_case(db_session, sharpened="retention mechanism", stage="probe",
               verdict_outcome="inconclusive")
    # Matches q and stage but not verdict
    _seed_case(db_session, sharpened="retention factor", stage="probe")
    # Matches q and verdict but not stage
    _seed_case(db_session, sharpened="retention signal", stage="gather",
               verdict_outcome="inconclusive")
    r = api_client.get("/api/cases?q=retention&stage=probe&verdict=inconclusive")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1


# ---------------------------------------------------------------------------
# AC7: Empty result set → 200 OK with []
# ---------------------------------------------------------------------------

def test_empty_result_is_200_not_404(api_client, db_session):
    """AC7: No matching cases returns 200 with empty array, not 404."""
    _seed_case(db_session, sharpened="pricing")
    r = api_client.get("/api/cases?q=zzznomatch")
    assert r.status_code == 200
    data = r.json()
    assert "cases" in data
    assert data["cases"] == []


# ---------------------------------------------------------------------------
# AC8: Existing behaviour of GET /api/cases with no params is unchanged
# ---------------------------------------------------------------------------

def test_no_params_shape_unchanged(api_client, db_session):
    """AC8: Without params, response shape is identical to pre-existing behaviour."""
    _seed_case(db_session, sharpened="some problem", stage="sharpened")
    r = api_client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    assert "cases" in data
    case = data["cases"][0]
    for key in ("id", "title", "stage", "verdict", "verdict_log", "plans"):
        assert key in case, f"Key '{key}' missing from response — existing behaviour broken"
