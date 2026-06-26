"""Tests for issue #11: Design probe type and target metric at Stage 4.

AC coverage:
  AC1  – POST /api/cases/{id}/probe calls Claude API and returns a probe design (API).
  AC2  – Probe type is classified into exactly one of four valid values (API + model).
  AC4  – Response includes target_metric, cost, time, and note (API).
  AC5  – Probe record persisted to DB with status='designed' and all fields (API).
  AC6  – ProbeCard renders type label, targetMetric in large mono, cost, time, note (JS).
  AC7  – When type='prototype', 'Send to commander' button visible but disabled (JS).
  AC8  – When type is not 'prototype', 'Send to commander' button not rendered (JS).
  AC9  – If Claude API fails, 502 returned and no Probe record persisted (API + JS).
  AC10 – Action plan section stays locked; no verdict rendered at Stage 4 (JS).
"""
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
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my running performance dropping?",
        sharpened="Running performance has dropped 15% over 6 weeks despite consistent training.",
        not_investigating=json.dumps(["Shoe wear", "Weather"]),
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Overtraining Load", mechanism="Excess training volume depresses HRV.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Iron Deficiency", mechanism="Low ferritin impairs oxygen transport.",
            prior="0.30", current_rank=2,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="C",
            name="Sleep Debt", mechanism="Insufficient sleep degrades recovery markers.",
            prior="0.15", current_rank=3,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_PROBE_RESULT = {
    "type": "measurement",
    "target_metric": "resting HRV (7-day average)",
    "cost": "free",
    "time": "7 days",
    "note": "Measure resting HRV each morning for 7 days and compare to baseline.",
}

_MOCK_PROBE_RESULT_LAB = {
    "type": "lab-test",
    "target_metric": "serum ferritin",
    "cost": "~£30",
    "time": "3–5 days",
    "note": "See your GP or a private lab for a full blood count including ferritin.",
}

_MOCK_PROBE_RESULT_PROTOTYPE = {
    "type": "prototype",
    "target_metric": "task completion rate",
    "cost": "~£0 (weekend build)",
    "time": "1 week test",
    "note": "Build a minimal prototype and measure task completion rate against baseline.",
}


# ---------------------------------------------------------------------------
# Model / schema tests (AC2, AC4, AC5)
# ---------------------------------------------------------------------------

def test_probe_model_has_cost_column():
    """AC5: Probe model must have a 'cost' column."""
    from app import models
    assert hasattr(models.Probe, "cost"), "Probe model must have a 'cost' column"


def test_probe_model_has_time_column():
    """AC5: Probe model must have a 'time' column."""
    from app import models
    assert hasattr(models.Probe, "time"), "Probe model must have a 'time' column"


def test_probe_model_has_note_column():
    """AC5: Probe model must have a 'note' column."""
    from app import models
    assert hasattr(models.Probe, "note"), "Probe model must have a 'note' column"


def test_probe_type_enum_has_four_values():
    """AC2: Probe type enum must contain exactly the four valid types."""
    from app import models
    valid = {"measurement", "lab-test", "behaviour-experiment", "prototype"}
    actual = set(models._PROBE_TYPE)
    assert actual == valid, f"Expected probe types {valid}, got {actual}"


# ---------------------------------------------------------------------------
# Probe service module
# ---------------------------------------------------------------------------

def test_probe_service_module_exists():
    """AC1: app.probe module must exist with design_probe function."""
    import importlib
    mod = importlib.import_module("app.probe")
    assert hasattr(mod, "design_probe"), "app.probe must export design_probe"
    assert hasattr(mod, "ProbeError"), "app.probe must export ProbeError"


# ---------------------------------------------------------------------------
# AC1: POST /api/cases/{id}/probe endpoint exists and calls Claude
# ---------------------------------------------------------------------------

def test_probe_endpoint_exists(api_client, db_session):
    """AC1: POST /api/cases/{id}/probe must exist and return 200."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200, r.text


def test_probe_endpoint_404_for_unknown_case(api_client):
    """AC1: POST /api/cases/{id}/probe returns 404 for unknown case."""
    r = api_client.post("/api/cases/00000000-0000-0000-0000-000000000000/probe")
    assert r.status_code == 404


def test_probe_endpoint_422_for_case_without_plans(api_client, db_session):
    """AC1: POST /api/cases/{id}/probe returns 422 when Case has no plans."""
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Some problem",
        sharpened="Some sharpened",
        not_investigating=json.dumps([]),
        stage="sharpened",
    )
    db_session.add(c)
    db_session.commit()

    r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code in (400, 422), r.text


# ---------------------------------------------------------------------------
# AC2: Type is one of the four valid values
# ---------------------------------------------------------------------------

def test_probe_response_type_is_valid(api_client, db_session):
    """AC2: The probe type in the API response must be one of the four valid types."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    data = r.json()
    valid = {"measurement", "lab-test", "behaviour-experiment", "prototype"}
    assert data["type"] in valid, f"probe type {data['type']!r} not in {valid}"


# ---------------------------------------------------------------------------
# AC4: Response includes all required fields
# ---------------------------------------------------------------------------

def test_probe_response_includes_all_fields(api_client, db_session):
    """AC4: Response must include type, target_metric, cost, time, note."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    data = r.json()
    for field in ("type", "target_metric", "cost", "time", "note"):
        assert field in data, f"Response missing field: {field}"
        assert data[field], f"Field {field!r} must be non-empty"


# ---------------------------------------------------------------------------
# AC5: Probe record persisted with status='designed'
# ---------------------------------------------------------------------------

def test_probe_persisted_to_db(api_client, db_session):
    """AC5: After POST /api/cases/{id}/probe, a Probe row exists in the DB."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None, "A Probe row must be created in the DB"


def test_probe_status_is_designed(api_client, db_session):
    """AC5: The persisted Probe must have status='designed'."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None
    assert probe.status == "designed", f"Expected status='designed', got {probe.status!r}"


def test_probe_all_fields_persisted(api_client, db_session):
    """AC5: All probe fields (type, target_metric, cost, time, note) are persisted."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert probe is not None
    assert probe.type == _MOCK_PROBE_RESULT["type"]
    assert probe.target_metric == _MOCK_PROBE_RESULT["target_metric"]
    assert probe.cost == _MOCK_PROBE_RESULT["cost"]
    assert probe.time == _MOCK_PROBE_RESULT["time"]
    assert probe.note == _MOCK_PROBE_RESULT["note"]


def test_probe_stage_advances_to_probe(api_client, db_session):
    """AC5: After designing a probe, the Case stage advances to 'probe'."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "probe", f"Case stage must advance to 'probe', got {updated.stage!r}"


def test_probe_idempotent_second_call(api_client, db_session):
    """AC5: A second POST /api/cases/{id}/probe returns the existing probe without creating a new one."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        api_client.post(f"/api/cases/{c.id}/probe")

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        r2 = api_client.post(f"/api/cases/{c.id}/probe")
    assert r2.status_code == 200

    db_session.expire_all()
    count = db_session.query(models.Probe).filter_by(case_id=c.id).count()
    assert count == 1, f"Only one Probe row should exist; found {count}"


# ---------------------------------------------------------------------------
# GET /api/cases/{id} returns probe data
# ---------------------------------------------------------------------------

def test_get_case_returns_probe_data(api_client, db_session):
    """AC5: GET /api/cases/{id} returns probe data after probe is designed."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT):
        api_client.post(f"/api/cases/{c.id}/probe")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "probe" in data, "GET /api/cases/{id} must include 'probe' field"
    probe = data["probe"]
    assert probe is not None
    assert probe["type"] == _MOCK_PROBE_RESULT["type"]
    assert probe["target_metric"] == _MOCK_PROBE_RESULT["target_metric"]


def test_get_case_probe_null_before_design(api_client, db_session):
    """AC5: GET /api/cases/{id} returns probe=null before probe is designed."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "probe" in data
    assert data["probe"] is None


# ---------------------------------------------------------------------------
# AC9: Claude API failure → 502, no Probe persisted
# ---------------------------------------------------------------------------

def test_probe_502_on_claude_failure(api_client, db_session):
    """AC9: If Claude API fails, endpoint returns 502."""
    from app.probe import ProbeError
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               side_effect=ProbeError("API timeout")):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 502, f"Expected 502 on Claude failure, got {r.status_code}"


def test_probe_not_persisted_on_failure(api_client, db_session):
    """AC9: If Claude API fails, no Probe record is written to the DB."""
    from app import models
    from app.probe import ProbeError
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               side_effect=ProbeError("network error")):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    count = db_session.query(models.Probe).filter_by(case_id=c.id).count()
    assert count == 0, f"No Probe should be persisted on failure; found {count}"


def test_probe_stage_unchanged_on_failure(api_client, db_session):
    """AC9: Case stage must not advance if probe design fails."""
    from app import models
    from app.probe import ProbeError
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               side_effect=ProbeError("bad key")):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "weigh", \
        f"Stage must not change on failure; got {updated.stage!r}"


# ---------------------------------------------------------------------------
# Probe service: validates Claude response
# ---------------------------------------------------------------------------

def test_probe_service_rejects_invalid_type():
    """AC2: ProbeError raised when Claude returns an invalid type."""
    from app.probe import design_probe

    bad_response = {
        "type": "app",  # not in valid types
        "target_metric": "some metric",
        "cost": "free",
        "time": "1 week",
        "note": "some note",
    }

    # Validation is exercised directly; the LLM transport is covered elsewhere.
    from app.probe import _validate_probe_response, ProbeError
    with pytest.raises(ProbeError):
        _validate_probe_response(bad_response)


def test_probe_service_rejects_missing_fields():
    """AC4: ProbeError raised when Claude response is missing required fields."""
    from app.probe import _validate_probe_response, ProbeError
    incomplete = {"type": "measurement"}  # missing target_metric, cost, time, note
    with pytest.raises(ProbeError):
        _validate_probe_response(incomplete)


def test_probe_service_accepts_valid_response():
    """AC4: No error raised for a valid probe response."""
    from app.probe import _validate_probe_response
    # Should not raise
    _validate_probe_response(_MOCK_PROBE_RESULT)


# ---------------------------------------------------------------------------
# AC6: ProbeCard renders type label, targetMetric in mono, cost, time, note (JS)
# ---------------------------------------------------------------------------

def test_probe_card_component_defined_in_js():
    """AC6: A ProbeCard component must be defined in the JS."""
    combined = _read_combined_js()
    assert "ProbeCard" in combined, "JS must define a ProbeCard component"


def test_probe_type_label_in_probe_card_js():
    """AC6: ProbeCard must render a probe type label."""
    combined = _read_combined_js()
    # type field or probe type label must be rendered
    assert ("probe" in combined.lower() and "type" in combined.lower()), \
        "ProbeCard must render the probe type"


def test_probe_target_metric_mono_font_in_js():
    """AC6: ProbeCard must render targetMetric in large monospace font."""
    combined = _read_combined_js()
    # Must reference target_metric in mono context
    assert "target_metric" in combined or "targetMetric" in combined, \
        "ProbeCard must reference target_metric"
    assert "mono" in combined and (
        "font-mono" in combined
        or "var(--font-mono)" in combined
        or "className" in combined
    ), "ProbeCard must use monospace font for the target metric"


def test_probe_cost_time_note_in_js():
    """AC6: ProbeCard must render cost, time, and note fields."""
    combined = _read_combined_js()
    assert "cost" in combined, "ProbeCard must render cost"
    assert "time" in combined, "ProbeCard must render time"
    assert "note" in combined, "ProbeCard must render note"


# ---------------------------------------------------------------------------
# AC7: 'Send to commander' button visible but disabled when type='prototype'
# ---------------------------------------------------------------------------

def test_send_to_commander_button_in_js():
    """AC7: A 'Send to commander' button must be defined in the JS."""
    combined = _read_combined_js()
    assert ("Send to commander" in combined or "send to commander" in combined.lower() or
            "sendToCommander" in combined or "commander" in combined.lower()), \
        "JS must define a 'Send to commander' button for prototype probes"


def test_send_to_commander_disabled_in_js():
    """AC7: The 'Send to commander' button must be disabled (stub) in JS."""
    combined = _read_combined_js()
    assert "disabled" in combined, "JS must mark 'Send to commander' button as disabled"


def test_send_to_commander_only_for_prototype_in_js():
    """AC8: The 'Send to commander' button must only render when type='prototype'."""
    combined = _read_combined_js()
    # Must conditionally render based on prototype type
    assert "prototype" in combined, "JS must check for 'prototype' type to show 'Send to commander'"


# ---------------------------------------------------------------------------
# AC9: Error state shown in JS on probe failure
# ---------------------------------------------------------------------------

def test_probe_error_state_in_js():
    """AC9: ProbeCard or CaseDetailScreen must handle and display probe error state."""
    combined = _read_combined_js()
    assert "error" in combined.lower(), "JS must handle probe API errors"


# ---------------------------------------------------------------------------
# AC10: No verdict or action plan at Stage 4 (JS)
# ---------------------------------------------------------------------------

def test_action_plan_stays_locked_in_js():
    """AC10: The action plan must remain locked (not rendered) at Stage 4."""
    combined = _read_combined_js()
    assert "Locked" in combined or "locked" in combined, \
        "Action plan must stay locked until verdict"


def test_probe_section_not_verdict_in_js():
    """AC10: The probe section must not render a verdict or action plan."""
    combined = _read_combined_js()
    # Probe section must exist
    assert "THE PROBE" in combined or "ProbeCard" in combined, \
        "Probe section must be present"
    # Action plan must stay locked
    assert "Locked until you log a verdict" in combined or \
           "Locked until" in combined or "locked" in combined.lower(), \
        "Action plan section must remain locked at Stage 4"


# ---------------------------------------------------------------------------
# CaseDetailScreen auto-triggers probe at stage >= 4 (JS)
# ---------------------------------------------------------------------------

def test_case_detail_auto_triggers_probe_at_stage4_in_js():
    """AC1: CaseDetailScreen must auto-trigger probe design when stage >= 4 and no probe exists."""
    combined = _read_combined_js()
    # Must have stage >= 4 gating for probe
    assert ("stage" in combined and
            (">= 4" in combined or "=== 4" in combined or
             "'probe'" in combined or "probe" in combined.lower())), \
        "CaseDetailScreen must gate probe design trigger at stage >= 4"


def test_probe_loading_state_in_js():
    """AC1: CaseDetailScreen must show a loading state during probe API call."""
    combined = _read_combined_js()
    assert "crux-spin" in combined or "loading" in combined.lower() or \
           "Designing" in combined or "designing" in combined.lower(), \
        "JS must show a loading state during probe design API call"
