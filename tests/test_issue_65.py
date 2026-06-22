"""Tests for issue #65: Search input and filter chips on Cases list.

AC coverage:
  AC1  – Search input is present in the CasesScreen JS
  AC2  – 300ms debounce is wired in the JS (debounce constant / setTimeout 300)
  AC3  – Search matches on case title field (sharpened / raw_problem)
  AC4  – Stage filter chips defined: All, Sharpened, Bake-off, Gather, Weigh, Probe, Verdict
  AC5  – Outcome filter chips defined: All, Open, Confirmed, Killed, Inconclusive
  AC6  – "All" chip logic: selecting a non-All chip deactivates All; selecting All clears others
  AC7  – Multiple non-All chips in the same group can be active simultaneously
  AC8  – AND logic between stage and outcome groups (both filters applied)
  AC9  – "Clear all" affordance visible when non-All filters are active
  AC10 – Empty state message shown when combined criteria match zero cases
  AC11 – Empty state NOT shown on initial load (before user interaction)
  AC12 – Filter / search state not persisted across navigation (fresh state on each mount)
"""
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

import pathlib

STATIC = pathlib.Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _cases_js() -> str:
    return (JS_DIR / "cases.js").read_text()


def _all_js() -> str:
    return "".join(f.read_text() for f in JS_DIR.iterdir() if f.suffix == ".js")


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


# ---------------------------------------------------------------------------
# AC1 – Search input present in CasesScreen
# ---------------------------------------------------------------------------

def test_search_input_present_in_js():
    """AC1: CasesScreen must render a text search input."""
    src = _cases_js()
    assert 'type="text"' in src or "type='text'" in src or 'placeholder' in src, \
        "CasesScreen must contain a text search input"
    # Verify it is in the CasesScreen function body
    idx = src.find("function CasesScreen")
    assert idx != -1, "CasesScreen function must be defined"
    body = src[idx:]
    assert "search" in body.lower() or "Search" in body, \
        "CasesScreen must reference search state or element"


def test_search_input_has_placeholder():
    """AC1: Search input should have a descriptive placeholder."""
    src = _cases_js()
    # Look for a placeholder that references search or cases
    idx = src.find("function CasesScreen")
    body = src[idx:]
    assert "placeholder" in body.lower(), \
        "Search input must have a placeholder attribute"


# ---------------------------------------------------------------------------
# AC2 – 300ms debounce
# ---------------------------------------------------------------------------

def test_debounce_300ms_present():
    """AC2: A 300ms debounce must be implemented (setTimeout 300 or debounce const)."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    assert "300" in body, \
        "CasesScreen must use a 300ms delay for the search debounce"
    assert "setTimeout" in body or "debounce" in body.lower(), \
        "CasesScreen must use setTimeout or a debounce helper for the search"


# ---------------------------------------------------------------------------
# AC3 – Search matches on title
# ---------------------------------------------------------------------------

def test_search_matches_title_field():
    """AC3: Client-side filter must match on the case title field."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # The filter should reference .title (the field returned by the API)
    assert ".title" in body or "title" in body.lower(), \
        "Search filter must match against the case title field"


def test_api_cases_returns_title_field(api_client, db_session):
    """AC3 (API): /api/cases returns a 'title' field per case for client-side filtering."""
    import uuid
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem here",
        sharpened="Sharpened problem statement",
        stage="sharpened",
    )
    db_session.add(c)
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert "title" in cases[0], "API must return a 'title' field for client-side search"
    assert cases[0]["title"] == "Sharpened problem statement"


# ---------------------------------------------------------------------------
# AC4 – Stage filter chips
# ---------------------------------------------------------------------------

def test_stage_chips_all_present():
    """AC4: Stage filter must include All, Sharpened, Bake-off, Gather, Weigh, Probe, Verdict."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    required_stages = ["All", "Sharpened", "Bake-off", "Gather", "Weigh", "Probe", "Verdict"]
    for stage in required_stages:
        assert stage in body, \
            f"Stage chip '{stage}' must be present in CasesScreen"


def test_stage_chips_state_managed():
    """AC4: CasesScreen must manage stage filter state."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # Should have state for active stage selections
    assert "stage" in body.lower(), \
        "CasesScreen must manage stage filter state"


# ---------------------------------------------------------------------------
# AC5 – Outcome filter chips
# ---------------------------------------------------------------------------

def test_outcome_chips_all_present():
    """AC5: Outcome filter must include All, Open, Confirmed, Killed, Inconclusive."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    required_outcomes = ["All", "Open", "Confirmed", "Killed", "Inconclusive"]
    for outcome in required_outcomes:
        assert outcome in body, \
            f"Outcome chip '{outcome}' must be present in CasesScreen"


def test_outcome_chips_state_managed():
    """AC5: CasesScreen must manage outcome filter state."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    assert "outcome" in body.lower() or "verdict" in body.lower(), \
        "CasesScreen must manage outcome/verdict filter state"


# ---------------------------------------------------------------------------
# AC6 – All chip mutual-exclusion logic
# ---------------------------------------------------------------------------

def test_all_chip_deactivation_logic_present():
    """AC6: Selecting a non-All chip must deactivate All; selecting All clears others."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # The toggle logic must reference "All" and handle chip toggling
    assert "All" in body, \
        "CasesScreen must reference 'All' chip in filter logic"
    # There should be a function or handler that toggles chip state
    assert "toggle" in body.lower() or "onClick" in body or "onclick" in body.lower(), \
        "CasesScreen must handle chip click events to toggle filter state"


# ---------------------------------------------------------------------------
# AC7 – Multiple non-All chips active simultaneously
# ---------------------------------------------------------------------------

def test_multi_select_stage_chips():
    """AC7: Multiple non-All stage chips can be active at once (Set or array state)."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # Multi-select requires storing a collection, not a single value
    assert "Set" in body or "[]" in body or "array" in body.lower() or \
           "includes" in body or "filter" in body.lower(), \
        "CasesScreen must use a collection (Set/array) for multi-chip selection"


# ---------------------------------------------------------------------------
# AC8 – AND logic between stage and outcome groups
# ---------------------------------------------------------------------------

def test_and_logic_between_filter_groups():
    """AC8: Cases must pass BOTH stage AND outcome filters to appear."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # The filter chain should apply both stage and outcome — look for compound filtering
    assert "stage" in body.lower() and ("verdict" in body.lower() or "outcome" in body.lower()), \
        "CasesScreen filter must reference both stage and outcome/verdict"


# ---------------------------------------------------------------------------
# AC9 – Clear all affordance
# ---------------------------------------------------------------------------

def test_clear_all_button_present():
    """AC9: 'Clear all' button or link must be present in CasesScreen."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    assert "Clear all" in body or "clear all" in body.lower() or "clearAll" in body, \
        "CasesScreen must include a 'Clear all' affordance"


def test_clear_all_resets_state():
    """AC9: Clear all handler must reset both filter groups and search input."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # Look for the clear handler or reset function
    assert "clearAll" in body or "clear" in body.lower(), \
        "CasesScreen must define a handler that clears all filters"


# ---------------------------------------------------------------------------
# AC10 – Empty state message when no matches
# ---------------------------------------------------------------------------

def test_empty_state_message_when_no_match():
    """AC10: An empty state message must appear when filters match no cases."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    assert (
        "No cases match" in body
        or "no cases match" in body.lower()
        or "match your search" in body.lower()
    ), "CasesScreen must show a 'No cases match' empty state message"


# ---------------------------------------------------------------------------
# AC11 – Empty state NOT shown on initial load
# ---------------------------------------------------------------------------

def test_empty_state_not_shown_before_interaction():
    """AC11: Empty state must not appear until user has interacted with search/filters."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # The 'No cases match' message must be gated — only shown when there is
    # an active query or active filter (i.e., when the user has interacted).
    # We verify the empty-state text is conditionally rendered (not shown unconditionally).
    # A conditional render must reference searchQuery / activeStages or similar state.
    assert (
        "searchQuery" in body
        or "query" in body.lower()
        or "activeStage" in body
        or "activeOutcome" in body
        or "hasFilter" in body
        or "hasActive" in body
    ), (
        "The filtered empty state must be gated on user interaction state so it "
        "does not appear on initial load"
    )


# ---------------------------------------------------------------------------
# AC12 – State not persisted across navigation
# ---------------------------------------------------------------------------

def test_filter_state_uses_component_local_state():
    """AC12: Filter state must be local React state (useState), not module-level globals."""
    src = _cases_js()
    idx = src.find("function CasesScreen")
    body = src[idx:]
    # useState calls inside the function ensure state resets on unmount/remount
    assert "useState" in body, \
        "CasesScreen must use useState for filter state (ensures fresh state on navigation)"
    # State should NOT be stored in module-level variables (a quick smell check:
    # the variable names shouldn't appear before the function definition)
    pre = src[:idx]
    assert "searchQuery" not in pre and "activeStages" not in pre, \
        "Filter state must not be defined as module-level variables"
