"""Tests for issue #66: PATCH /api/cases/{id} — edit sharpened statement and not_investigating.

AC coverage:
  AC3 – PATCH /api/cases/{id} accepts { sharpened?, not_investigating? }; partial updates allowed
  AC4 – Successful save updates values without triggering a stage change
  AC5 – Plans, sources, probe, verdict unchanged after edit
  AC6 – Verdict-stage case returns 403 or 409
  AC7a – Sharpened must be non-empty if provided (422)
  AC7b – not_investigating items must be non-empty strings (422)
"""
import json
import uuid
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers / fixtures
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
    cookie = create_session_cookie(AUTH_SECRET)
    client = TestClient(app)
    client.cookies.set("session", cookie)
    yield client
    app.dependency_overrides.pop(get_db, None)


def _create_case(db, stage="sharpened", sharpened="Original statement",
                 not_investigating=None):
    from datetime import datetime, timezone
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened=sharpened,
        not_investigating=json.dumps(not_investigating or ["item A", "item B"]),
        stage=stage,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _create_verdict_case(db):
    from datetime import datetime, timezone
    from app import models
    case = _create_case(db, stage="verdict", sharpened="Closed case statement")
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="some mechanism",
        prior="0.6",
        current_rank=1,
    )
    db.add(plan)
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="measurement",
        target_metric="metric",
        status="confirmed",
    )
    db.add(probe)
    db.commit()
    db.refresh(probe)
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="done",
        decided_at=datetime.now(tz=timezone.utc),
    )
    db.add(verdict)
    db.commit()
    return case


# ---------------------------------------------------------------------------
# AC3: PATCH endpoint exists and accepts partial updates
# ---------------------------------------------------------------------------

def test_patch_sharpened_only(api_client, db_session):
    """AC3: PATCH with only sharpened updates sharpened, leaves not_investigating alone."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated statement"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sharpened"] == "Updated statement"
    # not_investigating must be unchanged
    assert data["not_investigating"] == ["item A", "item B"]


def test_patch_not_investigating_only(api_client, db_session):
    """AC3: PATCH with only not_investigating updates list, leaves sharpened alone."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"not_investigating": ["new item"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["not_investigating"] == ["new item"]
    assert data["sharpened"] == "Original statement"


def test_patch_both_fields(api_client, db_session):
    """AC3: PATCH with both fields updates both."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "New sharpened", "not_investigating": ["X", "Y"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sharpened"] == "New sharpened"
    assert data["not_investigating"] == ["X", "Y"]


def test_patch_nonexistent_case(api_client, db_session):
    """PATCH on a non-existent case returns 404."""
    resp = api_client.patch(
        f"/api/cases/{uuid.uuid4()}",
        json={"sharpened": "doesn't matter"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC4: Stage not changed by a successful edit
# ---------------------------------------------------------------------------

def test_patch_does_not_change_stage(api_client, db_session):
    """AC4: Stage remains unchanged after PATCH."""
    case = _create_case(db_session, stage="bake_off")
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated"},
    )
    assert resp.status_code == 200
    from app import models
    db_case = db_session.query(models.Case).filter_by(id=case.id).first()
    assert db_case.stage == "bake_off"


# ---------------------------------------------------------------------------
# AC5: Plans / probe / verdict unchanged after edit
# ---------------------------------------------------------------------------

def test_patch_leaves_plans_intact(api_client, db_session):
    """AC5: Plans are not removed or modified by PATCH."""
    from app import models
    case = _create_case(db_session)
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="mechanism text",
        prior="0.7",
        current_rank=1,
    )
    db_session.add(plan)
    db_session.commit()

    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated"},
    )
    assert resp.status_code == 200
    plans_in_db = db_session.query(models.Plan).filter_by(case_id=case.id).all()
    assert len(plans_in_db) == 1
    assert plans_in_db[0].mechanism == "mechanism text"


# ---------------------------------------------------------------------------
# AC6: Verdict-stage cases are immutable (403 or 409)
# ---------------------------------------------------------------------------

def test_patch_verdict_stage_forbidden(api_client, db_session):
    """AC6: PATCH on verdict-stage case returns 403 or 409."""
    case = _create_verdict_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "trying to edit"},
    )
    assert resp.status_code in (403, 409)


# ---------------------------------------------------------------------------
# AC7a: sharpened must be non-empty if provided
# ---------------------------------------------------------------------------

def test_patch_empty_sharpened_rejected(api_client, db_session):
    """AC7a: Empty sharpened string returns 422."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": ""},
    )
    assert resp.status_code == 422


def test_patch_whitespace_sharpened_rejected(api_client, db_session):
    """AC7a: Whitespace-only sharpened string returns 422."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "   "},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC7b: not_investigating items must be non-empty strings
# ---------------------------------------------------------------------------

def test_patch_empty_not_investigating_item_rejected(api_client, db_session):
    """AC7b: not_investigating list with an empty string item returns 422."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"not_investigating": ["valid item", ""]},
    )
    assert resp.status_code == 422


def test_patch_whitespace_not_investigating_item_rejected(api_client, db_session):
    """AC7b: not_investigating list with whitespace-only item returns 422."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"not_investigating": ["  "]},
    )
    assert resp.status_code == 422


def test_patch_empty_not_investigating_list_allowed(api_client, db_session):
    """AC7b: Empty not_investigating list (clearing all) is valid."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"not_investigating": []},
    )
    assert resp.status_code == 200
    assert resp.json()["not_investigating"] == []
