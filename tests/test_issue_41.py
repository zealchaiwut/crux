"""Tests for issue #41: Validate plan presence before spec generation (follow-up).

Sprint-4 review of #26 flagged that spec generation can proceed with empty plans.
Issues #33 and #37 added guards; this test suite pins the contract so regressions
are caught immediately.

AC1: POST spec endpoint returns 422 when the case has no ranked plans.
AC2: 422 body includes a detail field indicating no ranked plans are present.
AC3: Spec generation proceeds normally when at least one ranked plan exists.
AC4: Existing tests for valid plans continue to pass unchanged.
AC5: A new test asserts spec generation on a plan-less case returns 422.
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

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


def _seed_case_and_probe(session, probe_type: str = "prototype"):
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


def _add_plans(session, case_id: str, ranks: list):
    from app import models

    labels = ["A", "B", "C", "D"]
    for i, rank in enumerate(ranks):
        p = models.Plan(
            id=str(uuid.uuid4()),
            case_id=case_id,
            label=labels[i],
            name=f"Plan {labels[i]}",
            mechanism=f"Mechanism {labels[i]}",
            current_rank=rank,
        )
        session.add(p)
    session.commit()


_MOCK_SPEC = "# Retention Probe\n\n**Target:** retention rate\n\n## AC\n- [ ] Track sessions\n"

_SPEC_URL = "/api/cases/{case_id}/probe/commander-spec"


# ---------------------------------------------------------------------------
# AC1 + AC5: plan-less case → 422
# ---------------------------------------------------------------------------


def test_ac1_ac5_no_plans_returns_422(api_client, db_session):
    """AC1 + AC5: spec generation on a case with no plans returns HTTP 422."""
    case = _seed_case_and_probe(db_session)

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422, (
        f"Expected 422 for plan-less case, got {resp.status_code}: {resp.text}"
    )


def test_ac1_unranked_plans_returns_422(api_client, db_session):
    """AC1: Plans exist but all have current_rank=None → HTTP 422."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [None, None])

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422, (
        f"Expected 422 when no ranked plans, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# AC2: 422 detail indicates no ranked plans
# ---------------------------------------------------------------------------


def test_ac2_no_plans_detail_mentions_plan(api_client, db_session):
    """AC2: 422 for plan-less case has a detail field mentioning plans."""
    case = _seed_case_and_probe(db_session)

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body, "422 response must contain a 'detail' field"
    assert isinstance(body["detail"], str), "detail must be a string"
    assert "plan" in body["detail"].lower(), (
        f"detail should mention 'plan'; got: {body['detail']!r}"
    )


def test_ac2_unranked_plans_detail_mentions_ranked(api_client, db_session):
    """AC2: 422 for unranked-plans case has a detail field mentioning 'ranked'."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [None, None])

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "ranked" in body["detail"].lower(), (
        f"detail should mention 'ranked'; got: {body['detail']!r}"
    )


# ---------------------------------------------------------------------------
# AC3: at least one ranked plan → proceeds normally
# ---------------------------------------------------------------------------


def test_ac3_one_ranked_plan_returns_200(api_client, db_session):
    """AC3: With one ranked plan spec generation proceeds and returns HTTP 200."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [1])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 200, (
        f"Expected 200 with one ranked plan, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("commander_spec") == _MOCK_SPEC


def test_ac3_multiple_ranked_plans_return_200(api_client, db_session):
    """AC3: With multiple ranked plans spec generation proceeds and returns HTTP 200."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [1, 2, 3])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 200


def test_ac3_mixed_ranked_unranked_proceeds(api_client, db_session):
    """AC3: At least one ranked plan among unranked ones → spec generation proceeds."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [1, None, None])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AC4: no API call on invalid input
# ---------------------------------------------------------------------------


def test_ac4_no_api_call_when_plan_less(api_client, db_session):
    """AC4: generate_commander_spec is NOT called when the case has no plans."""
    case = _seed_case_and_probe(db_session)

    with patch(
        "app.routers.cases.generate_commander_spec", new_callable=AsyncMock
    ) as mock_gen:
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422
    mock_gen.assert_not_called()


def test_ac4_no_api_call_when_all_unranked(api_client, db_session):
    """AC4: generate_commander_spec is NOT called when all plans are unranked."""
    case = _seed_case_and_probe(db_session)
    _add_plans(db_session, case.id, [None, None])

    with patch(
        "app.routers.cases.generate_commander_spec", new_callable=AsyncMock
    ) as mock_gen:
        resp = api_client.post(_SPEC_URL.format(case_id=case.id))

    assert resp.status_code == 422
    mock_gen.assert_not_called()
