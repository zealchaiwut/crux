"""Tests for issue #201: Enforce the verdict gate server-side.

AC coverage:
  AC1 – The case detail response omits (returns null) the plans field until a verdict exists.
  AC2 – A direct API call pre-verdict confirms plans is absent/null.
  AC3 – The same API call post-verdict confirms plans is present and non-empty.
  AC4 – SCHEMA.md documents the verdict gate as a server guarantee.
"""
import json
import os
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


def _seed_case_with_probe(session, with_verdict=False):
    """Seed a Case at probe stage with a plan and a probe; optionally add a verdict."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Should we launch feature X?",
        sharpened="Will launching feature X increase retention by 10%?",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Feature X launch",
        mechanism="Feature X addresses churn by targeting the friction point.",
        prior="0.7",
        current_rank=1,
    )
    session.add(plan)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="30-day retention rate",
        status="designed",
    )
    session.add(probe)
    session.flush()

    if with_verdict:
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Feature X confirmed to increase retention by 12%.",
        )
        session.add(verdict)
        c.stage = "verdict"

    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1 + AC2: Pre-verdict – plans field must be null (gated server-side)
# ---------------------------------------------------------------------------

def test_case_detail_plans_absent_pre_verdict(api_client, db_session):
    """AC1/AC2: GET /api/cases/{id} returns plans=null when no verdict has been logged.

    A case with a probe but no verdict must not expose action-plan data.
    This enforces the gate at the API layer so machine callers cannot bypass it.
    """
    c = _seed_case_with_probe(db_session, with_verdict=False)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["plans"] is None, (
        "plans must be null pre-verdict: the server must not expose action plan data "
        "until a probe verdict is logged (AC1/AC2)"
    )


# ---------------------------------------------------------------------------
# AC3: Post-verdict – plans field must be present and non-empty
# ---------------------------------------------------------------------------

def test_case_detail_plans_present_post_verdict(api_client, db_session):
    """AC3: GET /api/cases/{id} returns the full plans list after a verdict is logged."""
    c = _seed_case_with_probe(db_session, with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["plans"] is not None, (
        "plans must be present post-verdict: once a verdict is logged, action plan "
        "data must be accessible to callers (AC3)"
    )
    assert isinstance(data["plans"], list) and len(data["plans"]) > 0, (
        "plans must be a non-empty list post-verdict (AC3)"
    )


# ---------------------------------------------------------------------------
# AC3 companion: pre-probe stages (no probe yet) – plans are accessible
# ---------------------------------------------------------------------------

def test_case_detail_plans_present_when_no_probe(api_client, db_session):
    """AC3 companion: Cases with no probe yet (gather/weigh) still return plans.

    The verdict gate only locks plans when a probe exists but no verdict has
    been logged.  Early-stage cases (gather, weigh) are unaffected.
    """
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened test problem.",
        not_investigating=json.dumps([]),
        stage="gather",
    )
    db_session.add(c)
    db_session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Plan A",
        mechanism="Mechanism A",
        prior="0.6",
        current_rank=1,
    )
    db_session.add(plan)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["plans"] is not None, (
        "plans must not be gated for cases without a probe yet (gather/weigh stage)"
    )
    assert len(data["plans"]) == 1


# ---------------------------------------------------------------------------
# AC4: SCHEMA.md documents the verdict gate contract
# ---------------------------------------------------------------------------

def test_schema_md_documents_verdict_gate():
    """AC4: SCHEMA.md must document the server-side verdict gate for the plans field."""
    from pathlib import Path

    schema = (Path(__file__).parent.parent / "SCHEMA.md").read_text()
    assert "verdict gate" in schema.lower(), (
        "SCHEMA.md must describe the 'verdict gate' so future clients know it is a "
        "server guarantee, not a UI convention (AC4)"
    )
    assert "plans" in schema, (
        "SCHEMA.md verdict gate section must mention the 'plans' field (AC4)"
    )
