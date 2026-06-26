"""Tests for issue #73: Clarify intent of open/closed stats after filtering.

AC coverage:
  AC1 – The `open` and `closed` variables in CasesScreen are actively used in
         the JSX — not orphaned computed-but-discarded assignments.
  AC2 – N/A (variables are retained, not removed); `visibleCases` filtering
         logic is intact and functions as the data source for both variables.
  AC3 – `open` and `closed` are derived from `visibleCases` (the already-filtered
         list) so their counts reflect the current filter state in real time.
  AC4 – Section headers show "OPEN · {open.length}" and "CLOSED · {closed.length}"
         as the only count display — no separate total-count indicator exists that
         would confuse users about whether counts are filtered or global.
  AC5 – `open` and `closed` are defined before use; no undefined-variable
         references exist in the CasesScreen code path.
"""
import os
import pathlib
import re
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cases_js() -> str:
    return (STATIC_JS / "cases.js").read_text()


def _cases_screen_body() -> str:
    src = _cases_js()
    idx = src.find("function CasesScreen")
    assert idx != -1, "CasesScreen function must be defined in cases.js"
    return src[idx:]


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
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _add_case(db_session, **kwargs):
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem=kwargs.get("raw_problem", "test problem"),
        sharpened=kwargs.get("sharpened", "sharpened problem"),
        stage=kwargs.get("stage", "sharpened"),
    )
    db_session.add(c)
    db_session.flush()
    return c


def _add_probe(db_session, case_id, status="designed"):
    from app import models

    p = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case_id,
        type="measurement",
        status=status,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _add_verdict(db_session, probe_id, outcome):
    from app import models

    v = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe_id,
        outcome=outcome,
    )
    db_session.add(v)
    db_session.flush()
    return v


# ---------------------------------------------------------------------------
# AC1 – `open` and `closed` are actively used, not orphaned assignments
# ---------------------------------------------------------------------------

def test_open_variable_used_in_conditional_render():
    """AC1: `open` drives conditional rendering (open.length > 0 &&) in CasesScreen."""
    body = _cases_screen_body()
    assert re.search(r'open\.length\s*>', body), (
        "CasesScreen must use `open.length` in a conditional — otherwise the "
        "'open' variable is computed but never consumed."
    )


def test_open_variable_used_for_count_display():
    """AC1: `open` count is rendered in the UI (OPEN · {open.length})."""
    body = _cases_screen_body()
    assert "open.length" in body, (
        "CasesScreen must render `open.length` in the OPEN section header."
    )
    assert "OPEN" in body, (
        "CasesScreen must render an 'OPEN' section header."
    )


def test_open_variable_used_in_map():
    """AC1: `open.map(...)` renders the open case cards — not a dead variable."""
    body = _cases_screen_body()
    assert "open.map(" in body, (
        "CasesScreen must call `open.map(...)` to render open case cards."
    )


def test_closed_variable_used_in_conditional_render():
    """AC1: `closed` drives conditional rendering (closed.length > 0 &&) in CasesScreen."""
    body = _cases_screen_body()
    assert re.search(r'closed\.length\s*>', body), (
        "CasesScreen must use `closed.length` in a conditional — otherwise the "
        "'closed' variable is computed but never consumed."
    )


def test_closed_variable_used_for_count_display():
    """AC1: `closed` count is rendered in the UI (CLOSED · {closed.length})."""
    body = _cases_screen_body()
    assert "closed.length" in body, (
        "CasesScreen must render `closed.length` in the CLOSED section header."
    )
    assert "CLOSED" in body, (
        "CasesScreen must render a 'CLOSED' section header."
    )


def test_closed_variable_used_in_map():
    """AC1: `closed.map(...)` renders the closed case cards — not a dead variable."""
    body = _cases_screen_body()
    assert "closed.map(" in body, (
        "CasesScreen must call `closed.map(...)` to render closed case cards."
    )


# ---------------------------------------------------------------------------
# AC3 – `open` and `closed` derive from `visibleCases` (the filtered list)
# ---------------------------------------------------------------------------

def test_open_derives_from_visible_cases():
    """AC3: `open` is filtered from `visibleCases`, not from a separate unfiltered source."""
    body = _cases_screen_body()
    # The open assignment must reference visibleCases on the right-hand side
    match = re.search(r'const\s+open\s*=\s*visibleCases\.filter', body)
    assert match, (
        "CasesScreen must define `open` as `visibleCases.filter(...)` so it "
        "reflects the current filter state, not a stale unfiltered set."
    )


def test_closed_derives_from_visible_cases():
    """AC3: `closed` is filtered from `visibleCases`, not from a separate unfiltered source."""
    body = _cases_screen_body()
    match = re.search(r'const\s+closed\s*=\s*visibleCases\.filter', body)
    assert match, (
        "CasesScreen must define `closed` as `visibleCases.filter(...)` so it "
        "reflects the current filter state, not a stale unfiltered set."
    )


def test_visible_cases_derives_from_filtered_cases():
    """AC3: `visibleCases` comes from `filteredCases` — the memoised, fully-filtered list."""
    body = _cases_screen_body()
    match = re.search(r'const\s+visibleCases\s*=\s*filteredCases', body)
    assert match, (
        "CasesScreen must set `visibleCases = filteredCases || []` so that "
        "both `open` and `closed` reflect active search/filter criteria."
    )


def test_filtered_cases_uses_usememo():
    """AC3: `filteredCases` is memoised with React.useMemo so counts update reactively."""
    body = _cases_screen_body()
    assert "useMemo" in body or "React.useMemo" in body, (
        "filteredCases must use React.useMemo to recompute whenever "
        "search/filter state changes."
    )


def test_api_returns_verdict_field_for_open_case(api_client, db_session):
    """AC3: /api/cases returns `verdict` field so JS can filter into open/closed buckets."""
    _add_case(db_session, sharpened="No probe — awaiting")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert "verdict" in cases[0], (
        "API must return a 'verdict' field on each case so CasesScreen can "
        "classify it into the open or closed bucket."
    )
    assert cases[0]["verdict"] == "awaiting"


def test_api_returns_verdict_log_null_for_open_case(api_client, db_session):
    """AC3: /api/cases returns verdict_log=null for open cases (used by `closed` filter)."""
    _add_case(db_session, sharpened="Open case")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert cases[0]["verdict_log"] is None, (
        "Open cases must have verdict_log=null so `closed` filter correctly "
        "excludes them."
    )


def test_api_returns_verdict_log_for_closed_case(api_client, db_session):
    """AC3: /api/cases returns non-null verdict_log for cases with a logged verdict."""
    c = _add_case(db_session, sharpened="Closed case")
    p = _add_probe(db_session, c.id, status="running")
    _add_verdict(db_session, p.id, "confirmed")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict_log"] is not None, (
        "Cases with a logged verdict must return a non-null verdict_log so the "
        "'closed' filter correctly includes them."
    )
    assert cases[0]["verdict_log"]["outcome"] == "confirmed"


# ---------------------------------------------------------------------------
# AC4 – No separate total-count display alongside the filtered counts
# ---------------------------------------------------------------------------

def test_no_total_cases_count_displayed_separately():
    """AC4: CasesScreen must not show a global total case count separate from open/closed counts."""
    body = _cases_screen_body()
    # Cases.length or cases.length used as a count displayed to the user would
    # be a total-count indicator that would confuse users when filters are active.
    # It is acceptable to use cases.length in boolean guards (cases.length === 0)
    # but not to render it as a numeric count in the UI.
    # Look for patterns like {cases.length} or {totalCases} inside JSX text nodes.
    suspicious = re.findall(r'\{(?:cases|allCases|totalCases)\.length\}', body)
    assert not suspicious, (
        f"CasesScreen must not render a global case count {suspicious!r} "
        "alongside the filtered open/closed counts — users would be confused "
        "about whether displayed numbers reflect the current filter or the full dataset."
    )


def test_open_count_is_only_count_in_open_section_header():
    """AC4: The OPEN section header shows `open.length` as its count — no total mixed in."""
    body = _cases_screen_body()
    # Find the OPEN · ... header pattern and ensure the count is open.length
    open_section = re.search(r'OPEN\s*[·•]\s*\{([^}]+)\}', body)
    assert open_section, (
        "CasesScreen must render an 'OPEN · {count}' section header."
    )
    count_expr = open_section.group(1).strip()
    assert count_expr == "open.length", (
        f"The OPEN section header count must be {{open.length}} (filtered count), "
        f"got {{{count_expr}}}."
    )


def test_closed_count_is_only_count_in_closed_section_header():
    """AC4: The CLOSED section header shows `closed.length` as its count — no total mixed in."""
    body = _cases_screen_body()
    closed_section = re.search(r'CLOSED\s*[·•]\s*\{([^}]+)\}', body)
    assert closed_section, (
        "CasesScreen must render a 'CLOSED · {count}' section header."
    )
    count_expr = closed_section.group(1).strip()
    assert count_expr == "closed.length", (
        f"The CLOSED section header count must be {{closed.length}} (filtered count), "
        f"got {{{count_expr}}}."
    )


# ---------------------------------------------------------------------------
# AC5 – Variables defined before use; no undefined references
# ---------------------------------------------------------------------------

def test_open_defined_before_jsx_use():
    """AC5: `open` is defined (const open = ...) before it appears in JSX."""
    body = _cases_screen_body()
    define_pos = body.find("const open = ")
    use_pos = body.find("open.length")
    assert define_pos != -1, "CasesScreen must define `const open = ...`"
    assert use_pos != -1, "CasesScreen must use `open.length` in JSX"
    assert define_pos < use_pos, (
        "`open` must be defined before it is used in JSX to avoid undefined references."
    )


def test_closed_defined_before_jsx_use():
    """AC5: `closed` is defined (const closed = ...) before it appears in JSX."""
    body = _cases_screen_body()
    # Find the CasesScreen-specific `const closed =` (not the CaseCard one)
    # by looking for the one after `const visibleCases`
    visible_pos = body.find("const visibleCases")
    assert visible_pos != -1, "CasesScreen must define `const visibleCases`"
    define_pos = body.find("const closed = ", visible_pos)
    use_pos = body.find("closed.length")
    assert define_pos != -1, (
        "CasesScreen must define `const closed = ...` after `visibleCases`"
    )
    assert use_pos != -1, "CasesScreen must use `closed.length` in JSX"
    assert define_pos < use_pos, (
        "`closed` must be defined before it is used in JSX to avoid undefined references."
    )


def test_open_filter_references_valid_verdict_strings():
    """AC5: The `open` filter uses verdict strings that the API actually returns."""
    body = _cases_screen_body()
    # Find the start of the open filter block and inspect the following 200 chars
    open_start = re.search(r'const\s+open\s*=\s*visibleCases\.filter', body)
    assert open_start, "CasesScreen must define `open` via `visibleCases.filter(...)`"
    # Grab a generous window after the definition to capture multi-line expressions
    window = body[open_start.start(): open_start.start() + 200]
    assert '"progress"' in window or "'progress'" in window, (
        'The `open` filter must include "progress" (running probe, no verdict).'
    )
    assert '"awaiting"' in window or "'awaiting'" in window, (
        'The `open` filter must include "awaiting" (no probe or designed probe).'
    )


def test_closed_filter_references_verdict_log():
    """AC5: The `closed` filter checks `verdict_log` — the field the API returns for closed cases."""
    body = _cases_screen_body()
    closed_start = re.search(r'const\s+closed\s*=\s*visibleCases\.filter', body)
    assert closed_start, "CasesScreen must define `closed` via `visibleCases.filter(...)`"
    # Grab a generous window after the definition to capture the filter body
    window = body[closed_start.start(): closed_start.start() + 200]
    assert "verdict_log" in window, (
        "The `closed` filter must check `verdict_log` — the field the API sets "
        "when a case has a logged verdict."
    )
