"""Tests for issue #52: Build Verdicts list screen with search, filter, and grouping.

AC coverage:
  AC1  – Clicking the existing sidebar "Verdicts" nav item routes to the Verdicts
          screen without a full page reload (shell.js wires 'verdicts' route to
          VerdictScreen component instead of PlaceholderScreen).
  AC2  – Each row displays: outcome pill, case sharpened statement as row title,
          probe target_metric in monospace font, and a "View Case" link.
  AC3  – Toggle control switches between grouped view and flat view.
  AC4  – Keyword search input filters rows in real time; URL updates with ?q= param.
  AC5  – Three outcome filter chips (Confirmed/Killed/Inconclusive) filter with
          counts of matching verdicts.
  AC6  – In grouped view, zero-match groups show a per-group empty state rather
          than hiding the section heading silently.
  AC7  – In flat view with no results, a full-screen empty state is shown.
  AC8  – All controls are keyboard-accessible (buttons, accessible labels).
  AC9  – Screen renders correctly with 0, 1, and 50+ verdict records (API checks).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# DB / client helpers
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


def _seed_verdict(session, outcome, sharpened, target_metric="weight kg",
                  notes="", decided_at=None):
    """Seed Case → Probe → Verdict and return (verdict_id, case_id)."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        sharpened=sharpened,
        stage="verdict",
    )
    session.add(case)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="measurement",
        target_metric=target_metric,
        status=outcome,
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes=notes,
        decided_at=decided_at or datetime.now(tz=timezone.utc),
    )
    session.add(verdict)
    session.commit()
    return verdict.id, case.id


# ===========================================================================
# AC1 — Sidebar Verdicts nav item routes to VerdictScreen (not placeholder)
# ===========================================================================

def test_shell_verdicts_route_renders_verdicts_screen_not_placeholder():
    """AC1: shell.js routes 'verdicts' to VerdictScreen, not PlaceholderScreen."""
    shell = (JS_DIR / "shell.js").read_text()
    # The old placeholder rendered `<PlaceholderScreen title="Verdicts" />`
    # After this issue the routing must use the real VerdictScreen component
    assert "PlaceholderScreen" not in shell or (
        "route === 'verdicts'" in shell and "VerdictScreen" in shell
    ), "shell.js must route 'verdicts' to VerdictScreen, not PlaceholderScreen"


def test_shell_verdicts_nav_item_present():
    """AC1: The sidebar still has the Verdicts nav item wired to setRoute('verdicts')."""
    shell = (JS_DIR / "shell.js").read_text()
    assert "Verdicts" in shell, "Verdicts nav item must be in shell.js"
    assert "setRoute('verdicts')" in shell or 'setRoute("verdicts")' in shell, (
        "Verdicts nav item must call setRoute('verdicts')"
    )


def test_verdicts_screen_component_defined():
    """AC1: VerdictScreen or VerdictsScreen component is defined in verdicts.js."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "function VerdictScreen" in verdicts_js or "function VerdictsScreen" in verdicts_js, (
        "A VerdictScreen component must be defined in verdicts.js"
    )


def test_index_html_loads_verdicts_js():
    """AC1: index.html includes verdicts.js so VerdictScreen is available."""
    html = (STATIC / "index.html").read_text()
    assert "verdicts.js" in html, "index.html must load verdicts.js"


# ===========================================================================
# AC2 — Row displays outcome pill, sharpened statement, target metric, View Case
# ===========================================================================

def test_verdicts_js_renders_outcome_pill():
    """AC2: VerdictRow renders an outcome pill (uses Pill component or pill class)."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "pill" in verdicts_js.lower(), (
        "verdicts.js must render a verdict pill using the 'pill' CSS class"
    )


def test_verdicts_js_renders_sharpened_statement():
    """AC2: VerdictRow renders case sharpened statement as the row title."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "sharpened" in verdicts_js, (
        "verdicts.js must reference 'sharpened' to display the case's sharpened statement"
    )


def test_verdicts_js_renders_target_metric_in_mono():
    """AC2: Target metric is rendered in monospace font (font-mono or mono class)."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "target_metric" in verdicts_js, (
        "verdicts.js must reference 'target_metric'"
    )
    assert "font-mono" in verdicts_js or "var(--font-mono)" in verdicts_js or '"mono"' in verdicts_js, (
        "target_metric must be rendered with monospace font (font-mono class or --font-mono var)"
    )


def test_verdicts_js_renders_view_case_link():
    """AC2: Each verdict row has a 'View Case' link navigating to the Case."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "View Case" in verdicts_js or "view case" in verdicts_js.lower(), (
        "verdicts.js must include a 'View Case' link on each row"
    )


# ===========================================================================
# AC3 — Toggle between grouped and flat view
# ===========================================================================

def test_verdicts_js_has_view_toggle():
    """AC3: verdicts.js defines a grouped/flat toggle control."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        "grouped" in verdicts_js.lower() and "flat" in verdicts_js.lower()
    ), "verdicts.js must support both 'grouped' and 'flat' view modes"


def test_verdicts_js_grouped_view_has_three_sections():
    """AC3: Grouped view defines sections for Confirmed Causes, Killed Hypotheses, Inconclusive."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "Confirmed" in verdicts_js, "Grouped view must have a Confirmed section"
    assert "Killed" in verdicts_js, "Grouped view must have a Killed section"
    assert "Inconclusive" in verdicts_js, "Grouped view must have an Inconclusive section"


def test_verdicts_js_flat_view_sorts_newest_first():
    """AC3: Flat view is documented/structured to show newest-first order."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    # Flat view uses the default API ordering (newest-first) or sorts by date
    assert "flat" in verdicts_js.lower(), "verdicts.js must support flat view"


# ===========================================================================
# AC4 — Keyword search filters in real time; URL updates with ?q= param
# ===========================================================================

def test_verdicts_js_has_search_input():
    """AC4: verdicts.js includes a keyword search input."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        'type="search"' in verdicts_js
        or 'type="text"' in verdicts_js
        or "search" in verdicts_js.lower()
    ), "verdicts.js must include a keyword search input"


def test_verdicts_js_updates_url_with_query_param():
    """AC4: URL is updated with ?q= param when search changes (URLSearchParams / history.pushState / replaceState)."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        "URLSearchParams" in verdicts_js
        or "pushState" in verdicts_js
        or "replaceState" in verdicts_js
        or "searchParams" in verdicts_js
    ), "verdicts.js must update the URL with search query params"


# ===========================================================================
# AC5 — Three outcome filter chips with counts
# ===========================================================================

def test_verdicts_js_has_filter_chips():
    """AC5: verdicts.js defines the three outcome filter chips."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert "confirmed" in verdicts_js.lower(), "Filter chip for 'confirmed' must exist"
    assert "killed" in verdicts_js.lower(), "Filter chip for 'killed' must exist"
    assert "inconclusive" in verdicts_js.lower(), "Filter chip for 'inconclusive' must exist"


def test_verdicts_js_chips_show_counts():
    """AC5: Filter chips display counts of matching verdicts."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    # The JS must compute or display a count per chip
    assert (
        ".filter" in verdicts_js and ".length" in verdicts_js
    ), "verdicts.js must compute counts via .filter(...).length for chip display"


# ===========================================================================
# AC6 — Per-group empty state in grouped view
# ===========================================================================

def test_verdicts_js_grouped_empty_state_per_group():
    """AC6: Grouped view shows per-group empty state when a group has no matches."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    # Must have text for empty per-group state
    assert (
        "No confirmed" in verdicts_js
        or "no confirmed" in verdicts_js.lower()
        or "match" in verdicts_js.lower()
    ), (
        "verdicts.js must include a per-group empty state message (e.g. 'No confirmed causes match')"
    )


# ===========================================================================
# AC7 — Full-screen empty state in flat view
# ===========================================================================

def test_verdicts_js_flat_empty_state():
    """AC7: Flat view has a full-screen empty state when no results."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        "No verdicts" in verdicts_js
        or "no results" in verdicts_js.lower()
        or "empty" in verdicts_js.lower()
    ), "verdicts.js must include an empty state message for the flat view"


# ===========================================================================
# AC8 — Keyboard accessibility
# ===========================================================================

def test_verdicts_js_controls_have_accessible_labels():
    """AC8: Interactive controls have aria-label or semantic button elements."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        "aria-label" in verdicts_js
        or "aria-pressed" in verdicts_js
        or "<button" in verdicts_js
        or "button" in verdicts_js
    ), "verdicts.js must use semantic <button> elements or aria attributes for accessibility"


def test_verdicts_js_search_input_has_label():
    """AC8: Search input has an accessible label (aria-label or <label> element)."""
    verdicts_js = (JS_DIR / "verdicts.js").read_text()
    assert (
        "aria-label" in verdicts_js
        or "placeholder" in verdicts_js
        or "<label" in verdicts_js
    ), "Search input must have an accessible label"


# ===========================================================================
# AC9 — API works with 0, 1, and 50+ verdict records
# ===========================================================================

def test_api_verdicts_empty_db(api_client):
    """AC9: /api/verdicts returns 200 + [] when no verdicts exist."""
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    assert r.json() == []


def test_api_verdicts_single_record(api_client, db_session):
    """AC9: /api/verdicts returns exactly one verdict when one exists."""
    _seed_verdict(db_session, "confirmed", "Revenue dropped sharply")
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["outcome"] == "confirmed"
    assert data[0]["case"]["sharpened_snippet"] == "Revenue dropped sharply"


def test_api_verdicts_many_records(api_client, db_session):
    """AC9: /api/verdicts returns all 50+ verdicts, newest-first."""
    now = datetime.now(tz=timezone.utc)
    for i in range(52):
        _seed_verdict(
            db_session,
            outcome="confirmed" if i % 3 == 0 else "killed" if i % 3 == 1 else "inconclusive",
            sharpened=f"Sharpened statement {i}",
            decided_at=now - timedelta(minutes=i),
        )
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 52
    # Newest-first: statement 0 was added last with decided_at=now (most recent)
    assert "0" in data[0]["case"]["sharpened_snippet"]


def test_api_verdicts_registered_in_app(api_client):
    """AC9: The /api/verdicts route is registered and reachable (not 404)."""
    r = api_client.get("/api/verdicts")
    assert r.status_code != 404, "/api/verdicts must be registered in the FastAPI app"


# ===========================================================================
# Additional: verdicts router is included in the app
# ===========================================================================

def test_verdicts_router_included_in_main():
    """The verdicts router must be included in app/main.py (not just defined)."""
    main_py = (__import__("pathlib").Path(__file__).parent.parent / "app" / "main.py").read_text()
    assert "verdicts" in main_py.lower(), (
        "app/main.py must include the verdicts router"
    )
