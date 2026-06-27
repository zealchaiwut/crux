"""Tests for issue #147: Show Case Summary section at probe stage.

AC coverage:
  AC1 – CaseSummarySection is rendered inside CaseDetailScreen at stage >= 4 (probe).
  AC2 – Section is visible even when no verdict exists (null/absent verdict).
  AC3 – Section is NOT rendered when stage < 4 (earlier than probe).
  AC4 – Section heading/container use design tokens (colors, spacing, typography).
  AC5 – Summary text sourced from case.summary; placeholder rendered when empty/absent.
  AC6 – No regression: verdict section still renders correctly when verdict is present.
"""
import json
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"

_SUMMARY_JSON = json.dumps({
    "problem_statement": "Why did retention drop?",
    "option_ranking": "Option A: pricing. Option B: feature gap.",
    "recommended_plan": "Run a price-sensitivity A/B test.",
    "probe_plan": "Measurement probe tracking re-subscription rate.",
})


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


def _seed_case(session, stage="probe", summary=None, verdict=None):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is retention dropping?",
        sharpened="Retention dropped 20% post-change.",
        stage=stage,
        summary=summary,
    )
    session.add(c)
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: CaseSummarySection component exists and is used inside CaseDetailScreen
# ---------------------------------------------------------------------------

def test_case_summary_section_component_defined():
    """AC1: CaseSummarySection component must be defined in JS."""
    combined = _read_combined_js()
    assert "CaseSummarySection" in combined, \
        "CaseSummarySection component must be defined in cases.js"


def test_case_summary_section_used_in_case_detail_screen():
    """AC1: CaseSummarySection must be rendered inside CaseDetailScreen."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    assert detail_start != -1, "CaseDetailScreen must be defined"
    block = combined[detail_start:]
    assert "CaseSummarySection" in block, \
        "CaseSummarySection must be rendered inside CaseDetailScreen"


def test_case_summary_section_gated_on_stage_4():
    """AC1: CaseSummarySection must only render at stage >= 4 (probe)."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    block = combined[detail_start:]
    # Must have a stage >= 4 guard somewhere near CaseSummarySection
    summary_pos = block.find("CaseSummarySection")
    assert summary_pos != -1, "CaseSummarySection must appear in CaseDetailScreen"
    # Look at the context around CaseSummarySection for stage >= 4 condition
    context = block[max(0, summary_pos - 200):summary_pos + 50]
    assert ">= 4" in context or "stage >= 4" in context, \
        "CaseSummarySection must be guarded by 'stage >= 4' condition"


def test_api_returns_summary_at_probe_stage(api_client, db_session):
    """AC1: GET /api/cases/{id} returns the parsed summary object at probe stage."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data, "API must return 'summary' field"
    assert data["summary"] is not None
    assert data["summary"]["problem_statement"] == "Why did retention drop?"


# ---------------------------------------------------------------------------
# AC2: Section visible when no verdict exists
# ---------------------------------------------------------------------------

def test_case_summary_section_not_gated_on_verdict():
    """AC2: CaseSummarySection must NOT be gated on verdict presence."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    block = combined[detail_start:]
    summary_pos = block.find("CaseSummarySection")
    assert summary_pos != -1
    # Check the conditional context: there should be no verdict guard for CaseSummarySection
    context_before = block[max(0, summary_pos - 300):summary_pos]
    # If the last gating condition before CaseSummarySection is only stage-based (not verdict),
    # then "verdict_log" should not appear as a direct gate immediately before CaseSummarySection.
    # We verify by checking the nearest `{` conditional guard is stage-based.
    assert "verdict_log" not in context_before[-100:] or "stage >= 4" in context_before[-150:], \
        "CaseSummarySection must not be gated on verdict_log; only stage >= 4"


def test_api_returns_summary_without_verdict(api_client, db_session):
    """AC2: Case at probe stage with no verdict_log still returns summary field."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON, verdict=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    # verdict_log is None when no verdict has been logged
    assert data.get("verdict_log") is None, \
        "verdict_log must be null when no verdict has been logged"
    assert "summary" in data
    assert data["summary"] is not None


# ---------------------------------------------------------------------------
# AC3: Section NOT rendered at stages earlier than probe
# ---------------------------------------------------------------------------

def test_case_summary_not_rendered_before_probe():
    """AC3: CaseSummarySection must be inside a stage >= 4 guard (not rendered at earlier stages)."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    block = combined[detail_start:]
    summary_pos = block.find("CaseSummarySection")
    assert summary_pos != -1
    # Verify that the guard includes >= 4 (not just == 4)
    context = block[max(0, summary_pos - 200):summary_pos + 50]
    assert ">= 4" in context, \
        "CaseSummarySection must use '>= 4' guard so it renders at probe AND later stages"


@pytest.mark.parametrize("stage", ["sharpened", "bake_off", "gather", "weigh"])
def test_api_returns_null_summary_at_early_stages(api_client, db_session, stage):
    """AC3: Summary field is null for cases before probe stage (no summary generated yet)."""
    c = _seed_case(db_session, stage=stage, summary=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    # summary should be null since it hasn't been generated
    assert data.get("summary") is None, \
        f"Summary must be null for stage={stage!r} before probe"


# ---------------------------------------------------------------------------
# AC4: Design tokens used in CaseSummarySection
# ---------------------------------------------------------------------------

def test_case_summary_section_uses_surface_token():
    """AC4: CaseSummarySection must use var(--surface) for its container background."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    assert summary_start != -1
    block = combined[summary_start:summary_start + 2000]
    assert "var(--surface)" in block, \
        "CaseSummarySection must use var(--surface) design token for background"


def test_case_summary_section_uses_border_token():
    """AC4: CaseSummarySection must use var(--border) for its container border."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 2000]
    assert "var(--border)" in block, \
        "CaseSummarySection must use var(--border) design token"


def test_case_summary_section_uses_radius_token():
    """AC4: CaseSummarySection must use var(--radius) for border-radius."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 2000]
    assert "var(--radius)" in block, \
        "CaseSummarySection must use var(--radius) design token"


def test_case_summary_section_uses_spacing_tokens():
    """AC4: CaseSummarySection must use var(--space-*) tokens for padding/spacing."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 2000]
    assert "var(--space-" in block, \
        "CaseSummarySection must use var(--space-*) spacing tokens"


def test_case_summary_section_heading_uses_mono_class():
    """AC4: CaseSummarySection label must use the 'mono' class for typographic consistency."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 2000]
    assert "mono" in block, \
        "CaseSummarySection must use 'mono' class for section label, matching other sections"


def test_case_summary_section_label_text():
    """AC4: CaseSummarySection must render a 'CASE SUMMARY' heading."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 2000]
    assert "CASE SUMMARY" in block, \
        "CaseSummarySection must include a 'CASE SUMMARY' heading"


# ---------------------------------------------------------------------------
# AC5: Summary sourced from case.summary; placeholder when empty/absent
# ---------------------------------------------------------------------------

def test_case_summary_section_renders_placeholder_when_null():
    """AC5: CaseSummarySection must render a placeholder when summary is null."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 6000]
    # Should have an else/fallback branch for when summary is falsy
    placeholder_phrases = [
        "No summary",
        "no summary",
        "not generated",
        "not yet",
        "placeholder",
        "generated yet",
    ]
    has_placeholder = any(p in block for p in placeholder_phrases)
    assert has_placeholder, \
        "CaseSummarySection must render a placeholder message when summary is null/absent"


def test_case_summary_section_renders_summary_text():
    """AC5: CaseSummarySection must render summary content from the case.summary field."""
    combined = _read_combined_js()
    summary_start = combined.find("function CaseSummarySection")
    block = combined[summary_start:summary_start + 3000]
    # The component uses summary prop and accesses its fields
    assert "summary" in block, \
        "CaseSummarySection must consume a summary prop to display case summary content"


def test_api_returns_parsed_summary_object(api_client, db_session):
    """AC5: GET /api/cases/{id} returns summary as parsed JSON object, not raw string."""
    c = _seed_case(db_session, stage="probe", summary=_SUMMARY_JSON)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    summary = data.get("summary")
    assert isinstance(summary, dict), \
        f"summary must be a parsed JSON object, not {type(summary)}"
    assert "problem_statement" in summary


def test_api_returns_null_summary_when_not_generated(api_client, db_session):
    """AC5: GET /api/cases/{id} returns null summary when case.summary is not set."""
    c = _seed_case(db_session, stage="probe", summary=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("summary") is None, \
        "summary must be null when no summary has been generated"


# ---------------------------------------------------------------------------
# AC6: No regression — verdict section renders when verdict is present
# ---------------------------------------------------------------------------

def test_verdict_section_still_present_in_case_detail():
    """AC6: Verdict section must still be rendered in CaseDetailScreen (no regression)."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    block = combined[detail_start:]
    assert "VERDICT" in block, \
        "Verdict section must still be rendered in CaseDetailScreen (no regression)"


def test_verdict_section_after_summary_in_detail():
    """AC6: When verdict and summary coexist, summary appears before verdict section in the layout."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    block = combined[detail_start:]
    summary_pos = block.find("CaseSummarySection")
    verdict_pos = block.find("VERDICT")
    assert summary_pos != -1, "CaseSummarySection must appear in CaseDetailScreen"
    assert verdict_pos != -1, "VERDICT section must appear in CaseDetailScreen"
    assert summary_pos < verdict_pos, \
        "Case Summary section must appear before the Verdict section in the layout"


def test_api_returns_verdict_log_when_present(api_client, db_session):
    """AC6: GET /api/cases/{id} returns verdict_log when a verdict has been logged."""
    from app import models
    c = _seed_case(db_session, stage="verdict", summary=_SUMMARY_JSON)
    # Verdict is associated with a probe, so we must create a probe first
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="re-subscription rate",
        status="designed",
    )
    db_session.add(probe)
    db_session.flush()
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="Hypothesis confirmed.",
    )
    db_session.add(verdict)
    db_session.commit()
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data.get("verdict") == "confirmed", "verdict must still be returned from API"
    assert data.get("verdict_log") is not None, "verdict_log must be returned when verdict exists"
    assert data.get("summary") is not None, "summary must also be returned alongside verdict"
