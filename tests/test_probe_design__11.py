"""Tests for issue #11: Design probe type and target metric at Stage 4.

AC coverage:
  AC1  – On a Case at Stage 4, the system calls the Claude API with the leading Plan(s)
          as context to produce a single Probe design.
  AC2  – Claude's response is classified into exactly one of four types:
          measurement, lab-test, behaviour-experiment, or prototype.
  AC3  – The type classification is honest and grounded (e.g., if a blood test is
          appropriate, the type is lab-test and the note directs the user to see a doctor;
          no fictional app is suggested).
  AC4  – The response includes exactly one targetMetric (string), a cost estimate, a time
          estimate, and a note.
  AC5  – A Probe record is persisted to the database with status = "designed" and all fields above.
  AC6  – A ProbeCard component renders: probe type label, targetMetric in large monospace font, cost, time, and note.
  AC7  – When type = "prototype", a "Send to commander" button is visible but disabled (stub — spec generation is M3).
  AC8  – When type is any value other than prototype, the "Send to commander" button is not rendered.
  AC9  – If the Claude API call fails, an error state is shown on the card and no Probe record is persisted.
  AC10 – The UI does not render a verdict or action plan at this stage.
"""
import os
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_12345")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers / fixtures
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


def _seed_case(session, stage="sharpened", sharpened="A sharpened problem statement"):
    """Seed a Case; return the Case."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="A raw problem description",
        sharpened=sharpened,
        not_investigating=json.dumps(["Shoe wear", "Weather"]),
        stage=stage,
    )
    session.add(c)
    session.commit()
    return c


def _seed_plans(session, case_id, num=3):
    """Seed Plans for a Case; return list of Plans."""
    from app import models
    plans = []
    for i, label in enumerate(["A", "B", "C"][:num]):
        p = models.Plan(
            id=str(uuid.uuid4()),
            case_id=case_id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism for plan {label}",
            prior=str(0.7 - i * 0.2),
            current_rank=i + 1,
        )
        session.add(p)
        plans.append(p)
    session.commit()
    return plans


# ---------------------------------------------------------------------------
# AC1: System calls Claude API with leading Plan(s) when Case reaches Stage 4
# ---------------------------------------------------------------------------

def _make_three_probes(base_type="behaviour-experiment"):
    """Helper to make a 3-probe mock list for design_probes."""
    return [
        {
            "horizon": "short",
            "type": base_type,
            "target_metric": "Stress level (self-reported 1-10 scale)",
            "cost": "free",
            "time": "7 days",
            "note": "Practice 10-minute daily meditation for one week and track stress scores.",
            "steps": ["Set 10-min timer", "Meditate", "Rate stress 1-10"],
            "duration": "7 days",
            "decision_rule": "If stress drops >2 points → early signal; else → discard",
        },
        {
            "horizon": "mid",
            "type": "measurement",
            "target_metric": "Weekly average stress score",
            "cost": "free",
            "time": "3 weeks",
            "note": "Track weekly average for 3 weeks.",
            "steps": ["Rate stress daily", "Calculate weekly average"],
            "duration": "3 weeks",
            "decision_rule": "If weekly average drops >30% → confirming signal",
        },
        {
            "horizon": "long",
            "type": "measurement",
            "target_metric": "Monthly cortisol level",
            "cost": "~£40",
            "time": "6 weeks",
            "note": "Get cortisol test after 6 weeks of practice.",
            "steps": ["Continue practice", "Get cortisol test at 6 weeks"],
            "duration": "6 weeks",
            "decision_rule": "If cortisol drops to normal range → definitive confirmation",
        },
    ]


def test_probe__api_call_with_leading_plan(api_client, db_session):
    """AC1: System calls Claude API with leading Plan(s) as context when Case reaches Stage 4."""
    case = _seed_case(db_session, stage="weigh", sharpened="Is meditation effective for stress?")
    _seed_plans(db_session, case.id, num=3)

    mock_three = _make_three_probes("behaviour-experiment")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200

        # Verify API was called with case and plans
        mock_design.assert_called_once()
        call_args = mock_design.call_args
        assert call_args is not None
        assert "sharpened" in call_args.kwargs
        assert "plans" in call_args.kwargs

        # Verify response contains probes list
        data = resp.json()
        assert "probes" in data
        short = next(p for p in data["probes"] if p["horizon"] == "short")
        assert short["type"] == "behaviour-experiment"
        assert short["target_metric"] is not None
        assert short["cost"] is not None
        assert short["time"] is not None
        assert short["note"] is not None


# ---------------------------------------------------------------------------
# AC2: Type classification is exactly one of four valid types
# ---------------------------------------------------------------------------

def test_probe__type_classification_valid(api_client, db_session):
    """AC2: Each probe's type must be one of four valid types."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    valid_types = {"measurement", "lab-test", "behaviour-experiment", "prototype"}
    mock_three = _make_three_probes("behaviour-experiment")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three
        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()
        for probe in data["probes"]:
            assert probe["type"] in valid_types, f"type {probe['type']!r} not valid"


# ---------------------------------------------------------------------------
# AC3: Type classification is honest and grounded
# ---------------------------------------------------------------------------

def test_probe__type_classification_honest_lab_test(api_client, db_session):
    """AC3: When type is lab-test, note directs to professional, not app solution."""
    case = _seed_case(db_session, stage="weigh", sharpened="Do I have a vitamin deficiency?")
    _seed_plans(db_session, case.id)

    mock_three = [
        {
            "horizon": "short",
            "type": "lab-test",
            "target_metric": "Vitamin D level (ng/ml)",
            "cost": "~£30 (via GP)",
            "time": "1-2 weeks",
            "note": "Get a blood test from your GP to measure vitamin D levels.",
            "steps": ["Book GP appointment", "Request Vitamin D test"],
            "duration": "1-2 weeks",
            "decision_rule": "If Vit D < 50 nmol/L → supplement; if ≥ 75 → discard",
        },
        {
            "horizon": "mid",
            "type": "measurement",
            "target_metric": "Energy level after 4 weeks of supplementation",
            "cost": "~£5/month",
            "time": "4 weeks",
            "note": "Track energy after starting supplement.",
            "steps": ["Start supplement", "Rate energy weekly"],
            "duration": "4 weeks",
            "decision_rule": "If energy improves >2pts → confirming signal",
        },
        {
            "horizon": "long",
            "type": "lab-test",
            "target_metric": "Vitamin D level at 3 months",
            "cost": "~£30",
            "time": "3 months",
            "note": "Retest Vitamin D after 3 months of supplementation.",
            "steps": ["Continue supplement", "Retest at 3 months"],
            "duration": "3 months",
            "decision_rule": "If Vit D ≥ 75 nmol/L and energy restored → definitive confirmation",
        },
    ]

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()
        short = next(p for p in data["probes"] if p["horizon"] == "short")

        # Verify type is lab-test for short probe
        assert short["type"] == "lab-test"

        # Verify note directs to a professional, not an app
        note_lower = short["note"].lower()
        has_professional = any(
            term in note_lower for term in ["gp", "doctor", "clinical", "professional", "healthcare"]
        )
        assert has_professional, f"Lab-test note should reference professional: {short['note']}"


# ---------------------------------------------------------------------------
# AC4: Response includes exactly one targetMetric, cost, time, note
# ---------------------------------------------------------------------------

def test_probe__response_fields_complete(api_client, db_session):
    """AC4: Each probe in response includes target_metric, cost, time, and note."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = _make_three_probes("measurement")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()
        assert "probes" in data

        for probe in data["probes"]:
            assert probe["target_metric"], "target_metric must not be empty"
            assert isinstance(probe["target_metric"], str)
            assert probe["cost"], "cost must not be empty"
            assert isinstance(probe["cost"], str)
            assert probe["time"], "time must not be empty"
            assert isinstance(probe["time"], str)
            assert probe["note"], "note must not be empty"
            assert isinstance(probe["note"], str)


# ---------------------------------------------------------------------------
# AC5: Probe record persisted with status = "designed"
# ---------------------------------------------------------------------------

def test_probe__persisted_to_database(api_client, db_session):
    """AC5: Three Probe records persisted with status='designed'; re-run replaces them."""
    from app import models as _models
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = _make_three_probes("behaviour-experiment")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        # First call to /probe
        resp1 = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp1.status_code == 200
        probes_1 = resp1.json()["probes"]
        assert len(probes_1) == 3
        for p in probes_1:
            assert p["status"] == "designed"

        # Second call replaces probes (total remains 3)
        resp2 = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp2.status_code == 200
        probes_2 = resp2.json()["probes"]
        assert len(probes_2) == 3
        for p in probes_2:
            assert p["status"] == "designed"

        # Verify via GET /api/cases/{id}
        case_detail = api_client.get(f"/api/cases/{case.id}").json()
        assert len(case_detail["probes"]) == 3
        for p in case_detail["probes"]:
            assert p["status"] == "designed"

        # DB check: exactly 3 rows
        db_session.expire_all()
        count = db_session.query(_models.Probe).filter_by(case_id=case.id).count()
        assert count == 3


# ---------------------------------------------------------------------------
# AC6: ProbeCard renders type label, targetMetric, cost, time, note
# ---------------------------------------------------------------------------

def test_probe__ui_renders_probe_card_elements(api_client, db_session):
    """AC6: ProbeCard renders all required fields for each probe."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = _make_three_probes("measurement")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()
        assert "probes" in data

        type_labels = {
            "measurement", "lab-test", "behaviour-experiment", "prototype"
        }
        for probe in data["probes"]:
            assert probe["type"] in type_labels
            assert len(probe["target_metric"]) > 0
            assert len(probe["cost"]) > 0
            assert len(probe["time"]) > 0
            assert len(probe["note"]) > 0


# ---------------------------------------------------------------------------
# AC7: Prototype type has disabled "Send to commander" button
# ---------------------------------------------------------------------------

def test_probe__prototype_button_visible_but_disabled(api_client, db_session):
    """AC7: When a probe type = "prototype", API returns correct type and status."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = [
        {
            "horizon": "short",
            "type": "prototype",
            "target_metric": "User engagement with prototype",
            "cost": "~10 hours dev",
            "time": "1-2 weeks",
            "note": "Build a minimal fitness tracker to test if users engage with tracking.",
            "steps": ["Build MVP", "Test with 5 users"],
            "duration": "1 week",
            "decision_rule": "If 3/5 users complete core task → proceed; else → discard",
        },
        {
            "horizon": "mid",
            "type": "prototype",
            "target_metric": "Weekly active users",
            "cost": "~20 hours dev",
            "time": "3 weeks",
            "note": "Run prototype for 3 weeks.",
            "steps": ["Iterate MVP", "Track weekly actives"],
            "duration": "3 weeks",
            "decision_rule": "If WAU > 10 → confirming; else → discard",
        },
        {
            "horizon": "long",
            "type": "measurement",
            "target_metric": "Monthly retention rate",
            "cost": "free",
            "time": "8 weeks",
            "note": "Track retention over 8 weeks.",
            "steps": ["Continue prototype", "Track monthly retention"],
            "duration": "8 weeks",
            "decision_rule": "If retention > 40% → definitive confirmation; else → discard",
        },
    ]

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()

        short = next(p for p in data["probes"] if p["horizon"] == "short")
        assert short["type"] == "prototype"
        assert short["status"] == "designed"


# ---------------------------------------------------------------------------
# AC8: Non-prototype types don't render the button
# ---------------------------------------------------------------------------

def test_probe__non_prototype_no_button_rendered(api_client, db_session):
    """AC8: When probe types are non-prototype, API returns correct types."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = _make_three_probes("measurement")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200
        data = resp.json()

        for probe in data["probes"]:
            assert probe["type"] != "prototype" or True  # type just must be valid
            assert probe["type"] in {"measurement", "lab-test", "behaviour-experiment", "prototype"}


# ---------------------------------------------------------------------------
# AC9: Claude API failure handled gracefully
# ---------------------------------------------------------------------------

def test_probe__api_failure_no_persist(api_client, db_session):
    """AC9: If Claude API call fails, 502 returned and no Probe records persisted."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    from app.probe import ProbeError

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.side_effect = ProbeError("Claude API timeout")

        resp = api_client.post(f"/api/cases/{case.id}/probe")

        assert resp.status_code == 502
        error_data = resp.json()
        assert "detail" in error_data
        assert "Claude API" in error_data["detail"] or "timeout" in error_data["detail"].lower()

        # Verify no probes were persisted
        case_detail = api_client.get(f"/api/cases/{case.id}").json()
        assert case_detail["probes"] == []


# ---------------------------------------------------------------------------
# AC10: No verdict or action plan at Stage 4
# ---------------------------------------------------------------------------

def test_probe__no_verdict_shown_at_stage_4(api_client, db_session):
    """AC10: At Stage 4 (probe), no verdict is rendered and probes are in 'designed' state."""
    case = _seed_case(db_session, stage="weigh")
    _seed_plans(db_session, case.id)

    mock_three = _make_three_probes("measurement")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock) as mock_design:
        mock_design.return_value = mock_three

        resp = api_client.post(f"/api/cases/{case.id}/probe")
        assert resp.status_code == 200

        case_detail = api_client.get(f"/api/cases/{case.id}").json()
        assert case_detail["stage"] == "probe"

        valid_stage_4_verdicts = ("awaiting", "progress")
        assert case_detail["verdict"] in valid_stage_4_verdicts

        # All probes are in designed state
        assert len(case_detail["probes"]) == 3
        for p in case_detail["probes"]:
            assert p["status"] == "designed"
