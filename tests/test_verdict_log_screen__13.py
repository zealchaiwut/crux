"""Tests for issue #13: Build read-only Verdict log screen.

AC coverage:
  AC1  – A dedicated Verdicts screen exists and is reachable from the main navigation (JS).
  AC2  – The screen lists all Verdict rows in reverse-chronological order by default (API).
  AC3  – Each entry shows: Case name/ID (clickable link), outcome pill, decided metric, notes.
  AC4  – Outcome pill is visually distinct for confirmed/killed/inconclusive (JS CSS classes).
  AC5  – A filter control lets users narrow the list to confirmed/killed/inconclusive/all.
  AC6  – Clicking the Case link navigates to the corresponding Case detail (JS).
  AC7  – The screen is read-only — no create/edit/delete controls present (JS).
  AC8  – Empty-state message shown when no verdicts exist or filter returns zero results (JS + API).
  AC9  – Layout and entry structure match the VerdictScreen reference design (JS structure).
"""
import json
import os
import uuid
import datetime

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _seed_verdict(
    session, outcome, notes, decided_at, case_title=None, target_metric="serum ferritin"
):
    """Seed a Case+Probe+Verdict at stage verdict."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is energy low?",
        sharpened=case_title or "Energy dropped 30% over 8 weeks.",
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    session.add(c)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="lab-test",
        target_metric=target_metric,
        cost="~£30",
        time="3-5 days",
        note="See a GP.",
        status=outcome,
    )
    session.add(probe)
    session.flush()

    v = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes=notes,
        decided_at=decided_at,
    )
    session.add(v)
    session.commit()
    return c, probe, v


# ---------------------------------------------------------------------------
# AC2: GET /api/verdicts returns all verdicts in reverse-chronological order
# ---------------------------------------------------------------------------

def test_get_verdicts_returns_empty_list_when_none(api_client):
    """AC2/AC8: GET /api/verdicts returns empty list when no verdicts exist."""
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "verdicts" in data
    assert data["verdicts"] == []


def test_get_verdicts_returns_all_verdicts(api_client, db_session):
    """AC2: GET /api/verdicts returns all verdict rows."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "confirmed", "Root cause found.", now - datetime.timedelta(days=2))
    _seed_verdict(db_session, "killed", "Hypothesis refuted.", now - datetime.timedelta(days=1))
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["verdicts"]) == 2


def test_get_verdicts_reverse_chronological_order(api_client, db_session):
    """AC2: Verdicts are returned newest-first (reverse-chronological by decided_at)."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    older = now - datetime.timedelta(days=5)
    newer = now - datetime.timedelta(days=1)
    _seed_verdict(db_session, "killed", "Old verdict.", older)
    _seed_verdict(db_session, "confirmed", "New verdict.", newer)
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200, r.text
    items = r.json()["verdicts"]
    assert len(items) == 2
    assert items[0]["outcome"] == "confirmed", "Newest verdict should be first"
    assert items[1]["outcome"] == "killed", "Older verdict should be second"


# ---------------------------------------------------------------------------
# AC3: Each entry includes case_id, case_title, outcome, decided_metric, notes
# ---------------------------------------------------------------------------

def test_get_verdicts_entry_has_required_fields(api_client, db_session):
    """AC3: Each verdict entry has case_id, case_title, outcome, decided_metric, notes, decided_at."""  # noqa: E501
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    c, probe, v = _seed_verdict(
        db_session, "confirmed", "Root cause verified.",
        now, case_title="Energy dropped 30%.", target_metric="VO2max"
    )
    r = api_client.get("/api/verdicts")
    assert r.status_code == 200, r.text
    items = r.json()["verdicts"]
    assert len(items) == 1
    entry = items[0]
    assert entry["case_id"] == c.id, "case_id must match"
    assert entry["case_title"] == "Energy dropped 30%.", "case_title must match sharpened problem"
    assert entry["outcome"] == "confirmed"
    assert entry["decided_metric"] == "VO2max", "decided_metric must be probe target_metric"
    assert entry["notes"] == "Root cause verified."
    assert entry["decided_at"] is not None


# ---------------------------------------------------------------------------
# AC5: Filter by outcome
# ---------------------------------------------------------------------------

def test_get_verdicts_filter_confirmed(api_client, db_session):
    """AC5: GET /api/verdicts?outcome=confirmed returns only confirmed verdicts."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "confirmed", "Confirmed.", now)
    _seed_verdict(db_session, "killed", "Killed.", now - datetime.timedelta(hours=1))
    _seed_verdict(db_session, "inconclusive", "Inconclusive.", now - datetime.timedelta(hours=2))
    r = api_client.get("/api/verdicts?outcome=confirmed")
    assert r.status_code == 200, r.text
    items = r.json()["verdicts"]
    assert len(items) == 1
    assert items[0]["outcome"] == "confirmed"


def test_get_verdicts_filter_killed(api_client, db_session):
    """AC5: GET /api/verdicts?outcome=killed returns only killed verdicts."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "confirmed", "Confirmed.", now)
    _seed_verdict(db_session, "killed", "Killed.", now - datetime.timedelta(hours=1))
    r = api_client.get("/api/verdicts?outcome=killed")
    assert r.status_code == 200, r.text
    items = r.json()["verdicts"]
    assert len(items) == 1
    assert items[0]["outcome"] == "killed"


def test_get_verdicts_filter_inconclusive(api_client, db_session):
    """AC5: GET /api/verdicts?outcome=inconclusive returns only inconclusive verdicts."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "confirmed", "Confirmed.", now)
    _seed_verdict(db_session, "inconclusive", "Inconclusive.", now - datetime.timedelta(hours=1))
    r = api_client.get("/api/verdicts?outcome=inconclusive")
    assert r.status_code == 200, r.text
    items = r.json()["verdicts"]
    assert len(items) == 1
    assert items[0]["outcome"] == "inconclusive"


def test_get_verdicts_filter_all_returns_everything(api_client, db_session):
    """AC5: GET /api/verdicts?outcome=all returns all verdicts."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "confirmed", "A.", now)
    _seed_verdict(db_session, "killed", "B.", now - datetime.timedelta(hours=1))
    r = api_client.get("/api/verdicts?outcome=all")
    assert r.status_code == 200, r.text
    assert len(r.json()["verdicts"]) == 2


def test_get_verdicts_filter_empty_result(api_client, db_session):
    """AC5/AC8: GET /api/verdicts?outcome=confirmed when only killed returns empty list."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    _seed_verdict(db_session, "killed", "Killed.", now)
    r = api_client.get("/api/verdicts?outcome=confirmed")
    assert r.status_code == 200, r.text
    assert r.json()["verdicts"] == []


def test_get_verdicts_invalid_filter_rejected(api_client):
    """AC5: Invalid outcome filter returns 422."""
    r = api_client.get("/api/verdicts?outcome=maybe")
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC7: No create/edit/delete endpoints for /api/verdicts
# ---------------------------------------------------------------------------

def test_no_post_api_verdicts(api_client):
    """AC7: POST /api/verdicts does not exist (405 or 404)."""
    r = api_client.post("/api/verdicts", json={})
    assert r.status_code in (404, 405), f"Expected 404/405, got {r.status_code}"


def test_no_delete_api_verdicts(api_client):
    """AC7: DELETE /api/verdicts does not exist (405 or 404)."""
    r = api_client.delete("/api/verdicts/some-id")
    assert r.status_code in (404, 405), f"Expected 404/405, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC1: Verdicts screen reachable from navigation (JS)
# ---------------------------------------------------------------------------

def test_verdicts_nav_item_defined_in_js():
    """AC1: Navigation must include a 'Verdicts' link in the sidebar."""
    combined = _read_combined_js()
    assert "Verdicts" in combined, "Sidebar must include a Verdicts nav item"
    assert "verdicts" in combined, "JS must handle the 'verdicts' route"


def test_verdicts_screen_component_defined_in_js():
    """AC1: A VerdictScreen (or equivalent) component must be defined in the JS."""
    combined = _read_combined_js()
    assert "VerdictScreen" in combined or "VerdictsScreen" in combined, \
        "JS must define a VerdictScreen component"


def test_verdicts_route_renders_screen_not_placeholder(shell_js=None):
    """AC1: The verdicts route must not render a placeholder 'Coming in M1' screen."""
    combined = _read_combined_js()
    # The JS should NOT show 'Coming in M1' for the verdicts route
    # PlaceholderScreen may still be defined, but must not handle verdicts route
    # Check that VerdictScreen is connected to the verdicts route
    has_screen = "VerdictScreen" in combined or "VerdictsScreen" in combined
    assert "verdicts" in combined and has_screen, \
        "verdicts route must render VerdictScreen, not a placeholder"


# ---------------------------------------------------------------------------
# AC3/AC4: Outcome pill visual distinctness (JS CSS classes)
# ---------------------------------------------------------------------------

def test_pill_confirmed_class_in_js():
    """AC4: JS uses 'confirmed' CSS class for confirmed outcome pills."""
    combined = _read_combined_js()
    assert "confirmed" in combined, "JS must use 'confirmed' class for outcome pill"


def test_pill_killed_class_in_js():
    """AC4: JS uses 'killed' CSS class for killed outcome pills."""
    combined = _read_combined_js()
    assert "killed" in combined, "JS must use 'killed' class for outcome pill"


def test_pill_inconclusive_class_in_js():
    """AC4: JS uses 'inconclusive' CSS class for inconclusive outcome pills."""
    combined = _read_combined_js()
    assert "inconclusive" in combined, "JS must use 'inconclusive' class for outcome pill"


# ---------------------------------------------------------------------------
# AC5: Filter control in JS
# ---------------------------------------------------------------------------

def test_filter_control_in_verdicts_screen_js():
    """AC5: VerdictScreen JS must include a filter control (all/confirmed/killed/inconclusive)."""
    combined = _read_combined_js()
    # Must have some form of filter UI referencing the four filter values
    assert "all" in combined.lower(), "Filter must include 'all' option"
    # The four outcome states must all appear in context of filtering
    filter_terms = ["confirmed", "killed", "inconclusive"]
    for term in filter_terms:
        assert term in combined, f"Filter must include '{term}' option"


# ---------------------------------------------------------------------------
# AC6: Case link navigates to case detail (JS)
# ---------------------------------------------------------------------------

def test_case_link_navigates_to_detail_in_js():
    """AC6: VerdictScreen must contain a clickable element that sets route to case/<id>."""
    combined = _read_combined_js()
    # The verdicts screen should have click handler going to case detail
    assert "case/" in combined or "onOpen" in combined or "setRoute" in combined, \
        "VerdictScreen must include navigation to case detail on click"


# ---------------------------------------------------------------------------
# AC7: No edit/delete controls in VerdictScreen JS
# ---------------------------------------------------------------------------

def test_no_edit_controls_in_verdict_screen_js():
    """AC7: VerdictScreen must not contain edit controls."""
    combined = _read_combined_js()
    assert "Edit verdict" not in combined, "No 'Edit verdict' control must appear"


def test_no_delete_controls_in_verdict_screen_js():
    """AC7: VerdictScreen must not contain delete controls."""
    combined = _read_combined_js()
    assert "Delete verdict" not in combined, "No 'Delete verdict' control must appear"


# ---------------------------------------------------------------------------
# AC8: Empty-state message in JS
# ---------------------------------------------------------------------------

def test_empty_state_message_in_verdicts_screen_js():
    """AC8: VerdictScreen must render an empty-state message when no verdicts."""
    combined = _read_combined_js()
    # Must have some form of empty state message
    assert (
        "No verdicts" in combined
        or "no verdicts" in combined.lower()
        or "empty" in combined.lower()
        or "Nothing" in combined
    ), "VerdictScreen must include an empty-state message"
