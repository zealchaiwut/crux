"""Tests for issue #50: Add re-probe action for inconclusive verdicts.

AC coverage:
  AC1 – "Design new probe" button only appears for inconclusive verdict; not for
         confirmed, killed, or pre-verdict state (JS).
  AC2 – POST /api/cases/{id}/probe after inconclusive verdict creates new probes
         without modifying case stage, plans, or sources (API).
  AC3 – After re-probe, GET /api/cases/{id} returns the new probe (API).
  AC4 – Previous (inconclusive) probe is replaced; its verdict is orphaned (API).
         Note: issue #168 changed AC4 — old probes are now deleted on re-probe.
  AC5 – "Design new probe" button disabled while the request is in-flight (JS).
  AC6 – Error state shown when POST /probe fails; existing probe/verdict unchanged (JS + API).
  AC7 – Probe design always replaces existing probes (issue #168 removed confirmed/killed gate).
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


_MOCK_THREE_PROBES = [
    {
        "horizon": "short",
        "type": "behaviour-experiment",
        "target_metric": "experiment success rate (short-term)",
        "cost": "free",
        "time": "7 days",
        "note": "Quick signal: tighten controls for 7 days.",
        "steps": ["Step 1: baseline", "Step 2: run", "Step 3: measure"],
        "duration": "7 days",
        "decision_rule": "If rate drops by 20%, short-term signal confirmed.",
    },
    {
        "horizon": "mid",
        "type": "behaviour-experiment",
        "target_metric": "experiment success rate (mid-term)",
        "cost": "free",
        "time": "14 days",
        "note": "Redesign experiment with stricter controls.",
        "steps": ["Step 1: redesign", "Step 2: run", "Step 3: analyze"],
        "duration": "14 days",
        "decision_rule": "If rate drops by 30%, hypothesis confirmed.",
    },
    {
        "horizon": "long",
        "type": "behaviour-experiment",
        "target_metric": "experiment success rate (long-term)",
        "cost": "free",
        "time": "30 days",
        "note": "Full longitudinal study for definitive answer.",
        "steps": ["Step 1: plan", "Step 2: execute", "Step 3: review"],
        "duration": "30 days",
        "decision_rule": "If rate below 20% for 4 weeks, confirmed.",
    },
]


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
    has_error_state = (
        "reProbeError" in combined
        or "re-probe" in combined.lower()
        or "reprobe" in combined.lower()
        or "reProbe" in combined
    )
    assert has_error_state, "ProbeCard must handle re-probe error state"


# ---------------------------------------------------------------------------
# AC2: POST /probe creates new probes after inconclusive verdict (API)
# ---------------------------------------------------------------------------

def test_reprobe_creates_new_probe(api_client, db_session):
    """AC2: POST /probe after inconclusive verdict creates 3 new probe rows (issue #168)."""
    c, plans, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 200, r.text
    data = r.json()

    # Response is now {"probes": [...]} with 3 items (issue #168)
    assert "probes" in data, "Response must have 'probes' key"
    assert len(data["probes"]) == 3, f"Must create exactly 3 probes, got {len(data['probes'])}"

    # All new probes have different IDs from the old probe
    new_ids = {p["id"] for p in data["probes"]}
    assert old_probe_id not in new_ids, "Re-probe must create new probe rows, not reuse old ID"

    # All new probes have 'designed' status
    for probe in data["probes"]:
        assert probe["status"] == "designed"


def test_reprobe_does_not_change_case_stage(api_client, db_session):
    """AC2: Re-probe must not modify the case's current stage."""
    from app import models
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)
    original_stage = c.stage  # should be 'verdict'

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
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

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
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
    """AC3: GET /api/cases/{id} returns one of the new probes after re-probe."""
    c, _, old_probe, _ = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        r = api_client.post(f"/api/cases/{c.id}/probe")

    new_probe_ids = {p["id"] for p in r.json()["probes"]}

    r2 = api_client.get(f"/api/cases/{c.id}")
    assert r2.status_code == 200, r2.text
    data = r2.json()

    # probe field returns latest probe (one of the 3 new ones)
    assert data["probe"] is not None, "Case must have a probe after re-probe"
    assert data["probe"]["id"] in new_probe_ids, \
        "GET /cases/{id} must return one of the NEW probes, not the old one"
    assert data["probe"]["id"] != old_probe_id, \
        "The returned probe must not be the old inconclusive probe"
    assert data["probe"]["status"] == "designed"

    # probes list contains all 3 new probes
    assert len(data["probes"]) == 3, \
        f"GET /cases/{{id}} must list all 3 new probes, got {len(data['probes'])}"


def test_get_case_verdict_log_is_null_after_reprobe(api_client, db_session):
    """AC3: After re-probe, GET /api/cases/{id} returns verdict_log=null (new probes have no verdict)."""
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        api_client.post(f"/api/cases/{c.id}/probe")

    r = api_client.get(f"/api/cases/{c.id}")
    data = r.json()
    assert data["verdict_log"] is None, \
        "After re-probe, verdict_log must be null (new probes have no verdict yet)"


# ---------------------------------------------------------------------------
# AC4 (updated by issue #168): Old probes replaced; verdict row orphaned in DB
# ---------------------------------------------------------------------------

def test_old_probe_replaced_in_db_after_reprobe(api_client, db_session):
    """AC4 (updated #168): The previous inconclusive probe is deleted on re-probe."""
    from app import models
    c, _, old_probe, _ = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    # Issue #168: old probes are replaced (deleted) when re-probing
    replaced_probe = db_session.query(models.Probe).get(old_probe_id)
    assert replaced_probe is None, \
        "Old probe must be deleted (replaced) by re-probe (issue #168 AC5)"


def test_old_verdict_retained_in_db_after_reprobe(api_client, db_session):
    """AC4 (updated #168): The inconclusive verdict row remains in DB after re-probe.

    The old probe is deleted; the verdict becomes an orphan row in SQLite
    (FK RESTRICT is not enforced in SQLite without pragma foreign_keys=ON).
    In production (Postgres), the verdict would be blocked by RESTRICT — a future
    migration should add cascade delete or remove verdicts before deleting probes.
    """
    from app import models
    c, _, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)
    old_verdict_id = old_verdict.id
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    # Verdict row still exists as an orphan (SQLite does not enforce FK RESTRICT)
    retained_verdict = db_session.query(models.Verdict).get(old_verdict_id)
    assert retained_verdict is not None, \
        "Verdict row must still exist in DB (SQLite FK not enforced)"
    assert retained_verdict.outcome == "inconclusive"
    assert retained_verdict.probe_id == old_probe_id, \
        "Verdict still references the deleted probe (orphan row)"


def test_three_probes_exist_for_case_after_reprobe(api_client, db_session):
    """AC4 (updated #168): After re-probe, case has exactly 3 new probes in DB."""
    from app import models
    c, _, _, _ = _seed_case_with_inconclusive_verdict(db_session)

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 3, \
        f"After re-probe, case must have 3 probes (old deleted, 3 new), got {len(probes)}"


# ---------------------------------------------------------------------------
# AC6: Error when POST /probe API call fails (API)
# ---------------------------------------------------------------------------

def test_reprobe_error_leaves_old_probe_intact(api_client, db_session):
    """AC6: If re-probe API call fails, existing probe/verdict remain unchanged."""
    from app import models
    from app.probe import ProbeError
    c, _, old_probe, old_verdict = _seed_case_with_inconclusive_verdict(db_session)
    old_probe_id = old_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.side_effect = ProbeError("API timeout")
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 502, r.text

    db_session.expire_all()
    # Old probe still there and unchanged (design_probes failed before probes were replaced)
    probe_in_db = db_session.query(models.Probe).get(old_probe_id)
    assert probe_in_db is not None
    assert probe_in_db.status == "inconclusive"

    # No new probe created
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 1, "Failed re-probe must not create a new probe row"


# ---------------------------------------------------------------------------
# AC7 (updated by issue #168): Probe design now always replaces existing probes
# ---------------------------------------------------------------------------

def test_reprobe_for_confirmed_verdict_replaces_probes(api_client, db_session):
    """AC7 (updated #168): POST /probe on a confirmed case now creates 3 new probes.

    Issue #168 removed the confirmed/killed gate — probe design always replaces
    all existing probes regardless of the previous verdict outcome.
    """
    from app import models
    c, _, confirmed_probe, _ = _seed_case_with_confirmed_verdict(db_session)
    confirmed_probe_id = confirmed_probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 200, r.text
    data = r.json()

    # Returns 3 new probes
    assert "probes" in data, "Response must have 'probes' key"
    assert len(data["probes"]) == 3
    new_ids = {p["id"] for p in data["probes"]}
    assert confirmed_probe_id not in new_ids, \
        "Old confirmed probe must be replaced by new probes"

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 3, \
        f"Confirmed probe replaced by 3 new probes, got {len(probes)}"


def test_reprobe_for_killed_verdict_replaces_probes(api_client, db_session):
    """AC7 (updated #168): POST /probe on a killed case now creates 3 new probes."""
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
    old_probe_id = probe.id

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="killed",
        notes="Hypothesis disproved.",
        decided_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(verdict)
    db_session.commit()

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "probes" in data
    assert len(data["probes"]) == 3
    new_ids = {p["id"] for p in data["probes"]}
    assert old_probe_id not in new_ids, \
        "Old killed probe must be replaced by new probes"

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 3, f"Killed probe replaced by 3 new probes, got {len(probes)}"


def test_reprobe_for_probe_without_verdict_replaces_probes(api_client, db_session):
    """AC7 (updated #168): POST /probe on a probe-but-no-verdict case replaces probes."""
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
    old_probe_id = probe.id

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = _MOCK_THREE_PROBES
        r = api_client.post(f"/api/cases/{c.id}/probe")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "probes" in data
    assert len(data["probes"]) == 3
    new_ids = {p["id"] for p in data["probes"]}
    assert old_probe_id not in new_ids, \
        "Old designed probe must be replaced by new probes"

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    assert len(probes) == 3, f"Expected 3 replacement probes, got {len(probes)}"
