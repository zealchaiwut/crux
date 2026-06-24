"""Tests for issue #92: Make Weigh stage optional — skip context input.

AC coverage:
  AC1 — POST /api/cases/{id}/rerank accepts context: null without 4xx
  AC1 — POST /api/cases/{id}/rerank accepts context: "" without 4xx
  AC1 — POST /api/cases/{id}/rerank accepts missing context field without 4xx
  AC2 — weigh.py rerank_plans handles context=None gracefully
  AC3 — weigh_context column remains nullable in data model
  AC4 — WeighPanel renders "Skip — weigh on sources only" button (JS)
  AC5 — Skip path fires rerank with context: null (JS) and advances case to weigh stage (API)
  AC6 — Primary submit flow (with context) unchanged
  AC7 — Both paths produce a valid ranked result and move case state to weigh
"""
import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _read_combined_js():
    return "".join((JS_DIR / f).read_text() for f in sorted(JS_DIR.iterdir()) if f.suffix == ".js")


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


def _seed_case_with_plans(session, stage="gather"):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my energy low all day?",
        sharpened="Energy is consistently low despite adequate sleep.",
        not_investigating=json.dumps([]),
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Iron Deficiency", mechanism="Low ferritin impairs oxygen transport.",
            prior="0.50", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Sleep Quality", mechanism="Poor sleep architecture prevents recovery.",
            prior="0.30", current_rank=2,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="C",
            name="Thyroid Dysfunction", mechanism="Low T3/T4 slows metabolism.",
            prior="0.20", current_rank=3,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_RERANK_RESULT = [
    {"label": "B", "rank": 1, "standing": "ruled-in"},
    {"label": "A", "rank": 2, "standing": None},
    {"label": "C", "rank": 3, "standing": "ruled-out"},
]


# ---------------------------------------------------------------------------
# AC1: null / empty / missing context field all accepted (no 4xx)
# ---------------------------------------------------------------------------

def test_rerank_accepts_null_context(api_client, db_session):
    """AC1: POST /api/cases/{id}/rerank accepts context: null without 4xx."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200, f"Expected 200 for null context; got {r.status_code}: {r.text}"


def test_rerank_accepts_empty_string_context(api_client, db_session):
    """AC1: POST /api/cases/{id}/rerank accepts context: "" without 4xx."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ""})
    assert r.status_code == 200, f"Expected 200 for empty context; got {r.status_code}: {r.text}"


def test_rerank_accepts_missing_context_field(api_client, db_session):
    """AC1: POST /api/cases/{id}/rerank accepts missing context field without 4xx."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={})
    assert r.status_code == 200, f"Expected 200 for missing context field; got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# AC2: weigh.py rerank_plans handles None/empty context gracefully
# ---------------------------------------------------------------------------

def test_weigh_rerank_plans_signature_accepts_none():
    """AC2: rerank_plans must accept context=None (parameter allows None)."""
    import inspect
    from app.weigh import rerank_plans
    sig = inspect.signature(rerank_plans)
    param = sig.parameters.get("context")
    assert param is not None, "rerank_plans must have a 'context' parameter"
    annotation = str(param.annotation)
    default = param.default
    assert (
        "None" in annotation or
        default is None or
        default is inspect.Parameter.empty
    ), f"context parameter should allow None; annotation={annotation}, default={default}"


def test_weigh_rerank_plans_none_context_does_not_crash():
    """AC2: rerank_plans with context=None builds a valid prompt and calls Claude."""
    from app.weigh import rerank_plans
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
        {"label": "C", "name": "Plan C", "mechanism": "Mech C"},
    ]
    mock_response = (
        '[{"label":"A","rank":1,"standing":null},'
        '{"label":"B","rank":2,"standing":null},'
        '{"label":"C","rank":3,"standing":null}]'
    )
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=mock_response):
        result = asyncio.run(rerank_plans(
            sharpened="Why is my energy low?",
            plans=plans,
            context=None,
        ))
    assert len(result) == 3, "rerank_plans with None context must return all plans"


def test_weigh_rerank_plans_empty_string_context_does_not_crash():
    """AC2: rerank_plans with context="" builds a valid prompt and calls Claude."""
    from app.weigh import rerank_plans
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
        {"label": "C", "name": "Plan C", "mechanism": "Mech C"},
    ]
    mock_response = (
        '[{"label":"A","rank":1,"standing":null},'
        '{"label":"B","rank":2,"standing":null},'
        '{"label":"C","rank":3,"standing":null}]'
    )
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=mock_response):
        result = asyncio.run(rerank_plans(
            sharpened="Why is my energy low?",
            plans=plans,
            context="",
        ))
    assert len(result) == 3, "rerank_plans with empty string context must return all plans"


# ---------------------------------------------------------------------------
# AC3: weigh_context column remains nullable
# ---------------------------------------------------------------------------

def test_weigh_context_column_is_nullable():
    """AC3: weigh_context column on Case must be nullable (no migration required)."""
    from sqlalchemy import inspect as sa_inspect
    from app.models import Case
    mapper = sa_inspect(Case)
    col = mapper.columns.get("weigh_context")
    assert col is not None, "Case model must have weigh_context column"
    assert col.nullable, "weigh_context column must be nullable"


def test_skip_rerank_stores_null_weigh_context(api_client, db_session):
    """AC3: After skip (null context) rerank, weigh_context is NULL in the database."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.weigh_context is None, \
        f"weigh_context must be NULL after skip; got: {updated_case.weigh_context!r}"


# ---------------------------------------------------------------------------
# AC4: WeighPanel "Skip" button present in JS
# ---------------------------------------------------------------------------

def test_weighpanel_skip_button_exists_in_js():
    """AC4: WeighPanel must render a 'Skip — weigh on sources only' secondary button."""
    combined = _read_combined_js()
    assert "Skip" in combined and "weigh on sources only" in combined, \
        "WeighPanel must include a 'Skip — weigh on sources only' button"


# ---------------------------------------------------------------------------
# AC5: Skip fires rerank with context: null (JS); advances case to weigh stage (API)
# ---------------------------------------------------------------------------

def test_skip_fires_null_context_in_js():
    """AC5: Skip handler must fire rerank request with context: null."""
    combined = _read_combined_js()
    assert "context: null" in combined or "context:null" in combined, \
        "Skip button handler must fire rerank with context: null"


def test_skip_rerank_advances_stage_to_weigh(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank with null context advances case stage to 'weigh'."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    assert c.stage == "gather", "Precondition: case starts in gather stage"

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.stage == "weigh", \
        f"Case must advance to 'weigh' stage after skip rerank; got: {updated_case.stage!r}"


# ---------------------------------------------------------------------------
# AC6: Primary submit flow (with context) unchanged
# ---------------------------------------------------------------------------

def test_primary_submit_with_context_persists_context(api_client, db_session):
    """AC6: Primary submit (with context) still persists weigh_context on the case."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    ctx = "Ferritin 12 ng/mL, TSH 2.3, sleep 7h but multiple night wakings."
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ctx})
    assert r.status_code == 200

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.weigh_context == ctx, \
        f"weigh_context must persist provided context; got: {updated_case.weigh_context!r}"


def test_primary_submit_button_requires_non_empty_context_in_js():
    """AC6: Primary 'Re-rank for me' button is disabled when context is empty."""
    combined = _read_combined_js()
    assert "!context.trim()" in combined, \
        "Primary submit button must still be disabled when context is empty"


# ---------------------------------------------------------------------------
# AC7: Both paths produce valid ranked result and move case state to weigh
# ---------------------------------------------------------------------------

def test_skip_path_returns_valid_ranked_result(api_client, db_session):
    """AC7: Skip path (null context) returns valid ranked plans and moves case to weigh."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "Response must include 'plans'"
    assert len(data["plans"]) == 3, "All 3 plans must be returned"
    ranks = sorted(p["current_rank"] for p in data["plans"])
    assert ranks == [1, 2, 3], f"Plans must have unique ranks 1-3; got {ranks}"

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.stage == "weigh", "Case must be in weigh stage"


def test_primary_path_returns_valid_ranked_result(api_client, db_session):
    """AC7: Primary path (with context) returns valid ranked plans and moves case to weigh."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "real context data"})
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "Response must include 'plans'"
    assert len(data["plans"]) == 3, "All 3 plans must be returned"
    ranks = sorted(p["current_rank"] for p in data["plans"])
    assert ranks == [1, 2, 3], f"Plans must have unique ranks 1-3; got {ranks}"

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.stage == "weigh", "Case must be in weigh stage"
