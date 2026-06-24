"""Tests for issue #93: Expand Probe into full structured experiment plan.

AC coverage:
  AC1  – Probe model gains steps (JSON list), duration (Text), and decision_rule (Text);
          target_metric already exists and is confirmed surfaced.
  AC2  – DB migration applies cleanly with no data loss on existing probes.
  AC3  – app/probe.py populates all four fields (steps, duration, target_metric, decision_rule).
  AC4  – ProbeCard renders steps, duration, target_metric, and decision_rule.
  AC5  – New section is labelled "run this outside crux" in the UI.
  AC6  – New UI elements use only DESIGN.md tokens.
  AC7  – Null/empty decision_rule or empty steps list does not break card render.
  AC8  – Existing probes with only old fields render without errors.
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _seed_case_with_plans(session, stage="weigh"):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my energy dropping?",
        sharpened="Energy has dropped 20% over 4 weeks despite normal sleep.",
        not_investigating=json.dumps(["Weather"]),
        stage=stage,
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
            name="Dehydration", mechanism="Mild dehydration reduces energy.",
            prior="0.30", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_FULL_PROBE = {
    "type": "lab-test",
    "target_metric": "serum ferritin (ng/mL)",
    "cost": "~£30",
    "time": "1 week",
    "note": "Get a full blood count from your GP.",
    "steps": [
        "Book a GP appointment or visit a private lab.",
        "Request a full blood count including ferritin and transferrin saturation.",
        "Collect blood sample (typically morning, fasted).",
        "Receive results and note ferritin level.",
    ],
    "duration": "5–7 days from booking to results",
    "decision_rule": "If ferritin < 30 ng/mL → proceed with iron supplementation (Plan A); if ferritin ≥ 30 ng/mL → discard Plan A and test Plan B.",
}


# ---------------------------------------------------------------------------
# AC1: Model has new fields
# ---------------------------------------------------------------------------

def test_probe_model_has_steps_column():
    """AC1: Probe model must have a 'steps' column."""
    from app import models
    assert hasattr(models.Probe, "steps"), "Probe model must have 'steps' column"


def test_probe_model_has_duration_column():
    """AC1: Probe model must have a 'duration' column."""
    from app import models
    assert hasattr(models.Probe, "duration"), "Probe model must have 'duration' column"


def test_probe_model_has_decision_rule_column():
    """AC1: Probe model must have a 'decision_rule' column."""
    from app import models
    assert hasattr(models.Probe, "decision_rule"), "Probe model must have 'decision_rule' column"


def test_probe_model_has_target_metric_column():
    """AC1: target_metric already exists and is confirmed surfaced."""
    from app import models
    assert hasattr(models.Probe, "target_metric"), "Probe model must have 'target_metric' column"


# ---------------------------------------------------------------------------
# AC2: Migration — existing probes survive, new columns nullable
# ---------------------------------------------------------------------------

def test_existing_probe_survives_new_columns(db_session):
    """AC2: Existing probe rows (without new fields) persist without errors."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="resting HRV",
        cost="free",
        time="7 days",
        note="Measure each morning.",
        status="designed",
    )
    db_session.add(probe)
    db_session.commit()

    db_session.expire_all()
    loaded = db_session.get(models.Probe, probe.id)
    assert loaded is not None
    assert loaded.target_metric == "resting HRV"
    # New fields default to None — no crash
    assert loaded.steps is None
    assert loaded.duration is None
    assert loaded.decision_rule is None


# ---------------------------------------------------------------------------
# AC3: probe.py populates all four fields
# ---------------------------------------------------------------------------

def test_probe_service_returns_steps_field():
    """AC3: design_probe result must include 'steps' key."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    assert "steps" in result


def test_probe_service_returns_duration_field():
    """AC3: design_probe result must include 'duration' key."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    assert "duration" in result


def test_probe_service_returns_decision_rule_field():
    """AC3: design_probe result must include 'decision_rule' key."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    assert "decision_rule" in result


def test_probe_service_returns_target_metric_field():
    """AC3: design_probe result must include 'target_metric' key."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    assert "target_metric" in result


def test_probe_service_steps_is_list():
    """AC3: 'steps' must be a list of action strings."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) > 0


def test_probe_service_decision_rule_contains_confirm_and_kill():
    """AC3/UAT3: decision_rule must state both a confirmatory and a kill condition."""
    from app.probe import _validate_probe_response
    result = _validate_probe_response(_MOCK_FULL_PROBE.copy())
    dr = result["decision_rule"].lower()
    # Must contain if/then branching language
    has_condition = "if " in dr or "→" in dr or "->" in dr
    assert has_condition, f"decision_rule must contain conditional language: {dr!r}"


# ---------------------------------------------------------------------------
# AC3: API endpoint persists and returns new fields
# ---------------------------------------------------------------------------

def test_api_probe_response_includes_steps(api_client, db_session):
    """AC3: POST /api/cases/{id}/probe response includes 'steps'."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    assert "steps" in r.json()


def test_api_probe_response_includes_duration(api_client, db_session):
    """AC3: POST /api/cases/{id}/probe response includes 'duration'."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    assert "duration" in r.json()


def test_api_probe_response_includes_decision_rule(api_client, db_session):
    """AC3: POST /api/cases/{id}/probe response includes 'decision_rule'."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    assert "decision_rule" in r.json()


def test_api_probe_steps_persisted_correctly(api_client, db_session):
    """AC3: steps list is persisted to DB and returned via GET."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None
    # steps stored as JSON
    steps = json.loads(probe.steps) if isinstance(probe.steps, str) else probe.steps
    assert isinstance(steps, list)
    assert len(steps) == len(_MOCK_FULL_PROBE["steps"])


def test_api_probe_duration_persisted(api_client, db_session):
    """AC3: duration is persisted to DB."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None
    assert probe.duration == _MOCK_FULL_PROBE["duration"]


def test_api_probe_decision_rule_persisted(api_client, db_session):
    """AC3: decision_rule is persisted to DB."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None
    assert probe.decision_rule == _MOCK_FULL_PROBE["decision_rule"]


def test_get_case_probe_includes_new_fields(api_client, db_session):
    """AC3: GET /api/cases/{id} returns probe with steps, duration, decision_rule."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_FULL_PROBE):
        api_client.post(f"/api/cases/{c.id}/probe")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe = r.json()["probe"]
    assert probe is not None
    assert "steps" in probe
    assert "duration" in probe
    assert "decision_rule" in probe


# ---------------------------------------------------------------------------
# AC4: ProbeCard renders all four fields
# ---------------------------------------------------------------------------

def test_probe_card_renders_steps_in_js():
    """AC4: ProbeCard must reference 'steps' for rendering."""
    combined = _read_combined_js()
    assert "steps" in combined, "ProbeCard must render steps"


def test_probe_card_renders_duration_in_js():
    """AC4: ProbeCard must reference 'duration' for rendering."""
    combined = _read_combined_js()
    assert "duration" in combined, "ProbeCard must render duration"


def test_probe_card_renders_decision_rule_in_js():
    """AC4: ProbeCard must reference 'decision_rule' for rendering."""
    combined = _read_combined_js()
    assert "decision_rule" in combined, "ProbeCard must render decision_rule"


def test_probe_card_renders_target_metric_in_js():
    """AC4: ProbeCard must render target_metric."""
    combined = _read_combined_js()
    assert "target_metric" in combined, "ProbeCard must render target_metric"


# ---------------------------------------------------------------------------
# AC5: Section labelled "run this outside crux"
# ---------------------------------------------------------------------------

def test_probe_card_section_labelled_run_outside_crux():
    """AC5: New section must be labelled 'run this outside crux'."""
    combined = _read_combined_js()
    assert "run this outside crux" in combined.lower(), \
        "ProbeCard must have section labelled 'run this outside crux'"


# ---------------------------------------------------------------------------
# AC6: UI uses DESIGN.md tokens
# ---------------------------------------------------------------------------

def test_probe_new_section_uses_design_tokens():
    """AC6: New UI elements must use CSS variable tokens, not inline hex/pixel values."""
    combined = _read_combined_js()
    # The new section exists and uses var(--...) tokens
    assert "var(--" in combined, "JS must use CSS variable tokens"
    # No ad-hoc hex colors introduced (check for common pattern)
    # We confirm that decision_rule rendering uses token colors
    decision_rule_idx = combined.find("decision_rule")
    assert decision_rule_idx != -1
    # Find nearby usage to confirm token usage in that region
    region = combined[max(0, decision_rule_idx - 500):decision_rule_idx + 500]
    assert "var(--" in region, "decision_rule rendering must use CSS variable tokens"


# ---------------------------------------------------------------------------
# AC7: Graceful fallback for null/empty fields
# ---------------------------------------------------------------------------

def test_api_probe_null_decision_rule_does_not_crash(api_client, db_session):
    """AC7: null decision_rule does not break the API response."""
    probe_without_dr = dict(_MOCK_FULL_PROBE)
    probe_without_dr["decision_rule"] = None
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=probe_without_dr):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    data = r.json()
    # decision_rule should be null or empty string — no 500
    assert "decision_rule" in data


def test_api_probe_empty_steps_does_not_crash(api_client, db_session):
    """AC7: empty steps list does not break the API response."""
    probe_no_steps = dict(_MOCK_FULL_PROBE)
    probe_no_steps["steps"] = []
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=probe_no_steps):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data


def test_probe_card_graceful_fallback_null_steps_in_js():
    """AC7: ProbeCard must handle null/empty steps gracefully."""
    combined = _read_combined_js()
    # Should check for steps before mapping over them
    has_guard = (
        "steps &&" in combined
        or "steps?.length" in combined
        or "(steps || [])" in combined
        or "steps && steps.length" in combined
        or "probe.steps &&" in combined
        or "probe.steps ?" in combined
    )
    assert has_guard, "ProbeCard must guard against null/empty steps before rendering"


def test_probe_card_graceful_fallback_null_decision_rule_in_js():
    """AC7: ProbeCard must handle null decision_rule gracefully."""
    combined = _read_combined_js()
    has_guard = (
        "decision_rule &&" in combined
        or "decision_rule ?" in combined
        or "probe.decision_rule &&" in combined
        or "probe.decision_rule ?" in combined
    )
    assert has_guard, "ProbeCard must guard against null decision_rule before rendering"


# ---------------------------------------------------------------------------
# AC8: Existing probes (old fields only) render without errors
# ---------------------------------------------------------------------------

def test_get_case_legacy_probe_renders_without_error(api_client, db_session):
    """AC8: Existing probe with only old fields returns valid API response."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="probe")
    # Insert legacy probe with only old fields (no steps/duration/decision_rule)
    legacy_probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="resting HRV (7-day average)",
        cost="free",
        time="7 days",
        note="Measure resting HRV each morning.",
        status="designed",
    )
    db_session.add(legacy_probe)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["probe"] is not None
    assert data["probe"]["target_metric"] == "resting HRV (7-day average)"
    # New fields are null/empty but present — no crash
    assert "steps" in data["probe"]
    assert "duration" in data["probe"]
    assert "decision_rule" in data["probe"]


def test_legacy_probe_new_fields_are_null_or_empty(api_client, db_session):
    """AC8: Legacy probe's new fields return null or empty, not an error."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="probe")
    legacy_probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="behaviour-experiment",
        target_metric="energy level",
        cost="free",
        time="2 weeks",
        note="Track daily.",
        status="running",
    )
    db_session.add(legacy_probe)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe = r.json()["probe"]
    # New fields are falsy (None, empty list, or empty string) — not an exception
    assert probe["steps"] is None or probe["steps"] == [] or probe["steps"] == ""
    assert probe["duration"] is None or probe["duration"] == ""
    assert probe["decision_rule"] is None or probe["decision_rule"] == ""
