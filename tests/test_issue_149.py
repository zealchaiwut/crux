"""Tests for issue #149: Display steps, duration, and decision_rule in ProbeCard.

AC coverage:
  AC1 – ProbeCard renders a `steps` section beneath the existing type / target_metric / cost / time fields.
  AC2 – ProbeCard renders `duration` beneath `steps`.
  AC3 – ProbeCard renders `decision_rule` beneath `duration`.
  AC4 – All three new fields are grouped under a visible label reading "run this outside crux".
  AC5 – If any of the three fields is absent from the API response, that field is omitted
        gracefully (no blank rows, no JS errors).
  AC6 – Layout and typography match the patterns defined in DESIGN.md (design tokens used).
  AC7 – No regressions to the existing type, target_metric, cost, or time display.
"""
import json
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _read_combined_js():
    return "".join(
        (JS_DIR / f).read_text()
        for f in sorted(JS_DIR.iterdir())
        if f.suffix == ".js"
    )


def _probe_card_block(combined):
    """Return the source text of the ProbeCard function."""
    idx = combined.find("function ProbeCard")
    assert idx != -1, "ProbeCard must be defined in cases.js"
    # grab from definition to the next top-level function
    next_func = combined.find("\nfunction ", idx + 1)
    return combined[idx:next_func] if next_func != -1 else combined[idx:]


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


def _seed_case_with_probe(session, steps=None, duration=None, decision_rule=None):
    from app import models
    from datetime import datetime, timezone

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is churn increasing?",
        sharpened="Churn rose 15% after pricing change.",
        not_investigating=json.dumps([]),
        stage="probe",
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Pricing sensitivity",
        mechanism="New tier alienates budget customers.",
        prior="0.70",
        current_rank=1,
    )
    session.add(plan)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="churn rate by cohort",
        cost="~£0",
        time="2 weeks",
        status="designed",
        steps=steps,
        duration=duration,
        decision_rule=decision_rule,
    )
    session.add(probe)
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: ProbeCard renders `steps` — verified via JS source position
# ---------------------------------------------------------------------------

def test_probe_card_renders_steps_field():
    """AC1: ProbeCard source must reference probe.steps for rendering."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.steps" in block, (
        "ProbeCard must reference probe.steps to render the steps list (AC1)"
    )


def test_steps_rendered_after_existing_fields():
    """AC1: steps section must appear after type/target_metric/cost/time in source order."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    # type is shown as a badge early; probe.time is the last of the original fields
    time_pos = block.find("probe.time")
    steps_pos = block.find("probe.steps")
    assert time_pos != -1, "probe.time must be rendered in ProbeCard"
    assert steps_pos != -1, "probe.steps must be rendered in ProbeCard"
    assert steps_pos > time_pos, (
        "probe.steps section must appear after probe.time in source order (AC1)"
    )


def test_api_returns_steps_field(api_client, db_session):
    """AC1: GET /api/cases/{id} includes a steps list for the attached probe."""
    steps = ["Step one: recruit participants.", "Step two: run sessions.", "Step three: analyse results."]
    c = _seed_case_with_probe(db_session, steps=steps, duration="2 weeks", decision_rule="If >60% pass → proceed.")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json().get("probe")
    assert probe_data is not None, "API must return a probe object (AC1)"
    assert "steps" in probe_data, "probe response must include 'steps' field (AC1)"
    assert probe_data["steps"] == steps, "steps must match what was stored (AC1)"


# ---------------------------------------------------------------------------
# AC2: ProbeCard renders `duration` beneath `steps`
# ---------------------------------------------------------------------------

def test_probe_card_renders_duration_field():
    """AC2: ProbeCard source must reference probe.duration."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.duration" in block, (
        "ProbeCard must reference probe.duration (AC2)"
    )


def test_duration_rendered_after_steps():
    """AC2: duration must appear after steps in source order."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    steps_pos = block.find("probe.steps")
    duration_pos = block.find("probe.duration")
    assert steps_pos != -1, "probe.steps must be in ProbeCard"
    assert duration_pos != -1, "probe.duration must be in ProbeCard"
    assert duration_pos > steps_pos, (
        "probe.duration section must appear after probe.steps in source order (AC2)"
    )


def test_api_returns_duration_field(api_client, db_session):
    """AC2: GET /api/cases/{id} includes duration in the probe object."""
    c = _seed_case_with_probe(
        db_session,
        steps=["Do the thing."],
        duration="14 days",
        decision_rule="If retention > 80% → proceed.",
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    assert probe_data.get("duration") == "14 days", (
        "API must return the stored duration value (AC2)"
    )


# ---------------------------------------------------------------------------
# AC3: ProbeCard renders `decision_rule` beneath `duration`
# ---------------------------------------------------------------------------

def test_probe_card_renders_decision_rule_field():
    """AC3: ProbeCard source must reference probe.decision_rule."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.decision_rule" in block, (
        "ProbeCard must reference probe.decision_rule (AC3)"
    )


def test_decision_rule_rendered_after_duration():
    """AC3: decision_rule must appear after duration in source order."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    duration_pos = block.find("probe.duration")
    decision_rule_pos = block.find("probe.decision_rule")
    assert duration_pos != -1, "probe.duration must be in ProbeCard"
    assert decision_rule_pos != -1, "probe.decision_rule must be in ProbeCard"
    assert decision_rule_pos > duration_pos, (
        "probe.decision_rule section must appear after probe.duration in source order (AC3)"
    )


def test_api_returns_decision_rule_field(api_client, db_session):
    """AC3: GET /api/cases/{id} includes decision_rule in the probe object."""
    rule = "If churn < 5% → proceed with Plan A; if churn ≥ 5% → discard."
    c = _seed_case_with_probe(
        db_session,
        steps=["Measure churn."],
        duration="30 days",
        decision_rule=rule,
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    assert probe_data.get("decision_rule") == rule, (
        "API must return the stored decision_rule value (AC3)"
    )


# ---------------------------------------------------------------------------
# AC4: All three fields grouped under "run this outside crux" label
# ---------------------------------------------------------------------------

def test_run_this_outside_crux_label_in_probe_card():
    """AC4: ProbeCard must include the label 'run this outside crux'."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "run this outside crux" in block, (
        "ProbeCard must contain the label 'run this outside crux' (AC4)"
    )


def test_steps_duration_decision_rule_all_within_group():
    """AC4: steps, duration, and decision_rule must all appear after the group label in source order."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    label_pos = block.find("run this outside crux")
    steps_pos = block.find("probe.steps")
    duration_pos = block.find("probe.duration")
    decision_rule_pos = block.find("probe.decision_rule")
    assert label_pos != -1, "'run this outside crux' label must exist in ProbeCard (AC4)"
    assert steps_pos > label_pos, "probe.steps must appear after the group label (AC4)"
    assert duration_pos > label_pos, "probe.duration must appear after the group label (AC4)"
    assert decision_rule_pos > label_pos, "probe.decision_rule must appear after the group label (AC4)"


# ---------------------------------------------------------------------------
# AC5: Missing fields omitted gracefully — conditional rendering
# ---------------------------------------------------------------------------

def test_probe_card_conditionally_renders_steps():
    """AC5: steps section must be wrapped in a conditional guard in ProbeCard."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    # The inner render guard: {probe.steps && probe.steps.length > 0 && (
    assert "probe.steps.length" in block, (
        "ProbeCard must guard the steps list with a probe.steps.length check so "
        "the section is omitted when steps is empty (AC5)"
    )


def test_probe_card_conditionally_renders_duration():
    """AC5: duration must be wrapped in a conditional guard in ProbeCard."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    duration_idx = block.find("probe.duration")
    assert duration_idx != -1
    context_before = block[max(0, duration_idx - 100): duration_idx]
    assert "&&" in context_before or "{probe.duration" in block[duration_idx - 5: duration_idx + 20], (
        "probe.duration must be conditionally rendered (AC5)"
    )


def test_probe_card_conditionally_renders_decision_rule():
    """AC5: decision_rule must be wrapped in a conditional guard in ProbeCard."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    rule_idx = block.find("probe.decision_rule")
    assert rule_idx != -1
    context_before = block[max(0, rule_idx - 100): rule_idx]
    assert "&&" in context_before or "{probe.decision_rule" in block[rule_idx - 5: rule_idx + 20], (
        "probe.decision_rule must be conditionally rendered (AC5)"
    )


def test_api_handles_missing_steps_gracefully(api_client, db_session):
    """AC5: When steps is null, API returns an empty list (not null) for steps."""
    c = _seed_case_with_probe(db_session, steps=None, duration="1 week", decision_rule="If yes → proceed.")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    assert "steps" in probe_data, "steps field must always be present in API response (AC5)"
    assert isinstance(probe_data["steps"], list), "steps must be a list even when null in DB (AC5)"


def test_api_handles_missing_duration_gracefully(api_client, db_session):
    """AC5: When duration is null, API returns empty string (not null)."""
    c = _seed_case_with_probe(
        db_session,
        steps=["Do the thing."],
        duration=None,
        decision_rule="If yes → proceed.",
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    assert "duration" in probe_data, "duration field must always be present in API response (AC5)"
    # null duration comes back as empty string per router coercion
    assert probe_data["duration"] == "" or probe_data["duration"] is None, (
        "duration must be empty string or null when not set (AC5)"
    )


def test_api_handles_missing_decision_rule_gracefully(api_client, db_session):
    """AC5: When decision_rule is null, API returns empty string (not null)."""
    c = _seed_case_with_probe(
        db_session,
        steps=["Do the thing."],
        duration="1 week",
        decision_rule=None,
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    assert "decision_rule" in probe_data, "decision_rule field must always be present in API response (AC5)"
    assert probe_data["decision_rule"] == "" or probe_data["decision_rule"] is None, (
        "decision_rule must be empty string or null when not set (AC5)"
    )


# ---------------------------------------------------------------------------
# AC6: Design tokens used — no hard-coded colour or font-size values
# ---------------------------------------------------------------------------

def test_probe_card_steps_uses_design_tokens():
    """AC6: The steps list items must use design tokens (--text-sm, --text-muted) not raw values."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    # The inner render block starts at probe.steps.map — find it after the .length guard
    map_idx = block.find("probe.steps.map")
    assert map_idx != -1, "probe.steps.map must exist (steps rendered via map)"
    # Design tokens should be in the <li> style within ~400 chars of the .map call
    map_section = block[map_idx: map_idx + 400]
    assert "var(--text" in map_section or "var(--space" in map_section, (
        "steps list items must use design tokens (var(--text-*, var(--space-*) (AC6)"
    )


def test_probe_card_duration_uses_design_tokens():
    """AC6: duration display must use design tokens."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    # The inner duration value is after the {probe.duration && ( guard — find the second occurrence
    first_duration = block.find("probe.duration")
    second_duration = block.find("probe.duration", first_duration + 1)
    assert second_duration != -1, "probe.duration must appear at least twice (guard + render)"
    duration_section = block[second_duration: second_duration + 500]
    assert "var(--text" in duration_section or "var(--space" in duration_section, (
        "duration section must use design tokens (AC6)"
    )


def test_probe_card_decision_rule_uses_design_tokens():
    """AC6: decision_rule display must use design tokens."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    rule_start = block.find("probe.decision_rule")
    rule_section = block[rule_start:rule_start + 600]
    assert "var(--text" in rule_section or "var(--space" in rule_section, (
        "decision_rule section must use design tokens (AC6)"
    )


# ---------------------------------------------------------------------------
# AC7: No regressions to existing fields
# ---------------------------------------------------------------------------

def test_probe_card_still_renders_type():
    """AC7: ProbeCard must still render probe.type (via TYPE_LABELS)."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.type" in block, "ProbeCard must still render probe.type (AC7)"


def test_probe_card_still_renders_target_metric():
    """AC7: ProbeCard must still render probe.target_metric."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.target_metric" in block, (
        "ProbeCard must still render probe.target_metric (AC7)"
    )


def test_probe_card_still_renders_cost():
    """AC7: ProbeCard must still render probe.cost."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.cost" in block, "ProbeCard must still render probe.cost (AC7)"


def test_probe_card_still_renders_time():
    """AC7: ProbeCard must still render probe.time."""
    combined = _read_combined_js()
    block = _probe_card_block(combined)
    assert "probe.time" in block, "ProbeCard must still render probe.time (AC7)"


def test_api_probe_includes_all_legacy_fields(api_client, db_session):
    """AC7: GET /api/cases/{id} probe object must include type, target_metric, cost, time."""
    c = _seed_case_with_probe(
        db_session,
        steps=["Step 1."],
        duration="1 week",
        decision_rule="If X → proceed.",
    )
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    probe_data = r.json()["probe"]
    for field in ("type", "target_metric", "cost", "time"):
        assert field in probe_data, f"probe response must include '{field}' field (AC7)"
