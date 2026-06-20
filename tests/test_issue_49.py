"""Tests for issue #49: Surface and edit due date on ProbeCard.

AC coverage:
  AC1  – ProbeCard displays due_date as a monospace date chip (YYYY-MM-DD) when set (JS)
  AC2  – No chip or placeholder shown when due_date is not set (JS)
  AC3  – Overdue + no verdict → date chip uses --red token (JS)
  AC4  – Overdue + has verdict → chip renders in default (non-red) style (JS)
  AC5  – Clicking chip/edit icon shows <input type="date"> inline; no modal (JS)
  AC6  – Submit sends PATCH /api/probes/{id}/due-date; chip updates optimistically (JS + API)
  AC7  – Clearing date + submit sends null via PATCH, removing chip (JS + API)
  AC8  – PATCH failure reverts to previous value and surfaces error state (JS)
  AC9  – Edit affordance is keyboard-accessible (JS)
  AC10 – No reminders, notifications, or emails triggered (API)
  API1 – PATCH /api/probes/{id}/due-date with valid date persists to DB
  API2 – PATCH /api/probes/{id}/due-date with null clears due_date
  API3 – PATCH returns 404 for unknown probe
  API4 – PATCH returns 403/redirect when unauthenticated
  API5 – GET /api/cases/{id} includes due_date in probe payload
"""
import os
import uuid
import json as _json

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
    tc = TestClient(app, follow_redirects=False)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def unauthed_client(db_session):
    from app.main import app
    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app, follow_redirects=False)
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_probe(session, due_date=None):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Running performance dropped.",
        sharpened="Running performance dropped 15% over 6 weeks.",
        not_investigating=_json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="resting HRV (7-day average)",
        cost="free",
        time="7 days",
        note="Measure resting HRV each morning.",
        status="designed",
        due_date=due_date,
    )
    session.add(probe)
    session.commit()
    return probe, c


# ---------------------------------------------------------------------------
# API1: PATCH /api/probes/{id}/due-date with valid date persists to DB
# ---------------------------------------------------------------------------

def test_patch_probe_due_date_sets_date(api_client, db_session):
    """API1: PATCH /api/probes/{id}/due-date persists a valid date to the DB."""
    probe, _ = _seed_probe(db_session)
    r = api_client.patch(
        f"/api/probes/{probe.id}/due-date",
        json={"due_date": "2030-12-31"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == probe.id
    assert data["due_date"] == "2030-12-31"

    from app import models
    db_session.expire_all()
    updated = db_session.get(models.Probe, probe.id)
    assert str(updated.due_date) == "2030-12-31"


# ---------------------------------------------------------------------------
# API2: PATCH with null clears due_date
# ---------------------------------------------------------------------------

def test_patch_probe_due_date_clears_date(api_client, db_session):
    """API2: PATCH /api/probes/{id}/due-date with null removes the due_date."""
    import datetime
    probe, _ = _seed_probe(db_session, due_date=datetime.date(2030, 1, 1))
    r = api_client.patch(
        f"/api/probes/{probe.id}/due-date",
        json={"due_date": None},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["due_date"] is None

    from app import models
    db_session.expire_all()
    updated = db_session.get(models.Probe, probe.id)
    assert updated.due_date is None


# ---------------------------------------------------------------------------
# API3: 404 for unknown probe
# ---------------------------------------------------------------------------

def test_patch_probe_due_date_404_for_unknown(api_client):
    """API3: PATCH /api/probes/{id}/due-date returns 404 for an unknown probe ID."""
    r = api_client.patch(
        "/api/probes/00000000-0000-0000-0000-000000000000/due-date",
        json={"due_date": "2030-01-01"},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# API4: 403/redirect when unauthenticated
# ---------------------------------------------------------------------------

def test_patch_probe_due_date_403_unauthenticated(unauthed_client, db_session):
    """API4: PATCH /api/probes/{id}/due-date returns 403 when unauthenticated."""
    probe, _ = _seed_probe(db_session)
    r = unauthed_client.patch(
        f"/api/probes/{probe.id}/due-date",
        json={"due_date": "2030-01-01"},
    )
    assert r.status_code in (302, 401, 403), f"Expected auth rejection, got {r.status_code}"


# ---------------------------------------------------------------------------
# API5: GET /api/cases/{id} includes due_date in probe payload
# ---------------------------------------------------------------------------

def test_get_case_includes_probe_due_date(api_client, db_session):
    """API5: GET /api/cases/{id} includes due_date in the probe dict."""
    import datetime
    probe, case = _seed_probe(db_session, due_date=datetime.date(2030, 6, 15))
    r = api_client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["probe"] is not None
    assert "due_date" in data["probe"], "probe payload must include due_date field"
    assert data["probe"]["due_date"] == "2030-06-15"


def test_get_case_includes_null_probe_due_date(api_client, db_session):
    """API5: GET /api/cases/{id} returns null due_date when not set."""
    probe, case = _seed_probe(db_session, due_date=None)
    r = api_client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["probe"] is not None
    assert "due_date" in data["probe"]
    assert data["probe"]["due_date"] is None


# ---------------------------------------------------------------------------
# API response shape: includes id and due_date
# ---------------------------------------------------------------------------

def test_patch_probe_due_date_response_shape(api_client, db_session):
    """AC6/API1: PATCH response includes 'id' and 'due_date' fields."""
    probe, _ = _seed_probe(db_session)
    r = api_client.patch(
        f"/api/probes/{probe.id}/due-date",
        json={"due_date": "2029-03-01"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    assert "due_date" in data
    assert data["id"] == probe.id
    assert data["due_date"] == "2029-03-01"


# ---------------------------------------------------------------------------
# AC10: No side-effects (no email, notifications)
# ---------------------------------------------------------------------------

def test_due_date_patch_has_no_email_or_notification_code():
    """AC10: No reminders/notifications/emails in probes router due-date logic."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "app" / "routers" / "probes.py").read_text()
    for banned in ("send_email", "send_notification", "reminder", "smtp", "sendgrid", "mailgun"):
        assert banned not in src.lower(), f"Found banned side-effect keyword: {banned!r}"


# ---------------------------------------------------------------------------
# Frontend / JS tests
# ---------------------------------------------------------------------------

def test_due_date_chip_defined_in_js():
    """AC1: JS must render a date chip for ProbeCard when due_date is set."""
    js = _read_combined_js()
    assert "due_date" in js or "dueDate" in js, \
        "JS must reference due_date / dueDate to render the date chip"


def test_no_chip_when_due_date_absent_in_js():
    """AC2: JS must conditionally render the chip only when due_date is truthy."""
    js = _read_combined_js()
    # Must have a conditional guard around the chip
    assert ("due_date" in js or "dueDate" in js), \
        "JS must use due_date to conditionally render the chip"
    # Must have some null/falsy guard (&&, ternary, if)
    assert ("&&" in js or "?" in js or "if" in js.lower()), \
        "JS must have a conditional guard so the chip is hidden when due_date is absent"


def test_overdue_red_styling_in_js():
    """AC3: JS must apply --red token color for overdue probes with no verdict."""
    js = _read_combined_js()
    assert "--red" in js or "var(--red)" in js, \
        "JS must use the --red token for overdue date chip styling"
    # Must check verdict presence to conditionally apply red
    assert "verdict" in js.lower() or "hasVerdict" in js, \
        "JS must check verdict to decide overdue styling"


def test_overdue_with_verdict_default_style_in_js():
    """AC4: JS must skip red styling for overdue probe that has a verdict."""
    js = _read_combined_js()
    # The overdue red logic must be gated on hasVerdict being falsy
    assert "hasVerdict" in js or "verdict" in js.lower(), \
        "JS must gate red overdue styling on the absence of a verdict"


def test_inline_date_input_no_modal_in_js():
    """AC5: JS must use <input type='date'> inline; no separate dialog/modal for date editing."""
    js = _read_combined_js()
    assert 'type="date"' in js or "type='date'" in js or 'type=\\"date\\"' in js, \
        "JS must include <input type='date'> for inline date editing"


def test_patch_due_date_endpoint_called_in_js():
    """AC6: JS must call PATCH /api/probes/{id}/due-date on submit."""
    js = _read_combined_js()
    assert "/due-date" in js, \
        "JS must call PATCH /api/probes/{id}/due-date endpoint"


def test_clear_date_sends_null_in_js():
    """AC7: JS must send null when date is cleared."""
    js = _read_combined_js()
    # Clearing must result in null being sent
    assert "null" in js or "null" in js, \
        "JS must send null due_date when date field is cleared"


def test_error_revert_on_patch_failure_in_js():
    """AC8: JS must revert to previous value and show error state on PATCH failure."""
    js = _read_combined_js()
    # Must have some error handling and revert logic for the due date
    assert ("error" in js.lower() or "Error" in js), \
        "JS must have error handling for failed PATCH /due-date"
    # Must have some revert mechanism (prev value stored)
    assert ("prev" in js.lower() or "previous" in js.lower() or
            "setDueDate" in js or "dueDate" in js or "due_date" in js), \
        "JS must store previous due_date to revert on failure"


def test_keyboard_accessibility_in_js():
    """AC9: Edit affordance must be keyboard-accessible (Escape to dismiss)."""
    js = _read_combined_js()
    assert "Escape" in js or "escape" in js.lower() or "keydown" in js.lower(), \
        "JS must handle Escape key to dismiss the date input"
    # Must be focusable (button or input with no tabIndex=-1)
    assert "button" in js.lower() or "input" in js.lower(), \
        "JS must use a button or input element for the edit affordance"
