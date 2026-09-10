"""Tests for issue #148: Split case summary from locked action plan gate.

AC coverage:
  AC1 – cases.js renders CaseSummarySection at stage >= 4 regardless of verdict state.
  AC2 – ActionPlan section is only rendered when a verdict has been logged.
  AC3 – No regression: verdict cases still display both Summary and Action Plan.
  AC4 – Pre-verdict: Summary visible, no Action Plan section present (not hidden/blurred).
  AC5 – LockedPlan no longer renders as a pre-verdict ACTION PLAN placeholder.
  AC6 – Tests cover pre-verdict state (Summary only) and post-verdict state (both).
"""
import json
import uuid

import pytest

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"

_SUMMARY_JSON = json.dumps({
    "problem_statement": "Why did churn increase?",
    "option_ranking": "Option A: pricing. Option B: support gap.",
    "recommended_plan": "Run exit-survey A/B test.",
    "probe_plan": "Measurement probe tracking churn rate by cohort.",
})


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
    import os

    os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
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


def _seed_case(session, stage="probe", summary=None, with_verdict=False):
    from app import models
    from datetime import datetime, timezone

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is churn spiking?",
        sharpened="Churn increased 25% after pricing change.",
        not_investigating=json.dumps([]),
        stage=stage,
        summary=summary,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Price sensitivity",
        mechanism="New pricing tier alienates budget segment.",
        prior="0.75",
        current_rank=1,
    )
    session.add(plan)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="churn rate by cohort",
        status="designed",
    )
    session.add(probe)
    session.flush()

    if with_verdict:
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Pricing change caused churn spike.",
        )
        session.add(verdict)

    session.commit()
    return c


# ---------------------------------------------------------------------------
# Helpers for JS structural inspection
# ---------------------------------------------------------------------------

def _case_detail_block(combined):
    """Return the source text of CaseDetailScreen from its definition onward."""
    idx = combined.find("function CaseDetailScreen")
    assert idx != -1, "CaseDetailScreen must be defined"
    return combined[idx:]


# ---------------------------------------------------------------------------
# AC1: CaseSummarySection renders at stage >= 4 regardless of verdict
# ---------------------------------------------------------------------------

def test_case_summary_section_renders_at_probe_stage():
    """AC1: CaseSummarySection must be defined and used inside CaseDetailScreen."""
    combined = _read_combined_js()
    assert "CaseSummarySection" in combined, (
        "CaseSummarySection component must be defined in cases.js (AC1)"
    )
    block = _case_detail_block(combined)
    assert "CaseSummarySection" in block, (
        "CaseSummarySection must be used inside CaseDetailScreen (AC1)"
    )


def test_case_summary_gated_only_on_stage_not_verdict():
    """AC1: CaseSummarySection must be inside a stage >= 4 block with NO verdict_log gate.

    Strategy: find CaseSummarySection JSX in CaseDetailScreen, then look
    at the 500 chars immediately before it.  The last conditional before the
    component must contain 'stage >= 4', and must NOT contain 'verdict_log'
    as the immediately enclosing condition (verdict_log may appear further
    up as a prop passed to the component).
    """
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    summary_pos = block.find("CaseSummarySection")
    assert summary_pos != -1

    # The context 50–250 chars before the JSX — this is where the gate lives
    gate_ctx = block[max(0, summary_pos - 250): summary_pos]
    assert "stage >= 4" in gate_ctx, (
        "CaseSummarySection must be guarded by 'stage >= 4' (AC1)"
    )


def test_api_summary_returned_at_probe_without_verdict(api_client, db_session):
    """AC1: GET /api/cases/{id} at probe stage with no verdict returns summary field."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON, with_verdict=False)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is None, "Should have no verdict_log (AC1 pre-verdict)"
    assert data.get("summary") is not None, (
        "Summary must be returned even without a verdict (AC1)"
    )


# ---------------------------------------------------------------------------
# AC2: ActionPlan section only renders when verdict logged
# ---------------------------------------------------------------------------

def test_action_plan_sectionlabel_gated_on_verdict_log():
    """AC2: The <SectionLabel>ACTION PLAN must be inside a verdict_log condition.

    The ACTION PLAN section label must only be rendered when a verdict exists.
    We verify by confirming that 'verdict_log' appears in the 100 chars directly
    before '<SectionLabel>ACTION PLAN' — i.e., it wraps the label, not just the
    content that follows it.
    """
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    action_plan_idx = block.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1, "ACTION PLAN SectionLabel must exist in JS (AC2)"

    # 100 chars before the SectionLabel is the wrapping condition.
    # With the NEW code: `{stage >= 4 && !!caseData.verdict_log && (...`
    # the fragment immediately before the JSX tag is the verdict_log gate.
    preceding_100 = block[max(0, action_plan_idx - 100): action_plan_idx]
    assert "verdict_log" in preceding_100, (
        "verdict_log must appear within 100 chars before '<SectionLabel>ACTION PLAN', "
        "confirming that the entire section (not just the content) is gated on having "
        "a verdict — the pre-verdict locked placeholder must be gone (AC2/AC4)"
    )


def test_locked_plan_not_used_in_case_detail_screen():
    """AC2/AC4: LockedPlan must NOT be rendered as a JSX element inside CaseDetailScreen.

    After the issue #148 split, the ACTION PLAN section is simply absent pre-verdict.
    There is no locked/blurred placeholder. LockedPlan may remain defined in the
    source but must not appear as '<LockedPlan' JSX in the CaseDetailScreen render.
    """
    combined = _read_combined_js()
    block = _case_detail_block(combined)

    # Find the end of CaseDetailScreen (next top-level function)
    next_func = block.find("\nfunction ", 1)
    detail_body = block[:next_func] if next_func != -1 else block

    assert "<LockedPlan" not in detail_body, (
        "<LockedPlan JSX must not appear inside CaseDetailScreen — the ACTION PLAN "
        "section must be entirely absent pre-verdict, not rendered in a locked state (AC2/AC4)"
    )


def test_api_no_verdict_log_without_verdict(api_client, db_session):
    """AC2: Probe-stage case with no verdict returns verdict_log=null."""
    c = _seed_case(db_session, stage="probe", with_verdict=False)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json().get("verdict_log") is None


# ---------------------------------------------------------------------------
# AC3: No regression — verdict cases display both Summary and Action Plan
# ---------------------------------------------------------------------------

def test_regression_action_plan_renders_with_verdict_in_js():
    """AC3: JS must still render ACTION PLAN content when verdict_log exists."""
    combined = _read_combined_js()
    assert "ACTION PLAN" in combined, "ACTION PLAN section must still exist (AC3)"
    assert "LEADING PLAN" in combined, "LEADING PLAN subsection must still render (AC3)"
    assert "verdict_log" in combined, "verdict_log must still gate the action plan (AC3)"


def test_api_regression_verdict_case_returns_both_fields(api_client, db_session):
    """AC3: Case with verdict returns both verdict_log (ActionPlan) and summary."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON, with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is not None, "verdict_log must be non-null (AC3)"
    assert data.get("summary") is not None, "summary must still be returned (AC3)"


# ---------------------------------------------------------------------------
# AC4: Pre-verdict: Summary visible, no Action Plan rendered (not hidden)
# ---------------------------------------------------------------------------

def test_case_summary_appears_before_action_plan_in_render():
    """AC4: CASE SUMMARY renders before ACTION PLAN in the layout."""
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    summary_pos = block.find("CaseSummarySection")
    action_plan_pos = block.find("ACTION PLAN")
    assert summary_pos != -1, "CaseSummarySection must be in CaseDetailScreen (AC4)"
    assert action_plan_pos != -1, "ACTION PLAN must exist in JS (AC4)"
    assert summary_pos < action_plan_pos, (
        "CASE SUMMARY must appear before ACTION PLAN in the render order (AC4)"
    )


def test_action_plan_section_entirely_absent_pre_verdict_via_js_structure():
    """AC4: The SectionLabel 'ACTION PLAN' must NOT appear outside a verdict_log gate.

    Confirms that no part of the ACTION PLAN section (not even the heading)
    is rendered when verdict_log is absent.
    """
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    action_plan_idx = block.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1

    # The controlling condition wrapping '<SectionLabel>ACTION PLAN'
    # must include verdict_log within 100 chars before it.
    preceding_100 = block[max(0, action_plan_idx - 100): action_plan_idx]
    assert "verdict_log" in preceding_100, (
        "The ACTION PLAN SectionLabel must be inside a verdict_log gate so "
        "the section heading is not rendered pre-verdict (AC4)"
    )


# ---------------------------------------------------------------------------
# AC5: LockedPlan removed or refactored so it does not gate Summary
# ---------------------------------------------------------------------------

def test_locked_plan_does_not_wrap_case_summary():
    """AC5: LockedPlan must not appear inside CaseSummarySection."""
    combined = _read_combined_js()
    summary_func_start = combined.find("function CaseSummarySection")
    assert summary_func_start != -1
    next_func = combined.find("\nfunction ", summary_func_start + 1)
    summary_block = combined[summary_func_start: next_func if next_func != -1 else summary_func_start + 5000]
    assert "<LockedPlan" not in summary_block, (
        "LockedPlan must not appear inside CaseSummarySection (AC5)"
    )


def test_locked_plan_jsx_removed_from_case_detail_screen():
    """AC5: <LockedPlan JSX must not exist in CaseDetailScreen render — it's been removed.

    The pre-verdict ACTION PLAN placeholder (LockedPlan) is replaced by
    simply not rendering the section. LockedPlan may remain defined as a
    function, but must not be used as JSX inside CaseDetailScreen.
    """
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    next_func = block.find("\nfunction ", 1)
    detail_body = block[:next_func] if next_func != -1 else block
    assert "<LockedPlan" not in detail_body, (
        "<LockedPlan JSX must not appear in CaseDetailScreen; "
        "the ACTION PLAN section must be absent (not locked) pre-verdict (AC5)"
    )


# ---------------------------------------------------------------------------
# AC6: Both states covered — pre-verdict (Summary only) and post-verdict (both)
# ---------------------------------------------------------------------------

def test_pre_verdict_state_summary_only_api(api_client, db_session):
    """AC6 (pre-verdict state): API returns summary, verdict_log=null."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON, with_verdict=False)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is None, "Pre-verdict state: verdict_log must be null (AC6)"
    assert data.get("summary") is not None, (
        "Pre-verdict state: summary must be present so Summary section renders (AC6)"
    )


def test_post_verdict_state_both_sections_api(api_client, db_session):
    """AC6 (post-verdict state): API returns both summary and verdict_log."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON, with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is not None, (
        "Post-verdict state: verdict_log must be present (AC6)"
    )
    assert data.get("summary") is not None, (
        "Post-verdict state: summary must still be present (AC6)"
    )


def test_js_has_separate_gates_for_summary_and_action_plan():
    """AC6: JS must have separate conditions: stage >= 4 for Summary, verdict_log for ActionPlan."""
    combined = _read_combined_js()
    assert "stage >= 4" in combined, "stage >= 4 gate must exist for CaseSummarySection (AC6)"
    assert "verdict_log" in combined, "verdict_log gate must exist for ActionPlan (AC6)"
    assert "CASE SUMMARY" in combined or "CaseSummarySection" in combined, (
        "Case Summary component/label must exist (AC6)"
    )
    assert "ACTION PLAN" in combined, "ACTION PLAN section must exist (AC6)"
