"""Tests for issue #170: Gate action plan provisionally on first probe verdict.

AC coverage:
  AC1 – Action plan remains locked when zero probe verdicts have been logged
  AC2 – Action plan unlocks in provisional state when first (any) probe verdict is logged
  AC3 – Action plan transitions to final state once the long-horizon probe verdict is logged
  AC4 – Provisional action plan renders with label 'provisional · pending long-horizon'
  AC5 – Case Summary remains accessible at all states (pre-verdict, provisional, final)
  AC6 – Server-side gate enforces provisional/final logic (GET /action-plan returns 403 when locked)
  AC7 – Tests cover: (a) 0 verdicts → locked, (b) first verdict → provisional, (c) long-horizon → final
  AC8 – No regression to Case Summary availability or other probe-gated UI elements
"""
import json
import os
import uuid
from datetime import datetime, timezone

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


def _seed_case_with_three_probes(session, stage="probe"):
    """Seed a case with plans and three horizon probes (no verdicts yet)."""
    from app import models

    now = datetime.now(tz=timezone.utc)
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is performance dropping?",
        sharpened="Performance has dropped 15% over 6 weeks.",
        not_investigating=json.dumps([]),
        stage=stage,
        created_at=now,
    )
    session.add(c)
    session.flush()

    for rank, label in enumerate(["A", "B", "C"], start=1):
        plan = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism {label}",
            prior="0.33",
            current_rank=rank,
        )
        session.add(plan)

    probes = {}
    for horizon in ("short", "mid", "long"):
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric=f"{horizon} metric",
            cost="low",
            time="1 week",
            note=f"{horizon} note",
            steps=[],
            duration="1 week",
            decision_rule=f"{horizon} rule",
            status="designed",
            horizon=horizon,
            created_at=now,
        )
        session.add(probe)
        probes[horizon] = probe

    session.commit()
    return c, probes


def _log_verdict_for_probe(session, probe, outcome="confirmed"):
    """Log a verdict for a probe, updating its status."""
    from app import models
    now = datetime.now(tz=timezone.utc)
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes=f"Test verdict for {probe.horizon} probe",
        decided_at=now,
        created_at=now,
    )
    session.add(verdict)
    probe.status = outcome
    session.commit()
    return verdict


# ---------------------------------------------------------------------------
# AC1 / AC7a — 0 verdicts → locked
# ---------------------------------------------------------------------------

def test_zero_verdicts_action_plan_state_is_locked(api_client, db_session):
    """AC1/AC7a: With no probe verdicts, action_plan_state must be 'locked'."""
    case, _ = _seed_case_with_three_probes(db_session)
    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "locked"


def test_zero_verdicts_action_plan_endpoint_returns_403(api_client, db_session):
    """AC6/AC7a: GET /action-plan returns 403 when no probe has a verdict."""
    case, _ = _seed_case_with_three_probes(db_session)
    resp = api_client.get(f"/api/cases/{case.id}/action-plan")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC2 / AC7b — first verdict (any probe) → provisional
# ---------------------------------------------------------------------------

def test_first_verdict_non_long_gives_provisional_state(api_client, db_session):
    """AC2/AC7b: First verdict on a non-long probe → action_plan_state='provisional'."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "provisional"


def test_first_verdict_non_long_allows_action_plan_access(api_client, db_session):
    """AC2: GET /action-plan returns content (not 403) when state is provisional."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])

    resp = api_client.get(f"/api/cases/{case.id}/action-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "provisional"


def test_first_verdict_mid_probe_also_gives_provisional(api_client, db_session):
    """AC2: Mid-horizon first verdict also yields provisional (not just short)."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["mid"])

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    assert resp.json()["action_plan_state"] == "provisional"


# ---------------------------------------------------------------------------
# AC3 / AC7c — long-horizon verdict → final
# ---------------------------------------------------------------------------

def test_long_horizon_verdict_gives_final_state(api_client, db_session):
    """AC3/AC7c: Long-horizon probe verdict → action_plan_state='final'."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])
    _log_verdict_for_probe(db_session, probes["long"])

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "final"


def test_long_horizon_verdict_alone_gives_final_state(api_client, db_session):
    """AC3: Long-horizon verdict alone (first verdict) also gives final state."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["long"])

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    assert resp.json()["action_plan_state"] == "final"


def test_long_horizon_verdict_action_plan_endpoint_returns_final(api_client, db_session):
    """AC3: GET /action-plan returns state='final' once long-horizon verdict logged."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])
    _log_verdict_for_probe(db_session, probes["long"])

    resp = api_client.get(f"/api/cases/{case.id}/action-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "final"


# ---------------------------------------------------------------------------
# AC4 — provisional label text present in frontend code
# ---------------------------------------------------------------------------

def test_provisional_label_text_in_frontend():
    """AC4: Frontend cases.js contains the 'provisional · pending long-horizon' label text."""
    import pathlib
    js_path = pathlib.Path("app/static/js/cases.js")
    content = js_path.read_text()
    assert "provisional · pending long-horizon" in content, (
        "cases.js must render the label 'provisional · pending long-horizon' "
        "when action_plan_state is 'provisional'"
    )


# ---------------------------------------------------------------------------
# AC5 / AC8 — Case Summary accessible at all states; no regression
# ---------------------------------------------------------------------------

def test_case_summary_accessible_before_any_verdict(api_client, db_session):
    """AC5: Case Summary (POST /summary) accessible when action plan is locked."""
    from unittest.mock import AsyncMock, patch

    case, _ = _seed_case_with_three_probes(db_session)

    fake_summary = json.dumps({
        "problem_statement": "Performance drop issue",
        "option_ranking": "Plan A leads",
        "recommended_plan": "Plan A",
        "probe_plan": "Short horizon first",
    })
    with patch("app.routers.cases.generate_summary", new=AsyncMock(return_value=fake_summary)):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    assert "summary" in resp.json()


def test_case_summary_accessible_in_provisional_state(api_client, db_session):
    """AC5: Case Summary accessible when action plan is in provisional state."""
    from unittest.mock import AsyncMock, patch

    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])

    fake_summary = json.dumps({
        "problem_statement": "Performance drop issue",
        "option_ranking": "Plan A leads",
        "recommended_plan": "Plan A",
        "probe_plan": "Short horizon first",
    })
    with patch("app.routers.cases.generate_summary", new=AsyncMock(return_value=fake_summary)):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    assert "summary" in resp.json()


def test_case_summary_accessible_in_final_state(api_client, db_session):
    """AC5: Case Summary accessible when action plan is in final state."""
    from unittest.mock import AsyncMock, patch

    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])
    _log_verdict_for_probe(db_session, probes["long"])

    fake_summary = json.dumps({
        "problem_statement": "Performance drop issue",
        "option_ranking": "Plan A leads",
        "recommended_plan": "Plan A",
        "probe_plan": "Short horizon first",
    })
    with patch("app.routers.cases.generate_summary", new=AsyncMock(return_value=fake_summary)):
        resp = api_client.post(f"/api/cases/{case.id}/summary")

    assert resp.status_code == 200
    assert "summary" in resp.json()


def test_get_case_still_returns_probes_and_verdict_log(api_client, db_session):
    """AC8: No regression — GET /cases/{id} still returns probes and verdict_log."""
    case, probes = _seed_case_with_three_probes(db_session)
    _log_verdict_for_probe(db_session, probes["short"])

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    # probes still present
    assert isinstance(data.get("probes"), list)
    assert len(data["probes"]) == 3
    # action_plan_state is new field and correct
    assert "action_plan_state" in data


def test_action_plan_state_absent_before_probe_stage(api_client, db_session):
    """AC8: action_plan_state is 'locked' (not missing) even at pre-probe stages."""
    case, probes = _seed_case_with_three_probes(db_session, stage="weigh")
    # Remove probes to simulate pre-probe stage
    from app import models
    db_session.query(models.Probe).filter(models.Probe.case_id == case.id).delete()
    db_session.commit()

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_plan_state"] == "locked"


def test_action_plan_endpoint_404_for_unknown_case(api_client):
    """AC6: GET /action-plan returns 404 for non-existent case (not a gate bypass)."""
    resp = api_client.get("/api/cases/nonexistent-id/action-plan")
    assert resp.status_code == 404
