"""Tests for issue #37: Validate ranked plan presence before spec generation.

Follow-up to #33 — the existing check blocks zero plans, but plans with
current_rank=None still slip through and degrade spec quality.

AC1: Plans exist but ALL have current_rank=None → HTTP 422.
AC2: 422 detail message references "ranked" plans.
AC3: At least one plan with current_rank set → spec generation proceeds (HTTP 200).
AC4: No Claude API call when no ranked plans exist.
AC5: Mixed ranked/unranked plans (≥1 ranked) → proceeds normally.
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


def _seed_case_with_probe(session):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is NPS low?",
        sharpened="NPS declined 10 points.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()
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
    session.flush()
    return c


def _add_plans(session, case_id, ranks):
    """Add plans with given ranks (None means unranked)."""
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


_MOCK_SPEC = "# Spec\n\n**Target:** NPS\n\n## AC\n- [ ] Do thing\n"


# ---------------------------------------------------------------------------
# AC1: all null ranks → 422
# ---------------------------------------------------------------------------

def test_ac1_all_null_ranks_returns_422(api_client, db_session):
    """AC1: Plans present but all current_rank=None → HTTP 422."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [None, None])

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422, (
        f"Expected 422 when all plans unranked, got {resp.status_code}: {resp.text}"
    )


def test_ac1_single_null_rank_returns_422(api_client, db_session):
    """AC1: Single plan with current_rank=None → HTTP 422."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [None])

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422, (
        f"Expected 422 for single unranked plan, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# AC2: 422 detail mentions "ranked"
# ---------------------------------------------------------------------------

def test_ac2_detail_mentions_ranked(api_client, db_session):
    """AC2: 422 body detail references 'ranked'."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [None, None])

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "ranked" in body["detail"].lower(), (
        f"detail should mention 'ranked'; got: {body['detail']!r}"
    )


# ---------------------------------------------------------------------------
# AC3: ≥1 ranked plan → 200
# ---------------------------------------------------------------------------

def test_ac3_one_ranked_plan_proceeds(api_client, db_session):
    """AC3: One plan with current_rank=1 → HTTP 200."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [1])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200, (
        f"Expected 200 with one ranked plan, got {resp.status_code}: {resp.text}"
    )


def test_ac3_multiple_ranked_plans_proceed(api_client, db_session):
    """AC3: Multiple ranked plans → HTTP 200."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [1, 2, 3])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AC4: No Claude API call when no ranked plans
# ---------------------------------------------------------------------------

def test_ac4_no_api_call_when_all_unranked(api_client, db_session):
    """AC4: generate_commander_spec NOT called when all plans have null rank."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [None, None, None])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# AC5: Mixed ranked/unranked → proceeds (the ranked ones drive the spec)
# ---------------------------------------------------------------------------

def test_ac5_mixed_ranks_proceeds(api_client, db_session):
    """AC5: At least one ranked plan among unranked plans → HTTP 200."""
    case = _seed_case_with_probe(db_session)
    _add_plans(db_session, case.id, [1, None, None])

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200, (
        f"Expected 200 with one ranked + two unranked, got {resp.status_code}: {resp.text}"
    )
    mock_gen.assert_called_once()
