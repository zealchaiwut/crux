"""Tests for issue #132: Persist plan rationale from Weigh rerank response.

AC coverage:
  AC1 – Plan model has a nullable 'rationale' Text column
  AC2 – Alembic migration file exists for adding the rationale column
  AC3 – POST /api/cases/{id}/rerank writes rationale from Weigh into plan.rationale;
         if Weigh returns no rationale the field is stored as NULL
  AC4 – GET /api/cases/{id} response includes 'rationale' on each plan object (string or null)
  AC5 – No existing tests are broken; new tests cover rerank handler storing rationale
         and GET response including it
"""
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# Helpers
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


def _seed_case_with_plans(session, stage="weigh"):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my output quality declining?",
        sharpened="Output quality has declined 20% over the past month.",
        not_investigating=json.dumps([]),
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Process Drift", mechanism="Incremental deviations compound over time.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Tool Degradation", mechanism="Key tools have worn beyond tolerances.",
            prior="0.30", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_RERANK_WITH_RATIONALE = [
    {
        "label": "A",
        "rank": 1,
        "standing": "ruled-in",
        "rationale": "Process drift is supported by the audit log showing 12 unchecked deviations.",
    },
    {
        "label": "B",
        "rank": 2,
        "standing": None,
        "rationale": "Tool degradation is plausible but calibration records show only minor wear.",
    },
]

_RERANK_WITHOUT_RATIONALE = [
    {"label": "A", "rank": 1, "standing": "ruled-in"},
    {"label": "B", "rank": 2, "standing": None},
]


# ---------------------------------------------------------------------------
# AC1: Plan model has a nullable rationale Text column
# ---------------------------------------------------------------------------

def test_plan_model_has_rationale_column():
    """AC1: Plan model must have a nullable 'rationale' Text column."""
    from app import models
    assert hasattr(models.Plan, "rationale"), "Plan model must have a 'rationale' attribute"
    col = models.Plan.__table__.columns.get("rationale")
    assert col is not None, "Plan table must have a 'rationale' column"
    assert col.nullable, "Plan.rationale column must be nullable"


# ---------------------------------------------------------------------------
# AC2: Alembic migration file exists
# ---------------------------------------------------------------------------

def test_alembic_migration_for_rationale_exists():
    """AC2: An Alembic migration file that adds the 'rationale' column must exist."""
    import pathlib
    versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    found = any(
        "rationale" in f.read_text() and "plan" in f.read_text()
        for f in migration_files
    )
    assert found, (
        "No Alembic migration found that adds 'rationale' to the plan table. "
        "Create a migration with op.add_column('plan', sa.Column('rationale', sa.Text(), nullable=True))."
    )


# ---------------------------------------------------------------------------
# AC3: POST /api/cases/{id}/rerank writes rationale into plan.rationale
# ---------------------------------------------------------------------------

def test_rerank_persists_rationale(api_client, db_session):
    """AC3: POST /api/cases/{id}/rerank stores Weigh-returned rationale on plan.rationale."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_RERANK_WITH_RATIONALE):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "some context"})

    assert r.status_code == 200, r.text

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rationale_by_label = {p.label: p.rationale for p in plans}

    assert rationale_by_label["A"] == _RERANK_WITH_RATIONALE[0]["rationale"], (
        f"Plan A rationale not persisted; got: {rationale_by_label['A']!r}"
    )
    assert rationale_by_label["B"] == _RERANK_WITH_RATIONALE[1]["rationale"], (
        f"Plan B rationale not persisted; got: {rationale_by_label['B']!r}"
    )


def test_rerank_stores_null_rationale_when_weigh_returns_none(api_client, db_session):
    """AC3: If Weigh returns no rationale field, plan.rationale is stored as NULL."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_RERANK_WITHOUT_RATIONALE):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "some context"})

    assert r.status_code == 200, r.text

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    for p in plans:
        assert p.rationale is None, (
            f"Plan {p.label}.rationale must be NULL when Weigh returns no rationale; "
            f"got: {p.rationale!r}"
        )


def test_rerank_second_call_overwrites_rationale(api_client, db_session):
    """AC3: A subsequent rerank overwrites the previously stored rationale."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_RERANK_WITH_RATIONALE):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "first context"})

    new_result = [
        {
            "label": "A",
            "rank": 2,
            "standing": None,
            "rationale": "Updated: new data points to tool wear as primary driver.",
        },
        {
            "label": "B",
            "rank": 1,
            "standing": "ruled-in",
            "rationale": "Updated: calibration log confirms tolerance breach.",
        },
    ]
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=new_result):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "second context"})

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rationale_by_label = {p.label: p.rationale for p in plans}
    assert "Updated:" in (rationale_by_label["A"] or ""), (
        f"Plan A rationale must reflect the second rerank; got: {rationale_by_label['A']!r}"
    )
    assert "Updated:" in (rationale_by_label["B"] or ""), (
        f"Plan B rationale must reflect the second rerank; got: {rationale_by_label['B']!r}"
    )


# ---------------------------------------------------------------------------
# AC4: GET /api/cases/{id} includes rationale on each plan object
# ---------------------------------------------------------------------------

def test_get_case_includes_rationale_field(api_client, db_session):
    """AC4: GET /api/cases/{id} response includes 'rationale' on every plan object."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, r.text
    data = r.json()

    assert "plans" in data, "Response must include 'plans'"
    for plan in data["plans"]:
        assert "rationale" in plan, (
            f"Plan object missing 'rationale' field: {plan}"
        )


def test_get_case_rationale_null_before_rerank(api_client, db_session):
    """AC4: GET /api/cases/{id} returns null rationale for plans that have never been reranked."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, r.text
    data = r.json()

    for plan in data["plans"]:
        assert plan["rationale"] is None, (
            f"Plan {plan.get('label')} rationale must be null before first rerank; "
            f"got: {plan['rationale']!r}"
        )


def test_get_case_rationale_matches_stored_value(api_client, db_session):
    """AC4: GET /api/cases/{id} returns the exact rationale stored by the last rerank."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_RERANK_WITH_RATIONALE):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "some context"})

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, r.text
    data = r.json()

    rationale_by_label = {p["label"]: p["rationale"] for p in data["plans"]}
    assert rationale_by_label["A"] == _RERANK_WITH_RATIONALE[0]["rationale"], (
        f"GET rationale for Plan A does not match stored value; "
        f"got: {rationale_by_label['A']!r}"
    )
    assert rationale_by_label["B"] == _RERANK_WITH_RATIONALE[1]["rationale"], (
        f"GET rationale for Plan B does not match stored value; "
        f"got: {rationale_by_label['B']!r}"
    )
