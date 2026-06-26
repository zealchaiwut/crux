"""Tests for issue #150: Summary endpoint generate-and-cache behavior,
force-regeneration flag, pre-probe stage rejection, and Summary/ActionPlan
gate logic.

AC coverage:
  AC1 – POST /api/cases/{id}/summary generates a summary and caches the result
         on first call; a second call without ?force=true returns cached: True.
  AC2 – POST /api/cases/{id}/summary?force=true regenerates even when a cached
         result already exists and returns cached: False.
  AC3 – POST /api/cases/{id}/summary returns HTTP 422 when stage is before probe.
  AC4 – Summary component renders a pre-verdict placeholder before a verdict
         (and before a summary has been generated).
  AC5 – ActionPlan component remains absent/locked until a verdict exists.
  AC6 – ActionPlan component unlocks/renders after a verdict is present.
  AC7 – All new tests pass in CI with no skips.
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import os
os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"

# ---------------------------------------------------------------------------
# Stable fake summary JSON returned by the mocked generate_summary call.
# ---------------------------------------------------------------------------
_FAKE_SUMMARY = {
    "problem_statement": "Why did conversion drop after the redesign?",
    "option_ranking": "Option A: UX friction. Option B: page speed regression.",
    "recommended_plan": "Run an A/B test reverting the checkout flow.",
    "probe_plan": "Measurement probe tracking cart-to-purchase conversion rate.",
}
_FAKE_SUMMARY_JSON = json.dumps(_FAKE_SUMMARY)

_FAKE_SUMMARY_2 = {
    "problem_statement": "Updated: Why did conversion drop?",
    "option_ranking": "Option A: trust signals. Option B: page speed.",
    "recommended_plan": "Run a trust-badge A/B test.",
    "probe_plan": "Measurement probe tracking checkout completion.",
}
_FAKE_SUMMARY_2_JSON = json.dumps(_FAKE_SUMMARY_2)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


def _seed_case(session, stage="probe", summary=None, with_verdict=False):
    """Seed a minimal case with a probe (required for stages >= probe)."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is conversion declining?",
        sharpened="Conversion dropped 18% after the checkout redesign.",
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
        name="UX friction",
        mechanism="New checkout flow adds extra steps.",
        prior="0.65",
        current_rank=1,
    )
    session.add(plan)

    probe = None
    if stage in ("probe", "verdict"):
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            target_metric="checkout conversion rate",
            cost="~£0",
            time="2 weeks",
            status="designed",
        )
        session.add(probe)
        session.flush()

    if with_verdict and probe:
        verdict = models.Verdict(
            id=str(uuid.uuid4()),
            probe_id=probe.id,
            outcome="confirmed",
            notes="UX friction was the root cause.",
        )
        session.add(verdict)

    session.commit()
    return c


def _read_combined_js():
    return "".join(
        (JS_DIR / f).read_text()
        for f in sorted(JS_DIR.iterdir())
        if f.suffix == ".js"
    )


def _case_detail_block(combined):
    """Return source text starting at CaseDetailScreen definition."""
    idx = combined.find("function CaseDetailScreen")
    assert idx != -1, "CaseDetailScreen must be defined in the JS"
    return combined[idx:]


def _case_summary_section_block(combined):
    """Return source text of CaseSummarySection."""
    idx = combined.find("function CaseSummarySection")
    assert idx != -1, "CaseSummarySection must be defined in the JS"
    next_func = combined.find("\nfunction ", idx + 1)
    return combined[idx:next_func] if next_func != -1 else combined[idx:]


# ---------------------------------------------------------------------------
# AC1: First call generates summary, caches it; second call returns cached:True
# ---------------------------------------------------------------------------

def test_summary_endpoint_generates_on_first_call(api_client, db_session):
    """AC1: POST /api/cases/{id}/summary calls generate_summary and returns the result."""
    c = _seed_case(db_session, stage="probe")

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("cached") is False, (
        "First call must return cached: False when no prior summary exists (AC1)"
    )
    assert data.get("summary") == _FAKE_SUMMARY, (
        "First call must return the generated summary object (AC1)"
    )


def test_summary_endpoint_caches_on_second_call(api_client, db_session):
    """AC1: Second POST without ?force=true returns cached:True with same summary."""
    c = _seed_case(db_session, stage="probe")

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ) as mock_gen:
        # First call — generates and stores
        r1 = api_client.post(f"/api/cases/{c.id}/summary")
        assert r1.status_code == 200
        assert r1.json()["cached"] is False

        # Second call — should use cache, not call generate_summary again
        r2 = api_client.post(f"/api/cases/{c.id}/summary")

    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    assert r2.json().get("cached") is True, (
        "Second call without ?force=true must return cached: True (AC1)"
    )
    assert r2.json().get("summary") == _FAKE_SUMMARY, (
        "Cached summary must match the originally generated content (AC1)"
    )
    # generate_summary should have been called exactly once
    assert mock_gen.call_count == 1, (
        "generate_summary must be called only once across two calls when force is not set (AC1)"
    )


def test_summary_stored_in_db_after_first_call(api_client, db_session):
    """AC1: After first call, the summary is persisted to case.summary in the DB."""

    c = _seed_case(db_session, stage="probe")
    assert c.summary is None, "Summary must start as None before generation (AC1 precondition)"

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200

    db_session.refresh(c)
    assert c.summary is not None, "Summary must be persisted to case.summary after first call (AC1)"
    stored = json.loads(c.summary)
    assert stored["problem_statement"] == _FAKE_SUMMARY["problem_statement"], (
        "Stored summary must match the generated value (AC1)"
    )


# ---------------------------------------------------------------------------
# AC2: ?force=true regenerates even when a cached result exists
# ---------------------------------------------------------------------------

def test_force_regenerates_when_cache_exists(api_client, db_session):
    """AC2: POST /api/cases/{id}/summary?force=true regenerates the summary."""
    c = _seed_case(db_session, stage="probe", summary=_FAKE_SUMMARY_JSON)

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_2_JSON),
    ) as mock_gen:
        r = api_client.post(f"/api/cases/{c.id}/summary", params={"force": "true"})

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("cached") is False, (
        "?force=true must return cached: False even when a prior summary exists (AC2)"
    )
    assert data.get("summary") == _FAKE_SUMMARY_2, (
        "?force=true must return the freshly generated summary (AC2)"
    )
    assert mock_gen.call_count == 1, (
        "generate_summary must be called once when force=true (AC2)"
    )


def test_force_updates_cached_summary_in_db(api_client, db_session):
    """AC2: After ?force=true, the DB is updated with the new summary."""
    c = _seed_case(db_session, stage="probe", summary=_FAKE_SUMMARY_JSON)

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_2_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary", params={"force": "true"})

    assert r.status_code == 200
    db_session.refresh(c)
    stored = json.loads(c.summary)
    assert stored["problem_statement"] == _FAKE_SUMMARY_2["problem_statement"], (
        "DB summary must be updated to the force-regenerated value (AC2)"
    )


def test_without_force_skips_generation_when_cache_exists(api_client, db_session):
    """AC2: Without ?force=true, generate_summary is NOT called when a cache exists."""
    c = _seed_case(db_session, stage="probe", summary=_FAKE_SUMMARY_JSON)

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_2_JSON),
    ) as mock_gen:
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200
    assert r.json()["cached"] is True, (
        "Call without force must return cached: True when summary exists (AC2)"
    )
    assert mock_gen.call_count == 0, (
        "generate_summary must NOT be called when cache exists and force is not set (AC2)"
    )


# ---------------------------------------------------------------------------
# AC3: Returns 422 when stage is before probe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pre_probe_stage", ["sharpened", "bake_off", "gather", "weigh"])
def test_summary_returns_422_before_probe_stage(api_client, db_session, pre_probe_stage):
    """AC3: POST /api/cases/{id}/summary returns 422 for stages before probe."""
    c = _seed_case(db_session, stage=pre_probe_stage)

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 422, (
        f"Expected 422 for stage='{pre_probe_stage}', got {r.status_code} (AC3)"
    )
    detail = r.json().get("detail", "")
    assert pre_probe_stage in detail or "probe" in detail.lower(), (
        f"Error detail must mention the stage or 'probe' requirement (AC3): {detail!r}"
    )


def test_summary_succeeds_at_probe_stage(api_client, db_session):
    """AC3 (boundary): POST /api/cases/{id}/summary succeeds at stage='probe'."""
    c = _seed_case(db_session, stage="probe")

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, (
        f"Summary must succeed at stage='probe' (AC3 boundary): {r.text}"
    )


def test_summary_succeeds_at_verdict_stage(api_client, db_session):
    """AC3 (boundary): POST /api/cases/{id}/summary succeeds at stage='verdict'."""
    c = _seed_case(db_session, stage="verdict", with_verdict=True)

    with patch(
        "app.routers.cases.generate_summary",
        new=AsyncMock(return_value=_FAKE_SUMMARY_JSON),
    ):
        r = api_client.post(f"/api/cases/{c.id}/summary")

    assert r.status_code == 200, (
        f"Summary must succeed at stage='verdict' (AC3 boundary): {r.text}"
    )


# ---------------------------------------------------------------------------
# AC4: Summary component renders a pre-verdict placeholder before a verdict
# ---------------------------------------------------------------------------

def test_case_summary_section_has_placeholder_for_no_summary():
    """AC4: CaseSummarySection must render a placeholder when summary is null/undefined."""
    combined = _read_combined_js()
    block = _case_summary_section_block(combined)
    assert "No summary generated yet" in block, (
        "CaseSummarySection must include a 'No summary generated yet' placeholder "
        "for the pre-summary state (AC4)"
    )


def test_case_summary_section_renders_content_when_summary_present():
    """AC4: CaseSummarySection source must render summary fields when summary is present."""
    combined = _read_combined_js()
    block = _case_summary_section_block(combined)
    assert "summary.problem_statement" in block, (
        "CaseSummarySection must render summary.problem_statement (AC4)"
    )
    assert "summary.option_ranking" in block, (
        "CaseSummarySection must render summary.option_ranking (AC4)"
    )
    assert "summary.recommended_plan" in block, (
        "CaseSummarySection must render summary.recommended_plan (AC4)"
    )


def test_api_returns_null_summary_when_not_generated(api_client, db_session):
    """AC4: GET /api/cases/{id} returns summary: null when no summary has been generated."""
    c = _seed_case(db_session, stage="probe", summary=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("summary") is None, (
        "API must return summary: null when no summary has been generated yet (AC4)"
    )


def test_case_summary_section_visible_without_verdict():
    """AC4: CaseSummarySection must render at stage >= 4 regardless of verdict presence."""
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    # Find CaseSummarySection JSX usage
    summary_pos = block.find("CaseSummarySection")
    assert summary_pos != -1, "CaseSummarySection must be used in CaseDetailScreen (AC4)"

    # The gate immediately before it must be stage-based, not verdict-based
    gate_ctx = block[max(0, summary_pos - 250): summary_pos]
    assert "stage >= 4" in gate_ctx, (
        "CaseSummarySection must be gated on stage >= 4 (not verdict) so it "
        "renders in the pre-verdict state (AC4)"
    )
    # verdict_log must NOT be the direct gate for summary
    assert "!!caseData.verdict_log" not in gate_ctx, (
        "CaseSummarySection must NOT be gated on verdict_log — it renders pre-verdict (AC4)"
    )


# ---------------------------------------------------------------------------
# AC5: ActionPlan component remains locked/disabled until a verdict exists
# ---------------------------------------------------------------------------

def test_action_plan_gated_on_verdict_log_in_js():
    """AC5: The ACTION PLAN section in CaseDetailScreen is gated on verdict_log."""
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    action_plan_idx = block.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1, "ACTION PLAN SectionLabel must exist in CaseDetailScreen (AC5)"

    preceding = block[max(0, action_plan_idx - 150): action_plan_idx]
    assert "verdict_log" in preceding, (
        "The ACTION PLAN SectionLabel must be inside a verdict_log gate — "
        "it must not render until a verdict exists (AC5)"
    )


def test_api_no_verdict_log_when_no_verdict(api_client, db_session):
    """AC5: GET /api/cases/{id} returns verdict_log: null when no verdict logged."""
    c = _seed_case(db_session, stage="probe", with_verdict=False)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is None, (
        "verdict_log must be null when no verdict has been issued — "
        "ActionPlan must not render (AC5)"
    )


def test_action_plan_not_gated_only_on_stage_without_verdict():
    """AC5: The ACTION PLAN gate must require BOTH stage >= 4 AND verdict_log."""
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    action_plan_idx = block.find("<SectionLabel>ACTION PLAN")
    assert action_plan_idx != -1

    preceding = block[max(0, action_plan_idx - 150): action_plan_idx]
    assert "stage >= 4" in preceding and "verdict_log" in preceding, (
        "ACTION PLAN gate must check BOTH stage >= 4 AND verdict_log so it "
        "remains locked pre-verdict even when at probe stage (AC5)"
    )


# ---------------------------------------------------------------------------
# AC6: ActionPlan component unlocks after a verdict is present
# ---------------------------------------------------------------------------

def test_action_plan_renders_verdict_details_in_js():
    """AC6: The ACTION PLAN section renders verdict outcome and notes from verdict_log."""
    combined = _read_combined_js()
    block = _case_detail_block(combined)
    assert "verdict_log.outcome" in block, (
        "ACTION PLAN section must render verdict_log.outcome (AC6)"
    )
    assert "verdict_log.notes" in block, (
        "ACTION PLAN section must render verdict_log.notes (AC6)"
    )


def test_api_verdict_log_present_after_verdict(api_client, db_session):
    """AC6: GET /api/cases/{id} returns a non-null verdict_log after verdict is logged."""
    c = _seed_case(db_session, stage="verdict", with_verdict=True)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict_log") is not None, (
        "verdict_log must be non-null after a verdict is issued — "
        "ActionPlan should render (AC6)"
    )
    assert data["verdict_log"].get("outcome") == "confirmed", (
        "verdict_log.outcome must match the logged verdict (AC6)"
    )


def test_action_plan_unlocked_state_includes_leading_plan():
    """AC6: The unlocked ACTION PLAN section must show the LEADING PLAN sub-section."""
    combined = _read_combined_js()
    assert "LEADING PLAN" in combined, (
        "The unlocked ACTION PLAN section must include a LEADING PLAN sub-section (AC6)"
    )
