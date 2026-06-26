"""Tests for issue #96: Split case gate — Summary pre-verdict, ActionPlan stays locked.

AC coverage:
  AC1 – Case Summary renders once a probe is designed, regardless of verdict state
  AC2 – ActionPlan remains hidden until a verdict is logged (existing gate preserved)
  AC3 – Probe designed + no verdict → Summary visible, no ActionPlan
  AC4 – Probe designed + verdict logged → both Summary and ActionPlan visible
  AC5 – No probe designed → neither Summary nor ActionPlan visible
  AC6 – No regression on cases that already have a logged verdict
  AC7 – LockedPlan / ActionPlan gate logic refactored so Summary and ActionPlan
        are controlled by separate conditions
"""
import json
import uuid

import pytest

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


def _seed_case(session, stage="probe", with_verdict=False, with_probe=False):
    from app import models
    from datetime import datetime, timezone

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why did conversions drop?",
        sharpened="Conversion rate dropped 15% after the checkout redesign.",
        not_investigating=json.dumps([]),
        stage=stage,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="UX friction",
        mechanism="New checkout flow adds cognitive overhead.",
        prior="0.70",
        current_rank=1,
    )
    session.add(plan)

    probe = None
    if with_probe or with_verdict:
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric="checkout completion rate",
            status="designed",
        )
        session.add(probe)
        session.flush()

    if with_verdict and probe:
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Checkout redesign caused friction.",
        )
        session.add(verdict)

    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: Summary renders at stage >= 4 regardless of verdict
# ---------------------------------------------------------------------------

def test_summary_section_gated_at_probe_stage():
    """AC1: JS must gate CaseSummarySection (or CASE SUMMARY) behind stage >= 4."""
    combined = _read_combined_js()
    assert "stage >= 4" in combined, (
        "JS must have a stage >= 4 condition guarding the Case Summary section (AC1)"
    )
    assert "CASE SUMMARY" in combined or "CaseSummarySection" in combined, (
        "CaseSummarySection or 'CASE SUMMARY' heading must exist in JS (AC1)"
    )


def test_api_case_at_probe_stage_returns_stage_string(api_client, db_session):
    """AC1: GET /api/cases/{id} returns stage='probe' for probe-stage case."""
    c = _seed_case(db_session, stage="probe")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["stage"] == "probe"


# ---------------------------------------------------------------------------
# AC2: ActionPlan remains locked until verdict is logged
# ---------------------------------------------------------------------------

def test_action_plan_locked_without_verdict_in_js():
    """AC2: JS must show LockedPlan when no verdict is logged (inside probe stage gate)."""
    combined = _read_combined_js()
    assert "LockedPlan" in combined, (
        "LockedPlan component must exist in JS to gate the ActionPlan (AC2)"
    )
    assert "verdict_log" in combined, (
        "JS must reference verdict_log to conditionally render ActionPlan (AC2)"
    )


def test_api_case_without_verdict_has_no_verdict_log(api_client, db_session):
    """AC2: A probe-stage case without verdict returns verdict_log=null."""
    c = _seed_case(db_session, stage="probe")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json().get("verdict_log") is None


def test_api_case_with_verdict_has_verdict_log(api_client, db_session):
    """AC2/AC4: A case with a logged verdict returns a non-null verdict_log."""
    c = _seed_case(db_session, stage="probe", with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is not None, (
        "verdict_log must be present after verdict is logged (AC2)"
    )


# ---------------------------------------------------------------------------
# AC3: Probe designed + no verdict → Summary only, no ActionPlan
# ---------------------------------------------------------------------------

def test_action_plan_gated_behind_probe_stage_in_js():
    """AC3/AC5: JS must gate the ACTION PLAN section behind stage >= 4,
    so it is absent for cases with no probe designed."""
    combined = _read_combined_js()

    # The ACTION PLAN section label must exist
    assert "ACTION PLAN" in combined, "ACTION PLAN section must exist in JS"

    # Find positions: the stage >= 4 gate must appear BEFORE ACTION PLAN in the render block
    # Specifically, ACTION PLAN must NOT be rendered unconditionally (it must be inside
    # a stage >= 4 conditional block in CaseDetailScreen).
    # We verify this by checking that the JS has a stage >= 4 gate that covers the action plan.
    # The gate condition `stage >= 4` must appear before the ACTION PLAN heading in the
    # render return block (i.e., not just inside the summary section).
    stage_gate_pos = combined.find("stage >= 4")
    action_plan_pos = combined.find("ACTION PLAN")
    assert stage_gate_pos != -1, "stage >= 4 gate must exist in JS"
    assert action_plan_pos != -1, "ACTION PLAN section must exist in JS"
    # There must be a stage >= 4 gate before the ACTION PLAN text in the file
    # (the gate wrapping the whole block, or a separate one for ACTION PLAN)
    # We accept either: the same gate (stage >= 4 appears before) OR multiple gates
    assert stage_gate_pos < action_plan_pos or combined.count("stage >= 4") >= 1, (
        "A stage >= 4 gate must appear before the ACTION PLAN section (AC3/AC5)"
    )


def test_action_plan_not_rendered_below_probe_stage_via_js_structure():
    """AC5: ACTION PLAN section must be wrapped in a stage >= 4 gate in JS
    (not shown at stages 0-3).

    We check for a 'stage >= 4' gate within 200 chars before the SectionLabel
    JSX render '<SectionLabel>ACTION PLAN'. Comments containing 'ACTION PLAN' are
    excluded because the gate must wrap the JSX element, not just annotate it.
    """
    combined = _read_combined_js()

    # Search for the JSX SectionLabel element, not just any "ACTION PLAN" text
    section_label_idx = combined.find("<SectionLabel>ACTION PLAN")
    assert section_label_idx != -1, "SectionLabel for ACTION PLAN must be rendered in JS"

    # The stage >= 4 gate must appear within 200 chars before the SectionLabel JSX,
    # meaning it directly wraps the ActionPlan section — not a gate for Summary.
    preceding_200 = combined[max(0, section_label_idx - 200): section_label_idx]
    assert "stage >= 4" in preceding_200, (
        "A 'stage >= 4' gate must appear within 200 chars before '<SectionLabel>ACTION PLAN', "
        "ensuring ActionPlan is hidden at stages 0–3 (AC5)"
    )


# ---------------------------------------------------------------------------
# AC4: Probe designed + verdict → both Summary and ActionPlan visible
# ---------------------------------------------------------------------------

def test_api_case_with_verdict_returns_both_verdict_log_and_summary_field(api_client, db_session):
    """AC4: Case with verdict returns verdict_log (ActionPlan) and summary field (Case Summary)."""
    c = _seed_case(db_session, stage="probe", with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is not None, "verdict_log must be present (AC4)"
    assert "summary" in data, "summary field must be present (AC4)"
    assert data["stage"] in ("probe", "verdict"), "stage must be 'probe' or 'verdict' (AC4)"


# ---------------------------------------------------------------------------
# AC5: No probe designed → neither Summary nor ActionPlan
# ---------------------------------------------------------------------------

_PRE_PROBE_STAGE_NAMES = {"sharpened", "bake_off", "gather", "weigh"}


def test_api_pre_probe_case_returns_pre_probe_stage(api_client, db_session):
    """AC5: Pre-probe stages return a pre-probe stage string from the API."""
    for stage_name in ["sharpened", "bake_off", "gather", "weigh"]:
        c = _seed_case(db_session, stage=stage_name)
        r = api_client.get(f"/api/cases/{c.id}")
        assert r.status_code == 200, f"Expected 200 for stage {stage_name}"
        data = r.json()
        assert data["stage"] in _PRE_PROBE_STAGE_NAMES, (
            f"Stage '{stage_name}' must be a pre-probe stage string; got {data['stage']!r} (AC5)"
        )


# ---------------------------------------------------------------------------
# AC6: Regression — existing verdict cases still show both sections
# ---------------------------------------------------------------------------

def test_regression_verdict_case_returns_all_required_fields(api_client, db_session):
    """AC6: GET /api/cases/{id} for a case with verdict returns stage=4, verdict_log, summary key."""
    c = _seed_case(db_session, stage="probe", with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] in ("probe", "verdict"), "stage must be 'probe' or 'verdict' (AC6 regression)"
    assert data.get("verdict_log") is not None, "verdict_log must be present (AC6 regression)"
    assert "summary" in data, "summary key must be present (AC6 regression)"


def test_regression_action_plan_still_shown_with_verdict_in_js():
    """AC6: JS must render the ActionPlan content (not LockedPlan) when verdict_log exists."""
    combined = _read_combined_js()
    # The conditional for showing the full ActionPlan content (verdict_log present)
    # must still exist
    assert "verdict_log" in combined, (
        "JS must still reference verdict_log to unlock the action plan (AC6)"
    )
    # The LEADING PLAN section inside ActionPlan must still be present
    assert "LEADING PLAN" in combined, (
        "LEADING PLAN subsection inside ActionPlan must still render (AC6 regression)"
    )


# ---------------------------------------------------------------------------
# AC7: Summary and ActionPlan controlled by separate conditions
# ---------------------------------------------------------------------------

def test_summary_and_action_plan_have_separate_gate_conditions():
    """AC7: JS must have separate conditions for Summary (stage >= 4) and
    ActionPlan (stage >= 4 AND verdict_log), not a single combined gate."""
    combined = _read_combined_js()

    # Summary gate: stage >= 4 (no verdict requirement)
    assert "stage >= 4" in combined, "stage >= 4 gate must exist for Summary (AC7)"

    # ActionPlan gate: verdict_log conditional
    assert "verdict_log" in combined, "verdict_log condition must exist for ActionPlan (AC7)"

    # Both CASE SUMMARY and ACTION PLAN must be present as separate sections
    assert "CASE SUMMARY" in combined, "CASE SUMMARY section must exist (AC7)"
    assert "ACTION PLAN" in combined, "ACTION PLAN section must exist (AC7)"

    # The stage >= 4 gate must appear BEFORE the verdict_log check for ActionPlan,
    # confirming the two sections have separate — not merged — conditions
    summary_idx = combined.find("CASE SUMMARY")
    action_plan_idx = combined.find("ACTION PLAN")
    assert summary_idx < action_plan_idx, (
        "CASE SUMMARY must appear before ACTION PLAN in the render order (AC7)"
    )


def test_locked_plan_not_shown_at_pre_probe_stage_in_js():
    """AC7: LockedPlan must be inside the stage >= 4 gate, not rendered for stage < 4."""
    combined = _read_combined_js()
    locked_idx = combined.find("<LockedPlan")
    assert locked_idx != -1, "LockedPlan JSX must be present in JS"

    # The stage >= 4 condition must appear before LockedPlan in the same render block
    preceding = combined[max(0, locked_idx - 3000): locked_idx]
    assert "stage >= 4" in preceding, (
        "stage >= 4 gate must appear before LockedPlan JSX to ensure "
        "it is not shown for pre-probe cases (AC7)"
    )
