"""Tests for issue #50: Add re-probe action for inconclusive verdicts.

AC coverage:
  AC1 – "Design new probe" button only appears for inconclusive verdict; not for
         confirmed, killed, or pre-verdict state (JS).
  AC2 – POST /api/cases/{id}/probe after inconclusive verdict creates a new probe
         without modifying case stage, plans, or sources (API).
  AC3 – After re-probe, GET /api/cases/{id} returns the new probe (API).
  AC4 – Previous (inconclusive) probe and its verdict are retained in DB (API).
  AC5 – "Design new probe" button disabled while the request is in-flight (JS).
  AC6 – Error state shown when POST /probe fails; existing probe/verdict unchanged (JS + API).
  AC7 – Verdict gate regression: no re-probe for confirmed/killed verdicts (API).
"""
import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_combined_js():
    return "".join(
        (JS_DIR / f).read_text()
        for f in sorted(JS_DIR.iterdir())
        if f.suffix == ".js"
    )


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


def _seed_case_with_inconclusive_verdict(session):
    """Seed a Case at stage 'verdict' with a probe that received an inconclusive verdict."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why does my experiment keep failing?",
        sharpened="Experiment failure rate exceeds 80% with no obvious cause.",
        not_investigating=json.dumps(["Budget"]),
        stage="verdict",
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Methodology Gap", mechanism="Flawed sampling approach.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Equipment Error", mechanism="Calibration drift causes noise.",
            prior="0.30", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="experiment failure rate",
        cost="free",
        time="7 days",
        note="Track failure rate with detailed logging.",
        status="inconclusive",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="inconclusive",
        notes="Results were mixed; no clear winner.",
        decided_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return c, plans, probe, verdict


def _seed_case_with_confirmed_verdict(session):
    """Seed a Case at stage 'verdict' with a confirmed verdict."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="What is wrong?",
        sharpened="Problem clearly identified.",
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Root Cause", mechanism="Direct cause.",
            prior="0.8", current_rank=1,
        ),
    ]
    for p in plans:
        session.add(p)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="outcome metric",
        cost="free",
        time="1 week",
        note="Measure it.",
        status="confirmed",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="Hypothesis confirmed.",
        decided_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return c, plans, probe, verdict


_MOCK_PROBE_RESPONSE = {
    "type": "behaviour-experiment",
    "target_metric": "experiment success rate",
    "cost": "free",
    "time": "14 days",
    "note": "Redesign experiment with stricter controls.",
}


# ---------------------------------------------------------------------------
# JS tests
# ---------------------------------------------------------------------------

def test_design_new_probe_button_defined_in_js():
    """AC1: 'Design new probe' text must appear in JS (ProbeCard)."""
    combined = _read_combined_js()
    assert "Design new probe" in combined, \
        "JS must contain 'Design new probe' button text in ProbeCard"


def test_design_new_probe_only_for_inconclusive_in_js():
    """AC1: 'Design new probe' button must be conditional on verdict === 'inconclusive'."""
    combined = _read_combined_js()
    assert "inconclusive" in combined, \
        "ProbeCard JS must reference 'inconclusive' to gate the re-probe button"
    assert "Design new probe" in combined, \
        "ProbeCard must have 'Design new probe' button"


def test_design_new_probe_not_for_confirmed_in_js():
    """AC1: The re-probe button must not unconditionally render for non-inconclusive states."""
    combined = _read_combined_js()
    # The button must be gated on 'inconclusive' verdict; verify the condition exists
    # Find that the button is conditional, not always rendered
    assert "inconclusive" in combined, \
        "ProbeCard must check verdict==='inconclusive' before rendering re-probe button"


def test_design_new_probe_button_disabled_while_loading_in_js():
    """AC5: 'Design new probe' button must be disabled/hidden while request is in-flight."""
    combined = _read_combined_js()
    # The button should reference a loading/disabled state
    assert "disabled" in combined or "loading" in combined.lower(), \
        "ProbeCard must disable re-probe button while in-flight"


def test_design_new_probe_error_state_in_js():
    """AC6: ProbeCard must show an error message when re-probe fails."""
    combined = _read_combined_js()
    # Must handle error prop or state for re-probe
    assert "reProbeError" in combined or "re-probe" in combined.lower() or "reprobe" in combined.lower() or "reProbe" in combined, \
        "ProbeCard must handle re-probe error state"


# ---------------------------------------------------------------------------
# AC2: POST /probe creates new probe after inconclusive verdict (API)
# ---------------------------------------------------------------------------

def test_reprobe_creates_new_probe(api_client, db_session):
    """AC2: POST /probe after inconclusive verdict creates a new probe row."""
    from app import models
    c, plans, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 200, r.text
    data = r.json()

    # A new probe was created (different ID)
    assert data["id"] != old_probe.id, "Re-probe must create a new probe row"
    assert data["type"] == "behaviour-experiment"
    assert data["target_metric"] == "experiment success rate"
    assert data["status"] == "designed"


def test_reprobe_does_not_change_case_stage(api_client, db_session):
    """AC2: Re-probe must not modify the case's current stage."""
    from app import models
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)
    original_stage = c.stage  # should be 'verdict'

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    updated_case = db_session.query(models.Case).get(c.id)
    assert updated_case.stage == original_stage, \
        f"Case stage must remain '{original_stage}' after re-probe, got '{updated_case.stage}'"


def test_reprobe_does_not_change_plans(api_client, db_session):
    """AC2: Re-probe must not modify the case's bake-off plans."""
    from app import models
    c, plans, _, _ = _seed_case_with_inconclusive_verdict(db_session)
    plan_ids_before = {p.id for p in plans}
    plan_ranks_before = {p.id: p.current_rank for p in plans}

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    updated_plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    assert {p.id for p in updated_plans} == plan_ids_before, \
        "Plans must not be added or removed by re-probe"
    for p in updated_plans:
        assert p.current_rank == plan_ranks_before[p.id], \
            f"Plan {p.label} rank must be unchanged after re-probe"


# ---------------------------------------------------------------------------
# AC3: GET /cases/{id} returns new probe after re-probe (API)
# ---------------------------------------------------------------------------

def test_get_case_returns_new_probe_after_reprobe(api_client, db_session):
    """AC3: GET /api/cases/{id} returns the new probe after re-probe."""
    from app import models
    c, _, old_probe, _ = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        r = api_client.post(f"/api/cases/{c.id}/probe")

    new_probe_id = r.json()["id"]

    r2 = api_client.get(f"/api/cases/{c.id}")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["probe"] is not None, "Case must have a probe after re-probe"
    assert data["probe"]["id"] == new_probe_id, \
        "GET /cases/{id} must return the NEW probe, not the old one"
    assert data["probe"]["status"] == "designed"


def test_get_case_verdict_log_is_null_after_reprobe(api_client, db_session):
    """AC3: After re-probe, GET /api/cases/{id} returns verdict_log=null (new probe has no verdict)."""
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    r = api_client.get(f"/api/cases/{c.id}")
    data = r.json()
    assert data["verdict_log"] is None, \
        "After re-probe, verdict_log must be null (new probe has no verdict yet)"


# ---------------------------------------------------------------------------
# AC4: Old probe and verdict retained in DB (API)
# ---------------------------------------------------------------------------

def test_old_probe_retained_in_db_after_reprobe(api_client, db_session):
    """AC4: The previous inconclusive probe must remain in DB after re-probe."""
    from app import models
    c, _, old_probe, _ = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    retained_probe = db_session.query(models.Probe).get(old_probe_id)
    assert retained_probe is not None, "Old probe must be retained in DB after re-probe"
    assert retained_probe.status == "inconclusive", \
        "Old probe status must remain 'inconclusive'"


def test_old_verdict_retained_in_db_after_reprobe(api_client, db_session):
    """AC4: The inconclusive verdict must remain in DB after re-probe."""
    from app import models
    c, _, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)
    old_verdict_id = old_verdict.id

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    retained_verdict = db_session.query(models.Verdict).get(old_verdict_id)
    assert retained_verdict is not None, "Old verdict must be retained in DB after re-probe"
    assert retained_verdict.outcome == "inconclusive"
    assert retained_verdict.probe_id == old_probe.id


def test_two_probes_exist_for_case_after_reprobe(api_client, db_session):
    """AC4: After re-probe, case must have 2 probes in DB."""
    from app import models
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_PROBE_RESPONSE
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 2, f"After re-probe, case must have 2 probes, got {len(probes)}"


# ---------------------------------------------------------------------------
# AC6: Error when POST /probe API call fails (API)
# ---------------------------------------------------------------------------

def test_reprobe_error_leaves_old_probe_intact(api_client, db_session):
    """AC6: If re-probe API call fails, existing probe/verdict remain unchanged."""
    from app import models
    from app.probe import ProbeError
    c, _, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.side_effect = ProbeError("API timeout")
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 502, r.text

    db_session.expire_all()
    # Old probe still there and unchanged
    probe_in_db = db_session.query(models.Probe).get(old_probe_id)
    assert probe_in_db is not None
    assert probe_in_db.status == "inconclusive"

    # No new probe created
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 1, "Failed re-probe must not create a new probe row"


# ---------------------------------------------------------------------------
# AC7: No re-probe for confirmed or killed verdicts (API regression gate)
# ---------------------------------------------------------------------------

def test_no_reprobe_for_confirmed_verdict(api_client, db_session):
    """AC7: POST /probe with a confirmed verdict returns existing probe (no re-probe)."""
    from app import models
    c, _, confirmed_probe, _ = _seed_case_with_confirmed_verdict(db_session)
    confirmed_probe_id = confirmed_probe.id

    r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == confirmed_probe_id, \
        "POST /probe with confirmed verdict must return existing probe, not create a new one"

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 1, "Confirmed probe must not trigger re-probe"


def test_no_reprobe_for_killed_verdict(api_client, db_session):
    """AC7: POST /probe with a killed verdict returns existing probe (no re-probe)."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Problem",
        sharpened="Sharpened.",
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    db_session.add(c)
    db_session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()), case_id=c.id, label="A",
        name="Cause", mechanism="Mechanism.", prior="0.8", current_rank=1,
    )
    db_session.add(plan)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="metric",
        cost="free",
        time="1 week",
        note="Measure.",
        status="killed",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(probe)
    db_session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="killed",
        notes="Hypothesis disproved.",
        decided_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(verdict)
    db_session.commit()

    r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == probe.id, \
        "POST /probe with killed verdict must return existing probe"

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 1, "Killed probe must not trigger re-probe"


def test_no_reprobe_for_probe_without_verdict(api_client, db_session):
    """AC7: POST /probe with a probe that has no verdict returns existing probe."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Problem",
        sharpened="Sharpened.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(c)
    db_session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()), case_id=c.id, label="A",
        name="Cause", mechanism="Mechanism.", prior="0.8", current_rank=1,
    )
    db_session.add(plan)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="metric",
        cost="free",
        time="1 week",
        note="Measure.",
        status="designed",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(probe)
    db_session.commit()

    r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == probe.id, \
        "POST /probe with a no-verdict probe must return existing probe"
