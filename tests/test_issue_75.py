"""Tests for issue #75: Standardize stage field type in PATCH /cases response.

AC coverage:
  AC1 – PATCH /cases/{id} response returns stage as a string (e.g. "verdict"),
         not a numeric integer from _STAGE_ORDER.
  AC2 – stage string in PATCH response matches stage string in GET /cases/{id}.
  AC3 – No other fields (id, sharpened, not_investigating) change type or value.
  AC4 – Existing tests assert stage is a string, not an integer.
  AC5 – _STAGE_ORDER is removed from PATCH response serialization path.
"""
import json
import uuid
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

_VALID_STAGES = ["sharpened", "bake_off", "gather", "weigh", "probe"]


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


def _create_case(db, stage="sharpened", sharpened="A test statement",
                 not_investigating=None):
    from datetime import datetime, timezone
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened=sharpened,
        not_investigating=json.dumps(not_investigating or ["item A"]),
        stage=stage,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


# ---------------------------------------------------------------------------
# AC1: PATCH response returns stage as a string, not an integer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", _VALID_STAGES)
def test_patch_returns_stage_as_string(api_client, db_session, stage):
    """AC1: PATCH /cases/{id} response body must have stage as a string enum value."""
    case = _create_case(db_session, stage=stage)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated statement"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["stage"], str), (
        f"stage must be a string, got {type(data['stage']).__name__}: {data['stage']!r}"
    )
    assert data["stage"] == stage, (
        f"stage must equal the enum value {stage!r}, got {data['stage']!r}"
    )


def test_patch_stage_not_integer(api_client, db_session):
    """AC1: PATCH response must NOT return stage as an integer."""
    case = _create_case(db_session, stage="gather")
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert not isinstance(data["stage"], int), (
        f"stage must not be an int; got {data['stage']!r}"
    )


# ---------------------------------------------------------------------------
# AC2: PATCH stage matches GET /cases/{id} stage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", _VALID_STAGES)
def test_patch_stage_matches_get_stage(api_client, db_session, stage):
    """AC2: stage in PATCH response matches stage returned by GET /cases/{id}."""
    case = _create_case(db_session, stage=stage)

    patch_resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Some update"},
    )
    assert patch_resp.status_code == 200
    patch_stage = patch_resp.json()["stage"]

    get_resp = api_client.get(f"/api/cases/{case.id}")
    assert get_resp.status_code == 200
    get_stage = get_resp.json()["stage"]

    assert patch_stage == get_stage, (
        f"PATCH stage {patch_stage!r} must match GET stage {get_stage!r}"
    )
    assert isinstance(patch_stage, str), "PATCH stage must be a string"
    assert isinstance(get_stage, str), "GET stage must be a string"


# ---------------------------------------------------------------------------
# AC3: No other PATCH fields change type or value
# ---------------------------------------------------------------------------

def test_patch_other_fields_unchanged(api_client, db_session):
    """AC3: Only stage type changes — id, sharpened, not_investigating stay correct."""
    case = _create_case(
        db_session,
        stage="bake_off",
        sharpened="Original",
        not_investigating=["skip X", "skip Y"],
    )
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert isinstance(data["id"], str), "id must be a string"
    assert data["id"] == case.id
    assert isinstance(data["sharpened"], str), "sharpened must be a string"
    assert data["sharpened"] == "Updated"
    assert isinstance(data["not_investigating"], list), "not_investigating must be a list"
    assert data["not_investigating"] == ["skip X", "skip Y"]


# ---------------------------------------------------------------------------
# AC4: stage is a string value (enum key), not an integer
# ---------------------------------------------------------------------------

def test_patch_stage_is_enum_key_not_index(api_client, db_session):
    """AC4: PATCH stage value must be the enum key (e.g. 'probe'), not its list index (4)."""
    case = _create_case(db_session, stage="probe")
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Probe stage update"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "probe", (
        f"Expected 'probe', got {data['stage']!r} — must not be numeric index 4"
    )


def test_get_case_stage_is_string(api_client, db_session):
    """AC4 / AC2: GET /cases/{id} also returns stage as a string."""
    case = _create_case(db_session, stage="weigh")
    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["stage"], str), (
        f"GET /cases/{{id}} stage must be a string, got {type(data['stage']).__name__}"
    )
    assert data["stage"] == "weigh"


# ---------------------------------------------------------------------------
# AC5: _STAGE_ORDER not used in PATCH response serialization
# ---------------------------------------------------------------------------

def test_patch_stage_survives_all_valid_enum_values(api_client, db_session):
    """AC5: Every valid stage string is round-tripped correctly through PATCH."""
    for stage in _VALID_STAGES:
        case = _create_case(db_session, stage=stage)
        resp = api_client.patch(
            f"/api/cases/{case.id}",
            json={"sharpened": f"Update at {stage}"},
        )
        assert resp.status_code == 200, f"PATCH failed for stage={stage!r}"
        assert resp.json()["stage"] == stage, (
            f"Expected stage {stage!r}, got {resp.json()['stage']!r}"
        )
