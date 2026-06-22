"""Tests for issue #33: Validate plan presence before spec generation.

AC1: Empty plans_input → HTTP 422 with clear error message.
AC2: At least one ranked plan → spec generation proceeds normally (HTTP 200).
AC3: 422 body includes human-readable detail field.
AC4: Validation occurs before Claude prompt construction (no API call on 422).
AC5: Happy-path behaviour unchanged — no regression.
"""
import json
import os
import uuid
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_12345")


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api_client(db_session):
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case_with_probe_no_plans(session, probe_type: str = "prototype"):
    """Seed a Case with a Probe but NO plans."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is retention low?",
        sharpened="Retention dropped 15%.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type=probe_type,
        target_metric="retention rate",
        cost="~5 hours dev",
        time="3 days",
        note="Minimal retention probe.",
        status="designed",
    )
    session.add(probe)
    session.commit()
    return c


def _seed_case_with_probe_and_plans(session, plan_count: int = 3, probe_type: str = "prototype"):
    """Seed a Case with a Probe and one or more plans."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is engagement low?",
        sharpened="Engagement dropped 20%.",
        not_investigating=json.dumps(["External factors"]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    for i, label in enumerate(["A", "B", "C"][:plan_count]):
        p = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism {label}",
            prior=str(0.55 - i * 0.2),
            current_rank=i + 1,
        )
        session.add(p)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type=probe_type,
        target_metric="task completion rate",
        cost="~10 hours dev",
        time="1 week",
        note="Build a minimal tracker.",
        status="designed",
    )
    session.add(probe)
    session.commit()
    return c


def _seed_case_with_probe_null_ranks(session):
    """Seed a Case with plans that have current_rank=None."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is NPS low?",
        sharpened="NPS declined.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    for label in ["A", "B"]:
        p = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism {label}",
            prior="0.3",
            current_rank=None,
        )
        session.add(p)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="prototype",
        target_metric="NPS",
        cost="~8 hours",
        time="5 days",
        note="NPS probe.",
        status="designed",
    )
    session.add(probe)
    session.commit()
    return c


_MOCK_SPEC = """\
# Build a Minimal Tracker

**Target metric:** task completion rate

## Acceptance Criteria
- [ ] Users can log a task

## Build Context
Tests engagement with task tracking.
"""


# ---------------------------------------------------------------------------
# AC1: Empty plans → 422
# ---------------------------------------------------------------------------

def test_ac1_empty_plans_returns_422(api_client, db_session):
    """AC1: POST commander-spec with no plans returns HTTP 422."""
    case = _seed_case_with_probe_no_plans(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422, (
        f"Expected 422 when plans are absent, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# AC2: At least one ranked plan → 200 (normal flow)
# ---------------------------------------------------------------------------

def test_ac2_one_plan_proceeds_normally(api_client, db_session):
    """AC2: With one ranked plan, spec generation returns HTTP 200."""
    case = _seed_case_with_probe_and_plans(db_session, plan_count=1)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200, (
        f"Expected 200 when at least one plan present, got {resp.status_code}: {resp.text}"
    )


def test_ac2_multiple_plans_proceeds_normally(api_client, db_session):
    """AC2: With multiple ranked plans, spec generation returns HTTP 200."""
    case = _seed_case_with_probe_and_plans(db_session, plan_count=3)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AC3: 422 body has human-readable detail field
# ---------------------------------------------------------------------------

def test_ac3_422_includes_detail_field(api_client, db_session):
    """AC3: 422 response body includes a human-readable detail field."""
    case = _seed_case_with_probe_no_plans(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body, "422 response must contain a 'detail' field"
    assert isinstance(body["detail"], str), "detail must be a string"
    detail = body["detail"].lower()
    assert "plan" in detail, (
        f"detail should mention 'plan'; got: {body['detail']!r}"
    )


def test_ac3_422_detail_mentions_requirement(api_client, db_session):
    """AC3: detail field conveys that at least one plan is required."""
    case = _seed_case_with_probe_no_plans(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    body = resp.json()
    detail = body["detail"]
    assert "At least one plan is required" in detail, (
        f"detail should say 'At least one plan is required'; got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# AC4: No Claude API call when plans absent
# ---------------------------------------------------------------------------

def test_ac4_no_api_call_when_plans_absent(api_client, db_session):
    """AC4: generate_commander_spec is NOT called when plans_input is empty."""
    case = _seed_case_with_probe_no_plans(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# AC5: Happy-path regression — plans present → Claude called, spec returned
# ---------------------------------------------------------------------------

def test_ac5_happy_path_unchanged(api_client, db_session):
    """AC5: When plans exist, spec generation works exactly as before."""
    case = _seed_case_with_probe_and_plans(db_session, plan_count=3)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    mock_gen.assert_called_once()
    data = resp.json()
    assert "commander_spec" in data
    assert data["commander_spec"] == _MOCK_SPEC


def test_ac5_plans_with_null_ranks_still_proceed(api_client, db_session):
    """AC5: Plans with current_rank=None are present → proceed, ranks sorted as 99."""
    case = _seed_case_with_probe_null_ranks(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200, (
        f"Expected 200 when plans have null ranks; got {resp.status_code}: {resp.text}"
    )
    mock_gen.assert_called_once()
