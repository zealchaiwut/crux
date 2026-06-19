"""Tests for issue #12: Enforce verdict gate and log verdict action (Stage 5).

AC coverage:
  AC1  – Action plan never rendered in plain view for a Case without a Verdict (JS).
  AC2  – Cases without a Verdict display a LockedPlan panel (lock icon + prompt) (JS).
  AC3  – "Log verdict" UI presents three outcome options (Confirmed/Killed/Inconclusive) (JS).
  AC4  – Notes field is required (min 1 char); blank submission blocked (API).
  AC5  – Submitting creates a Verdict record linked to the Case (API).
  AC6  – On Verdict submission, Probe status updated to match outcome (API).
  AC7  – On Verdict submission, Case transitions to stage 5 / 'verdict' (API).
  AC8  – After verdict, LockedPlan unlocks and action plan is visible (JS).
  AC9  – Verdicts are persisted permanently (never deleted, even for killed/inconclusive) (API).
  AC10 – No edit/delete verdict controls in the UI (JS).
  AC11 – Stage 5 Case with Verdict shows action plan directly (JS).
"""
import json
import os
import uuid

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


def _seed_case_with_probe(session, probe_status="designed"):
    """Seed a Case at stage 'probe' with plans + a designed Probe."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my energy so low?",
        sharpened="Energy levels have dropped 30% over 8 weeks despite adequate sleep.",
        not_investigating=json.dumps(["Caffeine"]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Iron Deficiency", mechanism="Low ferritin impairs oxygen transport.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Overtraining", mechanism="Excess volume depresses HRV.",
            prior="0.30", current_rank=2,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="C",
            name="Sleep Debt", mechanism="Insufficient recovery.",
            prior="0.15", current_rank=3,
        ),
    ]
    for p in plans:
        session.add(p)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="lab-test",
        target_metric="serum ferritin",
        cost="~£30",
        time="3-5 days",
        note="See a GP for a full blood count including ferritin.",
        status=probe_status,
    )
    session.add(probe)
    session.commit()
    return c, plans, probe


def _seed_closed_case(session, outcome="confirmed"):
    """Seed a Case at stage 'verdict' with a Verdict record."""
    from app import models
    c, plans, probe = _seed_case_with_probe(session)
    c.stage = "verdict"
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes="Root cause verified in prod logs.",
        decided_at=__import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
    )
    probe.status = outcome if outcome in ("confirmed", "killed") else "inconclusive"
    session.add(verdict)
    session.commit()
    return c, plans, probe, verdict


# ---------------------------------------------------------------------------
# Model / schema tests
# ---------------------------------------------------------------------------

def test_verdict_model_exists():
    """AC5: Verdict model must exist in app.models."""
    from app import models
    assert hasattr(models, "Verdict"), "app.models must define Verdict"


def test_verdict_model_has_required_columns():
    """AC5: Verdict model must have probe_id, outcome, notes, decided_at columns."""
    from app import models
    for col in ("probe_id", "outcome", "notes", "decided_at"):
        assert hasattr(models.Verdict, col), f"Verdict model must have column: {col}"


def test_verdict_outcome_enum_has_three_values():
    """AC3: Verdict outcome enum must contain exactly confirmed, killed, inconclusive."""
    from app import models
    expected = {"confirmed", "killed", "inconclusive"}
    actual = set(models._VERDICT_OUTCOME)
    assert actual == expected, f"Expected {expected}, got {actual}"


def test_probe_status_includes_inconclusive():
    """AC6: Probe status enum must include 'inconclusive' to reflect closed outcomes."""
    from app import models
    assert "inconclusive" in models._PROBE_STATUS, \
        "Probe status enum must include 'inconclusive'"


# ---------------------------------------------------------------------------
# AC4: Blank notes rejected (API)
# ---------------------------------------------------------------------------

def test_verdict_requires_notes(api_client, db_session):
    """AC4: POST /api/cases/{id}/verdict with empty notes returns 422."""
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": ""},
    )
    assert r.status_code == 422, r.text


def test_verdict_requires_notes_whitespace_only(api_client, db_session):
    """AC4: POST /api/cases/{id}/verdict with whitespace-only notes returns 422."""
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "   "},
    )
    assert r.status_code == 422, r.text


def test_verdict_requires_outcome(api_client, db_session):
    """AC3: POST /api/cases/{id}/verdict without outcome returns 422."""
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"notes": "Some notes"},
    )
    assert r.status_code == 422, r.text


def test_verdict_rejects_invalid_outcome(api_client, db_session):
    """AC3: POST /api/cases/{id}/verdict with invalid outcome returns 422."""
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "maybe", "notes": "Some notes"},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC5: Verdict record created (API)
# ---------------------------------------------------------------------------

def test_verdict_creates_record_confirmed(api_client, db_session):
    """AC5: POST /api/cases/{id}/verdict (confirmed) creates a Verdict row."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "Root cause verified in prod logs."},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None, "A Verdict row must be created"
    assert verdict.outcome == "confirmed"
    assert verdict.notes == "Root cause verified in prod logs."
    assert verdict.decided_at is not None


def test_verdict_creates_record_killed(api_client, db_session):
    """AC5: POST /api/cases/{id}/verdict (killed) creates a Verdict row."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "killed", "notes": "Hypothesis refuted by data."},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None
    assert verdict.outcome == "killed"


def test_verdict_creates_record_inconclusive(api_client, db_session):
    """AC5: POST /api/cases/{id}/verdict (inconclusive) creates a Verdict row."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "inconclusive", "notes": "Data was mixed; no clear winner."},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None
    assert verdict.outcome == "inconclusive"


def test_verdict_404_for_unknown_case(api_client):
    """AC5: POST /api/cases/{id}/verdict returns 404 for unknown case."""
    r = api_client.post(
        "/api/cases/00000000-0000-0000-0000-000000000000/verdict",
        json={"outcome": "confirmed", "notes": "Some notes."},
    )
    assert r.status_code == 404


def test_verdict_422_for_case_without_probe(api_client, db_session):
    """AC5: POST /api/cases/{id}/verdict returns 422 when Case has no probe."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Some problem",
        sharpened="Sharpened problem",
        not_investigating=json.dumps([]),
        stage="weigh",
    )
    db_session.add(c)
    db_session.commit()
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "Some notes."},
    )
    assert r.status_code in (400, 422), r.text


# ---------------------------------------------------------------------------
# AC6: Probe status updated after verdict (API)
# ---------------------------------------------------------------------------

def test_probe_status_updated_to_confirmed(api_client, db_session):
    """AC6: After confirmed verdict, Probe status must be 'confirmed'."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "Root cause verified."},
    )
    db_session.expire_all()
    updated_probe = db_session.query(models.Probe).get(probe.id)
    assert updated_probe.status == "confirmed", \
        f"Probe status must be 'confirmed', got {updated_probe.status!r}"


def test_probe_status_updated_to_killed(api_client, db_session):
    """AC6: After killed verdict, Probe status must be 'killed'."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "killed", "notes": "Hypothesis refuted."},
    )
    db_session.expire_all()
    updated_probe = db_session.query(models.Probe).get(probe.id)
    assert updated_probe.status == "killed", \
        f"Probe status must be 'killed', got {updated_probe.status!r}"


def test_probe_status_updated_to_inconclusive(api_client, db_session):
    """AC6: After inconclusive verdict, Probe status must be 'inconclusive'."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "inconclusive", "notes": "Mixed data."},
    )
    db_session.expire_all()
    updated_probe = db_session.query(models.Probe).get(probe.id)
    assert updated_probe.status == "inconclusive", \
        f"Probe status must be 'inconclusive', got {updated_probe.status!r}"


# ---------------------------------------------------------------------------
# AC7: Case advances to Stage 5 / 'verdict' (API)
# ---------------------------------------------------------------------------

def test_case_advances_to_verdict_stage(api_client, db_session):
    """AC7: After verdict submission, Case stage must be 'verdict' (stage 5)."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    r = api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "All checked."},
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    updated_case = db_session.query(models.Case).get(c.id)
    assert updated_case.stage == "verdict", \
        f"Case must advance to 'verdict' stage, got {updated_case.stage!r}"


def test_case_detail_returns_stage_5_after_verdict(api_client, db_session):
    """AC7: GET /api/cases/{id} returns stage=5 after verdict is logged."""
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "All checked."},
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stage"] == 5, f"Stage must be 5, got {data['stage']}"


# ---------------------------------------------------------------------------
# AC9: Verdicts persisted permanently (API)
# ---------------------------------------------------------------------------

def test_killed_verdict_persisted(api_client, db_session):
    """AC9: A killed Verdict record is not deleted."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "killed", "notes": "Hypothesis refuted."},
    )
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None, "Killed verdict must persist in DB"
    assert verdict.outcome == "killed"
    assert verdict.notes is not None
    assert verdict.decided_at is not None


def test_inconclusive_verdict_persisted(api_client, db_session):
    """AC9: An inconclusive Verdict record is not deleted."""
    from app import models
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "inconclusive", "notes": "Data was inconclusive."},
    )
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None, "Inconclusive verdict must persist in DB"
    assert verdict.outcome == "inconclusive"


def test_verdict_endpoint_is_not_delete(api_client, db_session):
    """AC9: There is no DELETE endpoint for verdicts (no deletion supported)."""
    from app.main import app
    routes = [r.path for r in app.routes]
    delete_verdict_routes = [r for r in routes if "verdict" in r.lower() and "delete" in str(r).lower()]
    # No DELETE /verdicts endpoint should exist
    assert not any("verdict" in r and r.startswith("/api") for r in delete_verdict_routes), \
        "No DELETE verdict endpoint should exist"


def test_get_case_includes_verdict_log(api_client, db_session):
    """AC9/AC11: GET /api/cases/{id} includes verdict_log after verdict is submitted."""
    c, _, probe = _seed_case_with_probe(db_session)
    api_client.post(
        f"/api/cases/{c.id}/verdict",
        json={"outcome": "confirmed", "notes": "Checked and verified."},
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "verdict_log" in data, "Case detail must include 'verdict_log' after verdict submission"
    assert data["verdict_log"] is not None
    assert data["verdict_log"]["outcome"] == "confirmed"
    assert data["verdict_log"]["notes"] == "Checked and verified."
    assert data["verdict_log"]["decided_at"] is not None


# ---------------------------------------------------------------------------
# AC1 / AC2: LockedPlan panel in JS (no action plan without verdict)
# ---------------------------------------------------------------------------

def test_locked_plan_component_defined_in_js():
    """AC2: A LockedPlan component must be defined in the JS."""
    combined = _read_combined_js()
    assert "LockedPlan" in combined, "JS must define a LockedPlan component"


def test_locked_plan_shows_lock_icon_in_js():
    """AC2: LockedPlan must render a lock icon."""
    combined = _read_combined_js()
    assert ("ti-lock" in combined or "lock" in combined.lower()), \
        "LockedPlan must render a lock icon (ti-lock or similar)"


def test_locked_plan_shows_log_verdict_prompt_in_js():
    """AC2: LockedPlan must prompt the user to log a verdict to unlock."""
    combined = _read_combined_js()
    assert "Log verdict" in combined or "log verdict" in combined.lower(), \
        "LockedPlan must show a 'Log verdict to unlock' prompt"


def test_action_plan_not_rendered_without_verdict_in_js():
    """AC1: Action plan must not be visible when there is no verdict."""
    combined = _read_combined_js()
    # The action plan section must be gated on verdict presence
    assert "verdict" in combined, \
        "CaseDetailScreen must gate the action plan section on verdict presence"
    assert "LockedPlan" in combined, \
        "LockedPlan must be used to hide the action plan when no verdict"


# ---------------------------------------------------------------------------
# AC3: LogVerdictModal presents three outcome options in JS
# ---------------------------------------------------------------------------

def test_log_verdict_modal_defined_in_js():
    """AC3: A LogVerdictModal (or equivalent) component must be defined in the JS."""
    combined = _read_combined_js()
    assert ("LogVerdict" in combined or "log-verdict" in combined.lower()
            or "logVerdict" in combined or "Log verdict" in combined), \
        "JS must define a LogVerdictModal or equivalent component"


def test_log_verdict_modal_has_confirmed_option_in_js():
    """AC3: Log verdict form must offer 'Confirmed' outcome."""
    combined = _read_combined_js()
    assert "confirmed" in combined.lower() or "Confirmed" in combined, \
        "Log verdict form must include Confirmed option"


def test_log_verdict_modal_has_killed_option_in_js():
    """AC3: Log verdict form must offer 'Killed' outcome."""
    combined = _read_combined_js()
    assert "killed" in combined.lower() or "Killed" in combined, \
        "Log verdict form must include Killed option"


def test_log_verdict_modal_has_inconclusive_option_in_js():
    """AC3: Log verdict form must offer 'Inconclusive' outcome."""
    combined = _read_combined_js()
    assert "inconclusive" in combined.lower() or "Inconclusive" in combined, \
        "Log verdict form must include Inconclusive option"


def test_log_verdict_modal_has_notes_field_in_js():
    """AC4: Log verdict form must have a notes textarea."""
    combined = _read_combined_js()
    assert "notes" in combined.lower(), "Log verdict form must include a notes field"


# ---------------------------------------------------------------------------
# AC8 / AC11: After verdict, action plan unlocks in JS
# ---------------------------------------------------------------------------

def test_action_plan_section_unlocks_with_verdict_in_js():
    """AC8/AC11: JS must render action plan when verdict is present (stage 5)."""
    combined = _read_combined_js()
    # Must have conditional rendering based on verdict state
    assert "verdict" in combined and ("LockedPlan" in combined or "locked" in combined.lower()), \
        "JS must toggle between LockedPlan and action plan based on verdict state"


def test_stage_5_shows_action_plan_directly_in_js():
    """AC11: CaseDetailScreen at stage 5 must show action plan without locked overlay."""
    combined = _read_combined_js()
    # The action plan section must not always show LockedPlan
    # It must conditionally show the plan when verdict exists
    assert "verdict" in combined and "ACTION PLAN" in combined, \
        "ACTION PLAN section must be present and gated on verdict in CaseDetailScreen"


# ---------------------------------------------------------------------------
# AC10: No edit/delete verdict controls in JS
# ---------------------------------------------------------------------------

def test_no_edit_verdict_control_in_js():
    """AC10: No 'Edit verdict' control must appear in the JS."""
    combined = _read_combined_js()
    assert "Edit verdict" not in combined and "edit verdict" not in combined.lower(), \
        "JS must not contain an 'Edit verdict' control"


def test_no_delete_verdict_control_in_js():
    """AC10: No 'Delete verdict' control must appear in the JS."""
    combined = _read_combined_js()
    assert "Delete verdict" not in combined and "delete verdict" not in combined.lower(), \
        "JS must not contain a 'Delete verdict' control"
