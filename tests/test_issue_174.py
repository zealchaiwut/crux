"""Tests for issue #174: Render summary with linked inline citations.

AC coverage:
  AC1  – Summary paragraphs rendered in cases.js display inline [n] citation markers
         as clickable elements at positions provided by the data.
  AC2  – Each [n] marker is a clickable element that opens the Source Detail modal
         for the correct source (matched by source ID/index).
  AC3  – A References list is rendered below the summary paragraphs, enumerating
         all cited sources in order.
  AC4  – Each entry in the References list is also clickable and opens the correct
         Source Detail modal.
  AC5  – The Source Detail modal opens with the correct source pre-loaded when
         triggered from either a marker or a reference entry.
  AC6  – Citation markers and the References list use DESIGN.md color tokens,
         typography, and spacing — no hard-coded style values.
  AC7  – The summary section reuses existing section container/heading styles;
         no new layout primitives are introduced.
  AC8  – If no citations exist for a summary, no References section is rendered
         (no empty heading or list).
  AC9  – The feature degrades gracefully when the Batch 2 Source Detail modal is
         absent — markers render but log a console warning rather than throwing.
"""
import os
import pathlib
import re
import uuid
import json

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


def _extract_component(src, name):
    """Extract the body of a named function component from cases.js."""
    pattern = rf"function {re.escape(name)}\((.+?)(?=\n// ---------------------------------------------------------------------------|\nfunction )"
    m = re.search(pattern, src, re.DOTALL)
    return m.group(0) if m else None


def _extract_summary_section(src):
    return _extract_component(src, "CaseSummarySection")


# ===========================================================================
# DB / API fixtures
# ===========================================================================

def _make_engine():
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
    engine = _make_engine()
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


def _seed_case_with_summary(session, summary_json=None):
    from app import models

    src_id_a = str(uuid.uuid4())
    src_id_b = str(uuid.uuid4())

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why did retention drop?",
        sharpened="User retention dropped after pricing change.",
        stage="probe",
        summary=summary_json or json.dumps({
            "paragraphs": [
                f"The retention drop coincides with the pricing change [1].",
                f"A secondary factor is competitive pressure [2].",
                f"Evidence points primarily to price sensitivity [1] as root cause.",
            ],
            "references": [
                {"id": 1, "source_id": src_id_a, "title": "Price Study Q1", "url": "https://example.com/price"},
                {"id": 2, "source_id": src_id_b, "title": "Competitor Report", "url": "https://example.com/comp"},
            ],
        }),
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Price sensitivity",
        mechanism="Price exceeded perceived value.",
        current_rank=1,
    )
    session.add(plan)
    session.flush()

    src_a = models.Source(
        id=src_id_a,
        plan_id=plan.id,
        kind="article",
        title="Price Study Q1",
        url="https://example.com/price",
        claim="Price was the dominant factor.",
    )
    src_b = models.Source(
        id=src_id_b,
        plan_id=plan.id,
        kind="article",
        title="Competitor Report",
        url="https://example.com/comp",
        claim="Rival launched key feature.",
    )
    session.add_all([src_a, src_b])
    session.commit()
    return c, src_id_a, src_id_b


# ===========================================================================
# AC1: Summary paragraphs display [n] markers as clickable elements
# ===========================================================================

def test_case_summary_section_renders_paragraphs_not_old_fields():
    """AC1: CaseSummarySection must render summary.paragraphs (not old
    summary.problem_statement / option_ranking / recommended_plan / probe_plan)."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    assert "summary.paragraphs" in block or ".paragraphs" in block, (
        "CaseSummarySection must render from summary.paragraphs (AC1)"
    )


def test_summary_markers_rendered_as_clickable_elements():
    """AC1: [n] citation markers in paragraph text must be rendered as clickable
    elements (not emitted as raw text)."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # The component must split/parse paragraph text to render [n] markers specially.
    # The parsing logic may live in CaseSummarySection itself OR in a named helper
    # that CaseSummarySection calls.
    has_marker_parse = (
        re.search(r'\[(\d+)\]', block) is not None
        or "\\[" in block
        or "split" in block
        or "replace" in block
        or "parseParagraph" in block
        or "renderParagraph" in block
        or "CitationMarker" in block
        or "_renderCitationParagraph" in block
        or "_renderCitation" in block
    )
    # Also accept if a dedicated module-level helper is referenced
    if not has_marker_parse:
        has_marker_parse = (
            re.search(r'\[(\d+)\]', src) is not None
            and ("split" in src or "CitationMarker" in src or "_renderCitation" in src)
        )
    assert has_marker_parse, (
        "CaseSummarySection must parse paragraph text to render [n] markers as "
        "interactive elements, not as raw text strings (AC1)"
    )


# ===========================================================================
# AC2: Each [n] marker is a clickable element
# ===========================================================================

def test_citation_marker_is_clickable():
    """AC2: [n] markers must be rendered as buttons or clickable spans, not plain text."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # There must be an onClick handler associated with the marker rendering
    assert "onClick" in block, (
        "CaseSummarySection must attach an onClick handler to citation markers (AC2)"
    )


def test_citation_marker_click_opens_source_detail_modal():
    """AC2: Clicking [n] marker must open SourceDetailModal for the correct source."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # The component must reference SourceDetailModal or a local modal state
    opens_modal = (
        "SourceDetailModal" in block
        or "setSelectedSource" in block
        or "selectedSource" in block
        or "openSource" in block
        or "showModal" in block
    )
    assert opens_modal, (
        "CaseSummarySection must open SourceDetailModal when a citation marker is clicked (AC2)"
    )


# ===========================================================================
# AC3: References list rendered below paragraphs
# ===========================================================================

def test_references_section_is_rendered():
    """AC3: CaseSummarySection must render a References heading and list."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    has_references_label = (
        '"References"' in block
        or "'References'" in block
        or "REFERENCES" in block
        or "references" in block.lower()
    )
    assert has_references_label, (
        "CaseSummarySection must render a 'References' section heading (AC3)"
    )


def test_references_list_enumerates_cited_sources():
    """AC3: References list must render entries from summary.references in order."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # Must iterate over references array
    iterates_refs = (
        "references" in block
        and (
            ".map(" in block
            or "forEach" in block
            or ".map\n" in block
        )
    )
    assert iterates_refs, (
        "CaseSummarySection must iterate over summary.references to render the list (AC3)"
    )


# ===========================================================================
# AC4: Each reference entry is clickable
# ===========================================================================

def test_reference_entries_are_clickable():
    """AC4: Reference list entries must have an onClick handler."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # Must have onClick (already checked above, but verify it's in the references rendering context)
    # The block must reference both onClick and references together
    assert "onClick" in block and "reference" in block.lower(), (
        "CaseSummarySection must render reference entries with an onClick handler (AC4)"
    )


# ===========================================================================
# AC5: Modal opens with correct source pre-loaded
# ===========================================================================

def test_source_detail_modal_rendered_in_summary_section():
    """AC5: CaseSummarySection must render SourceDetailModal when a citation/reference
    is clicked, with the correct source pre-loaded."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    assert "SourceDetailModal" in block, (
        "CaseSummarySection must render SourceDetailModal for citation/reference clicks (AC5)"
    )


def test_summary_section_receives_sources_prop():
    """AC5: CaseSummarySection must accept a sources prop to look up full source
    data when a citation marker is clicked."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    assert "sources" in block, (
        "CaseSummarySection must accept a 'sources' prop for looking up source details (AC5)"
    )


def test_case_detail_screen_passes_sources_to_summary_section():
    """AC5: CaseDetailScreen must pass sources (flattened from plans) to CaseSummarySection."""
    src = _src()
    # Find the CaseSummarySection JSX usage
    summary_usage = re.search(
        r'<CaseSummarySection\b[^/]*/?>',
        src,
        re.DOTALL,
    )
    assert summary_usage is not None, "CaseSummarySection JSX usage not found in cases.js"
    usage_block = summary_usage.group(0)

    assert "sources" in usage_block, (
        "CaseSummarySection JSX must receive a 'sources' prop so it can open the Source "
        "Detail modal with full source data (AC5)"
    )


# ===========================================================================
# AC6: No hard-coded style values — use design tokens
# ===========================================================================

def test_citation_markers_use_design_tokens_not_hardcoded_colors():
    """AC6: Citation marker styles must reference CSS token variables, not hex/rgb values."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # Find the citation marker rendering (look around the [n] parsing logic)
    # It should use var(--...) tokens not raw color values like #7c3aed
    hardcoded_hex = re.findall(r'color:\s*["\']?#[0-9a-fA-F]{3,6}', block)
    hardcoded_rgb = re.findall(r'color:\s*rgb\(', block)

    assert not hardcoded_hex, (
        f"Citation/reference rendering must not use hardcoded hex colors; "
        f"found: {hardcoded_hex}. Use var(--crux) or other design tokens (AC6)"
    )
    assert not hardcoded_rgb, (
        f"Citation/reference rendering must not use hardcoded rgb() colors; "
        f"found: {hardcoded_rgb}. Use CSS variable tokens (AC6)"
    )


def test_references_section_uses_design_token_spacing():
    """AC6: References section spacing must use var(--space-*) tokens."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    has_space_token = "var(--space-" in block
    assert has_space_token, (
        "CaseSummarySection must use var(--space-*) spacing tokens (AC6)"
    )


# ===========================================================================
# AC7: Reuses existing section container/heading styles
# ===========================================================================

def test_summary_section_uses_existing_container_styles():
    """AC7: CaseSummarySection must not introduce new layout primitives — it
    should reuse the existing surface/border/radius card pattern."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # Must still use the surface card pattern established in the existing component
    uses_surface = (
        "var(--surface)" in block
        or "var(--border)" in block
        or "var(--radius)" in block
    )
    assert uses_surface, (
        "CaseSummarySection must reuse existing surface/border/radius card styles (AC7)"
    )


def test_summary_section_uses_section_label():
    """AC7: CaseSummarySection must use SectionLabel (existing heading component) for
    its heading, not a bespoke layout element."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    assert "SectionLabel" in block, (
        "CaseSummarySection must use the SectionLabel component for its heading (AC7)"
    )


# ===========================================================================
# AC8: No References section when no citations
# ===========================================================================

def test_references_section_not_rendered_when_empty():
    """AC8: When summary.references is empty/absent, no References section must be rendered."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    # The References section rendering must be guarded by a condition on references length/existence
    refs_conditional = (
        re.search(r'references\s*&&\s*references\.length', block) is not None
        or re.search(r'references\.length\s*>', block) is not None
        or re.search(r'references\s*\?\s*\.?\s*length', block) is not None
        or re.search(r'\?\s*references', block) is not None
        or re.search(r'if.*references', block) is not None
        or re.search(r'references\s*&&', block) is not None
    )
    assert refs_conditional, (
        "CaseSummarySection must conditionally render the References section only when "
        "summary.references is non-empty (AC8)"
    )


def test_api_summary_with_empty_references(api_client, db_session):
    """AC8: Case with summary but no references still returns a valid response and
    the frontend can handle it (empty references array)."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Problem with no sources.",
        sharpened="No sources available.",
        stage="probe",
        summary=json.dumps({
            "paragraphs": [
                "This case has no cited sources.",
                "The evidence is limited.",
                "Further research is needed.",
            ],
            "references": [],
        }),
    )
    db_session.add(c)
    db_session.flush()
    db_session.commit()

    resp = api_client.get(f"/api/cases/{c.id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    summary = data.get("summary")
    assert summary is not None, "Summary must be returned"
    assert isinstance(summary.get("references"), list), "references must be an array"
    assert summary["references"] == [], "references must be empty when no sources cited"


# ===========================================================================
# AC9: Graceful degradation when SourceDetailModal is absent
# ===========================================================================

def test_graceful_degradation_uses_console_warn():
    """AC9: CaseSummarySection must call console.warn (not throw) when the
    Source Detail modal is unavailable."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    assert "console.warn" in block, (
        "CaseSummarySection must log a console.warn when SourceDetailModal cannot be opened, "
        "rather than throwing an exception (AC9)"
    )


def test_graceful_degradation_checks_modal_availability():
    """AC9: CaseSummarySection must guard the modal open call with a typeof/existence check."""
    src = _src()
    block = _extract_summary_section(src)
    assert block is not None, "CaseSummarySection not found in cases.js"

    guards_modal = (
        "typeof SourceDetailModal" in block
        or "SourceDetailModal ?" in block
        or "typeof openSource" in block
        or re.search(r'if\s*\(\s*(typeof\s+)?SourceDetailModal', block) is not None
        or re.search(r'SourceDetailModal\s*!==\s*["\']undefined["\']', block) is not None
        or "typeof SourceDetailModal !== \"undefined\"" in block
        or "typeof SourceDetailModal !== 'undefined'" in block
        or "SourceDetailModal == null" in block
    )
    assert guards_modal, (
        "CaseSummarySection must check whether SourceDetailModal is available before calling it, "
        "to support graceful degradation (AC9)"
    )
