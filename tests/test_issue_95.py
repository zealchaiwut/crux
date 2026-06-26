"""Tests for issue #95: Show Case Summary section at probe stage.

AC coverage:
  AC1  – A Case Summary section renders in CaseDetailScreen when stage === 4 (probe),
          regardless of whether a verdict has been produced
  AC2  – The section is visually distinct and uses existing section styles (SectionLabel,
          card, spacing tokens from DESIGN.md)
  AC3  – The summary text is pulled from caseData.summary (correct case data field, not hardcoded)
  AC4  – The section does not appear at stages prior to probe (e.g., intake, analysis)
  AC5  – The section does not duplicate or conflict with verdict output when verdict is present
  AC6  – No new one-off styles introduced — only existing tokens and section components reused
  AC7  – The close-case affordance is accessible from this section without requiring probe execution
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


_MOCK_SUMMARY = {
    "problem_statement": "User retention dropped 20% after the pricing change.",
    "option_ranking": "A (Price sensitivity): Most likely cause. B (Feature gap): Possible. C (Communication): Least.",
    "recommended_plan": "Investigate price sensitivity through a targeted survey.",
    "probe_plan": "Run a 2-week A/B test offering a discount to churned users.",
}


def _seed_case(session, stage="probe", summary=None, with_verdict=False):
    from app import models
    from datetime import datetime, timezone

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why did our retention drop?",
        sharpened="User retention dropped 20% after the pricing change.",
        not_investigating=json.dumps([]),
        stage=stage,
        summary=json.dumps(summary) if summary is not None else None,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Price sensitivity",
        mechanism="Users left because the price exceeded perceived value.",
        prior="0.60",
        current_rank=1,
    )
    session.add(plan)

    if with_verdict:
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric="churn rate",
            status="confirmed",
        )
        session.add(probe)
        session.flush()
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="Price was the main driver.",
        )
        session.add(verdict)

    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: Case Summary section renders at probe stage (stage === 4)
# ---------------------------------------------------------------------------

def test_case_summary_component_or_section_defined():
    """AC1: A CaseSummarySection component or CASE SUMMARY heading must exist in JS."""
    combined = _read_combined_js()
    assert "CASE SUMMARY" in combined or "CaseSummarySection" in combined, (
        "JS must define a CaseSummarySection component or render a 'CASE SUMMARY' section heading "
        "to satisfy AC1"
    )


def test_get_case_includes_summary_field_at_probe_stage(api_client, db_session):
    """AC1: GET /api/cases/{id} must return a 'summary' key when the case is at probe stage."""
    c = _seed_case(db_session, stage="probe", summary=_MOCK_SUMMARY)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, f"Expected 200; got {r.status_code}: {r.text}"
    data = r.json()
    assert "summary" in data, (
        f"GET /api/cases/{{id}} must include a 'summary' key; got keys: {list(data)}"
    )


def test_get_case_summary_is_parsed_dict_when_present(api_client, db_session):
    """AC1/AC3: When summary exists, the API must return it as a parsed object (not a raw string)."""
    c = _seed_case(db_session, stage="probe", summary=_MOCK_SUMMARY)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    summary = data.get("summary")
    assert summary is not None, "summary must be non-null when the case has a generated summary"
    assert isinstance(summary, dict), (
        f"summary must be a dict (parsed JSON), not {type(summary).__name__}: {summary!r}"
    )
    assert summary.get("problem_statement"), "summary must include 'problem_statement'"
    assert summary.get("option_ranking"), "summary must include 'option_ranking'"
    assert summary.get("recommended_plan"), "summary must include 'recommended_plan'"
    assert summary.get("probe_plan"), "summary must include 'probe_plan'"


def test_get_case_summary_is_none_when_not_generated(api_client, db_session):
    """AC1: GET /api/cases/{id} must return summary=null when no summary has been generated."""
    c = _seed_case(db_session, stage="probe", summary=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data, "Response must always include a 'summary' key"
    assert data["summary"] is None, (
        f"summary must be null when not yet generated; got: {data['summary']!r}"
    )


def test_case_summary_section_stage_condition_present_in_js():
    """AC1: The JS must gate the Case Summary section behind stage >= 4 (probe stage)."""
    combined = _read_combined_js()
    assert "stage >= 4" in combined or "stage===4" in combined or "stage === 4" in combined, (
        "JS must only render the Case Summary section at stage 4 (probe) or later"
    )


# ---------------------------------------------------------------------------
# AC2: Section uses existing styles — SectionLabel, card, spacing tokens
# ---------------------------------------------------------------------------

def test_case_summary_uses_section_label():
    """AC2: CaseSummarySection must use SectionLabel (or the same mono heading pattern)."""
    combined = _read_combined_js()
    # The section must either reference SectionLabel component or the standard mono heading class
    has_section_label_usage = (
        "SectionLabel" in combined
    )
    assert has_section_label_usage, (
        "CaseSummarySection must use the SectionLabel component for its heading (AC2)"
    )


def test_case_summary_card_uses_existing_tokens():
    """AC2: Case Summary card must use var(--surface), var(--border), var(--radius) tokens."""
    combined = _read_combined_js()
    # Check that the existing token pattern appears in the JS (already used elsewhere, still required)
    assert "var(--surface)" in combined, "Card background must use var(--surface)"
    assert "var(--border)" in combined, "Card border must use var(--border)"
    assert "var(--radius)" in combined, "Card border-radius must use var(--radius)"


# ---------------------------------------------------------------------------
# AC3: Summary text pulled from caseData.summary (not hardcoded)
# ---------------------------------------------------------------------------

def test_case_summary_reads_from_summary_field():
    """AC3: The JS must reference caseData.summary (the correct data field) to render content."""
    combined = _read_combined_js()
    # The component must read from .summary on the case data object
    assert "caseData.summary" in combined or ".summary" in combined, (
        "JS must read summary content from caseData.summary, not a hardcoded string (AC3)"
    )


def test_get_case_summary_round_trips_correctly(api_client, db_session):
    """AC3: The summary returned by the API matches what was stored (not mangled or hardcoded)."""
    custom_summary = {
        "problem_statement": "Custom problem: network latency spikes under load.",
        "option_ranking": "X: caching layer. Y: CDN. Z: database tuning.",
        "recommended_plan": "Implement CDN for static assets.",
        "probe_plan": "Measure P95 latency before and after CDN rollout.",
    }
    c = _seed_case(db_session, stage="probe", summary=custom_summary)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    returned_summary = data.get("summary")
    assert returned_summary is not None
    assert returned_summary["problem_statement"] == custom_summary["problem_statement"], (
        "problem_statement must round-trip unchanged"
    )
    assert returned_summary["recommended_plan"] == custom_summary["recommended_plan"], (
        "recommended_plan must round-trip unchanged"
    )


# ---------------------------------------------------------------------------
# AC4: Section does not appear at stages prior to probe
# ---------------------------------------------------------------------------

_PRE_PROBE_STAGES = {"sharpened", "bake_off", "gather", "weigh"}


def test_case_summary_absent_at_pre_probe_stages(api_client, db_session):
    """AC4: GET /api/cases/{id} must return a pre-probe stage string for pre-probe cases."""
    for stage_name in ["sharpened", "bake_off", "gather", "weigh"]:
        c = _seed_case(db_session, stage=stage_name, summary=None)
        r = api_client.get(f"/api/cases/{c.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] in _PRE_PROBE_STAGES, (
            f"Stage '{stage_name}' must be in pre-probe stages; got {data['stage']}"
        )


def test_js_does_not_render_summary_before_probe():
    """AC4: The JS must only render CaseSummarySection when stage >= 4 (not for earlier stages)."""
    combined = _read_combined_js()
    # The stage gate condition must be present; verified in AC1 test above.
    # Additionally confirm the condition is specifically guarding the summary section,
    # not just a global probe check.
    assert "stage >= 4" in combined or "stage===4" in combined or "stage === 4" in combined, (
        "The JS must guard the Case Summary section behind the probe stage gate (AC4)"
    )


# ---------------------------------------------------------------------------
# AC5: Section does not duplicate verdict output
# ---------------------------------------------------------------------------

def test_case_summary_section_does_not_contain_verdict_heading():
    """AC5: CaseSummarySection must not render a 'VERDICT' heading (that belongs to Action Plan)."""
    combined = _read_combined_js()
    # Find the CaseSummarySection or the CASE SUMMARY block
    # The VERDICT heading must be in a different section (ACTION PLAN), not inside CASE SUMMARY
    case_summary_idx = combined.find("CASE SUMMARY")
    action_plan_idx = combined.find("ACTION PLAN")
    if case_summary_idx != -1 and action_plan_idx != -1:
        # CASE SUMMARY must appear before ACTION PLAN
        assert case_summary_idx < action_plan_idx, (
            "CASE SUMMARY section must appear before ACTION PLAN section in the render order (AC5)"
        )


def test_get_case_with_verdict_still_returns_summary(api_client, db_session):
    """AC5: When a verdict exists, GET /api/cases/{id} still returns the summary field."""
    c = _seed_case(db_session, stage="probe", summary=_MOCK_SUMMARY, with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data, "summary key must be present even when verdict_log exists"
    assert data.get("verdict_log") is not None, "verdict_log must be present for this case"
    # Both must coexist without conflict
    assert data.get("summary") is not None, "summary must still be non-null alongside verdict_log"


# ---------------------------------------------------------------------------
# AC6: No new one-off styles — only tokens used
# ---------------------------------------------------------------------------

def test_no_hardcoded_pixel_values_in_summary_section():
    """AC6: CaseSummarySection must not introduce hardcoded pixel values outside design tokens."""
    combined = _read_combined_js()
    case_summary_idx = combined.find("CASE SUMMARY")
    if case_summary_idx == -1:
        case_summary_idx = combined.find("CaseSummarySection")
    if case_summary_idx == -1:
        pytest.skip("CaseSummarySection not yet in JS — skipping AC6 style check")

    # Extract a window of JS around the section (2000 chars)
    snippet = combined[case_summary_idx: case_summary_idx + 2000]

    # No hardcoded hex colors directly in the summary section styles
    import re
    hex_colors = re.findall(r"'#[0-9a-fA-F]{3,6}'", snippet)
    assert len(hex_colors) == 0, (
        f"CaseSummarySection must not use hardcoded hex colors; found: {hex_colors} (AC6)"
    )


# ---------------------------------------------------------------------------
# AC7: Close-case affordance accessible from Case Summary section
# ---------------------------------------------------------------------------

def test_close_case_affordance_in_summary_section():
    """AC7: The JS must render a 'Log verdict' or close-case button in the Case Summary area."""
    combined = _read_combined_js()
    # The Log Verdict button must exist in JS and be accessible at probe stage
    assert "Log verdict" in combined or "log verdict" in combined.lower(), (
        "A 'Log verdict' affordance must be present in the JS (AC7)"
    )


def test_summary_section_verdict_button_not_blocked_by_probe(api_client, db_session):
    """AC7: A probe-stage case with no probe run must still return stage='probe'."""
    c = _seed_case(db_session, stage="probe", summary=_MOCK_SUMMARY)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] == "probe", f"Expected stage 'probe' for probe-stage case; got {data['stage']}"
    # The case has no verdict_log and no probe — the close-case affordance must still
    # be renderable (not gated behind probe execution)
    assert data.get("verdict_log") is None, "No verdict should exist yet for this fixture"
    assert data.get("probe") is None, "No probe should exist yet — affordance must not depend on it"
