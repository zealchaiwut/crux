"""Tests for issue #172: Add source detail modal to SourceChip click.

AC coverage:
  AC1  – Clicking any SourceChip opens a modal dialog
         (collapsed chip onClick opens modal, not inline expansion)
  AC2  – Modal displays: title, kind, url (clickable link), claim, citation,
         support_status, support_rationale, content_summary
  AC3  – extracted_content / transcript rendered in collapsed "Show more" expander
  AC4  – For sources where extracted_content is null, modal shows Fetch content button
  AC5  – Fetch content triggers API call, shows loading state, populates fields on
         success or shows error without closing the modal
  AC6  – Modal follows CommanderSpecModal pattern: role=dialog, aria-modal, Escape
         key close, backdrop click close, ARIA roles
  AC7  – All fields gracefully handle missing/null values (— or omit the row)
  AC8  – Keyboard-navigable; WCAG 2.1 AA contrast requirements met (structural checks)
"""
import os
import pathlib
import re
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"


def _src():
    return CASES_JS.read_text()


# ===========================================================================
# Helpers
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


def _seed_case_with_source(session, extracted_content=None, content_summary=None,
                            support_rationale=None):
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened statement",
        stage="gather",
    )
    session.add(case)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="Some mechanism",
        prior="0.5",
        current_rank=1,
    )
    session.add(plan)
    session.flush()

    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="article",
        title="Test Source Title",
        url="https://example.com/article",
        claim="Test claim about the hypothesis",
        citation="Author, 2024",
        support_status="supports",
        rationale="AI rationale here",
        support_rationale=support_rationale or "Supports rationale here",
        manually_overridden=False,
        extracted_content=extracted_content,
        content_summary=content_summary or "Summary of article content",
    )
    session.add(source)
    session.commit()
    return case, plan, source


# ===========================================================================
# AC1: Collapsed SourceChip click opens modal (static JS analysis)
# ===========================================================================

def test_sourcechip_collapsed_click_opens_modal_not_inline_expand():
    """AC1: Collapsed chip onClick opens modal state, not setExpanded(true)."""
    src = _src()
    # The collapsed chip button must NOT call setExpanded(true) as its onClick
    # It should open the modal instead — look for showModal / openModal / setShowModal
    collapsed_chip_block = re.search(
        r"if \(!expanded\)\s*\{(.+?)// Expanded state",
        src,
        re.DOTALL,
    )
    assert collapsed_chip_block, "Could not find collapsed chip block (if (!expanded)) in cases.js"
    block = collapsed_chip_block.group(1)
    # The block should NOT have onClick={() => setExpanded(true)} as the primary click
    assert "setShowModal(true)" in block or "openModal" in block or "setModalOpen(true)" in block, (
        "Collapsed SourceChip onClick must open a modal (setShowModal(true) or equivalent), "
        "not just setExpanded(true)"
    )


# ===========================================================================
# AC1 + AC6: SourceDetailModal component exists and follows modal pattern
# ===========================================================================

def test_source_detail_modal_component_exists():
    """AC1 + AC6: SourceDetailModal function component is defined in cases.js."""
    src = _src()
    assert "function SourceDetailModal" in src, (
        "SourceDetailModal component must be defined in cases.js"
    )


def test_source_detail_modal_has_dialog_role():
    """AC6: SourceDetailModal uses role='dialog' for accessibility."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal function not found in cases.js"
    block = modal_block.group(0)
    assert 'role="dialog"' in block, "SourceDetailModal must have role='dialog'"


def test_source_detail_modal_has_aria_modal():
    """AC6: SourceDetailModal has aria-modal='true'."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal function not found in cases.js"
    block = modal_block.group(0)
    assert 'aria-modal="true"' in block, "SourceDetailModal must have aria-modal='true'"


def test_source_detail_modal_handles_escape_key():
    """AC6: SourceDetailModal closes on Escape key press."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal function not found in cases.js"
    block = modal_block.group(0)
    assert "Escape" in block, (
        "SourceDetailModal must handle Escape key to close (like CommanderSpecModal)"
    )
    assert "onClose" in block or "onClose()" in block, (
        "SourceDetailModal must call onClose (or equivalent) on Escape"
    )


def test_source_detail_modal_closes_on_backdrop_click():
    """AC6: SourceDetailModal backdrop (outer div) has onClick that closes the modal."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal function not found in cases.js"
    block = modal_block.group(0)
    # Backdrop click: outer div has onClick close, inner div has stopPropagation
    assert "stopPropagation" in block, (
        "SourceDetailModal inner content must call e.stopPropagation() to prevent backdrop click"
    )


def test_source_detail_modal_has_close_button():
    """AC6: SourceDetailModal has a close button with aria-label."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal function not found in cases.js"
    block = modal_block.group(0)
    assert 'aria-label="Close"' in block or "aria-label=\"Close modal\"" in block, (
        "SourceDetailModal must have a close button with aria-label='Close'"
    )


# ===========================================================================
# AC2: Modal displays all required source fields
# ===========================================================================

def test_source_detail_modal_renders_title():
    """AC2: SourceDetailModal renders the source title."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "title" in block, "SourceDetailModal must display the source title"


def test_source_detail_modal_renders_url_as_link():
    """AC2: SourceDetailModal renders the URL as a clickable anchor tag."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    # URL should be rendered in an <a> tag
    assert "<a" in block and "url" in block.lower(), (
        "SourceDetailModal must render URL as a clickable link (<a> element)"
    )


def test_source_detail_modal_renders_claim():
    """AC2: SourceDetailModal renders the claim field."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "claim" in block, "SourceDetailModal must display the source claim"


def test_source_detail_modal_renders_citation():
    """AC2: SourceDetailModal renders the citation field."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "citation" in block, "SourceDetailModal must display the source citation"


def test_source_detail_modal_renders_support_rationale():
    """AC2: SourceDetailModal renders support_rationale."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "support_rationale" in block, (
        "SourceDetailModal must display support_rationale"
    )


def test_source_detail_modal_renders_content_summary():
    """AC2: SourceDetailModal renders content_summary."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "content_summary" in block, (
        "SourceDetailModal must display content_summary"
    )


def test_source_detail_modal_renders_kind():
    """AC2: SourceDetailModal renders the source kind."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "kind" in block, "SourceDetailModal must display source kind"


# ===========================================================================
# AC3: extracted_content in collapsed "Show more" expander
# ===========================================================================

def test_source_detail_modal_has_show_more_expander():
    """AC3: SourceDetailModal has a 'Show more' toggle for extracted_content."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "Show more" in block or "showMore" in block or "showContent" in block, (
        "SourceDetailModal must have a 'Show more' expander for extracted_content"
    )


def test_source_detail_modal_expander_uses_extracted_content():
    """AC3: The Show more expander reveals extracted_content."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "extracted_content" in block, (
        "SourceDetailModal must use extracted_content in the Show more expander"
    )


# ===========================================================================
# AC4: Fetch content button shown when extracted_content is null
# ===========================================================================

def test_source_detail_modal_shows_fetch_button_when_no_content():
    """AC4: SourceDetailModal conditionally renders Fetch content button."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "Fetch content" in block, (
        "SourceDetailModal must render a 'Fetch content' button"
    )


def test_source_detail_modal_fetch_button_conditional_on_null_content():
    """AC4: Fetch content button is conditional (only when extracted_content is null/empty)."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    # The fetch button must be inside a conditional that checks extracted_content
    fetch_pos = block.find("Fetch content")
    # There should be a condition referencing extracted_content before the button
    content_before_button = block[:fetch_pos]
    assert "extracted_content" in content_before_button, (
        "Fetch content button must be conditionally shown based on extracted_content being null"
    )


# ===========================================================================
# AC5: Fetch content calls the API endpoint and shows loading
# ===========================================================================

def test_source_detail_modal_fetch_calls_fetch_content_endpoint():
    """AC5: Fetch content button triggers POST /api/sources/{id}/fetch-content."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "fetch-content" in block, (
        "SourceDetailModal must call the fetch-content API endpoint"
    )


def test_source_detail_modal_fetch_shows_loading_state():
    """AC5: Fetch content shows a loading state during the API call."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert ("fetching" in block.lower() or "loading" in block.lower() or
            "crux-spin" in block), (
        "SourceDetailModal must show a loading state while fetching content"
    )


def test_source_detail_modal_fetch_shows_error_on_failure():
    """AC5: Fetch content shows an inline error on failure without closing the modal."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    assert "fetchError" in block or "fetch_error" in block or (
        "role=\"alert\"" in block and "fetch" in block.lower()
    ), (
        "SourceDetailModal must show an inline error message on fetch failure"
    )


# ===========================================================================
# AC7: Null/missing fields render gracefully
# ===========================================================================

def test_source_detail_modal_null_values_show_dash():
    """AC7: Missing/null values display as — or are omitted rather than 'undefined'."""
    src = _src()
    modal_block = re.search(
        r'function SourceDetailModal\(.+?\n\}(?=\n\n// )',
        src,
        re.DOTALL,
    )
    assert modal_block, "SourceDetailModal not found"
    block = modal_block.group(0)
    # Should use || "—" or similar null-coalescing for fields
    assert "—" in block or "\\u2014" in block or "??" in block or '|| ""' in block, (
        "SourceDetailModal must handle null/missing values gracefully (e.g., show — for missing fields)"
    )


# ===========================================================================
# Backend: case detail endpoint returns extracted_content and support_rationale in sources
# ===========================================================================

def test_case_detail_sources_include_extracted_content(api_client, db_session):
    """AC2: Case detail API includes extracted_content in source objects."""
    case, plan, source = _seed_case_with_source(
        db_session,
        extracted_content="This is the extracted text.",
        content_summary="Summary of the article.",
    )

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    plans = data.get("plans", [])
    assert plans, "Case must have plans"
    sources = plans[0].get("sources", [])
    assert sources, "Plan must have sources"
    s = sources[0]
    assert "extracted_content" in s, (
        "Case detail API must include extracted_content in source objects"
    )
    assert s["extracted_content"] == "This is the extracted text."


def test_case_detail_sources_include_content_summary(api_client, db_session):
    """AC2: Case detail API includes content_summary in source objects."""
    case, plan, source = _seed_case_with_source(
        db_session,
        extracted_content="Article text here.",
        content_summary="Article discusses health benefits.",
    )

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    sources = data["plans"][0]["sources"]
    s = sources[0]
    assert "content_summary" in s, (
        "Case detail API must include content_summary in source objects"
    )
    assert s["content_summary"] == "Article discusses health benefits."


def test_case_detail_sources_include_support_rationale(api_client, db_session):
    """AC2: Case detail API includes support_rationale in source objects."""
    case, plan, source = _seed_case_with_source(
        db_session,
        support_rationale="This source directly supports the hypothesis because...",
    )

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    sources = data["plans"][0]["sources"]
    s = sources[0]
    assert "support_rationale" in s, (
        "Case detail API must include support_rationale in source objects"
    )
    assert s["support_rationale"] == "This source directly supports the hypothesis because..."


def test_case_detail_sources_null_extracted_content_is_preserved(api_client, db_session):
    """AC4/AC7: Null extracted_content is passed through (not omitted or falsified)."""
    case, plan, source = _seed_case_with_source(
        db_session,
        extracted_content=None,
    )

    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    sources = data["plans"][0]["sources"]
    s = sources[0]
    assert "extracted_content" in s, "extracted_content key must be present even when null"
    assert s["extracted_content"] is None, "null extracted_content must come through as null"
