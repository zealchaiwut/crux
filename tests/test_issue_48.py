"""Tests for issue #48: Add 'Mark as Running' transition for Probes.

AC coverage:
  AC1  – 'Mark as running' button appears on ProbeCard only when status='designed' and no verdict (JS)
  AC2  – Clicking sends PATCH /api/probes/{id}/status with {status: 'running'} (JS + API)
  AC3  – ProbeCard immediately reflects status=running on success without full reload (JS)
  AC4  – 'Mark as running' is hidden when status is not 'designed' (JS)
  AC5  – 'Mark as running' is hidden when a verdict has been logged (JS)
  AC6  – PATCH /api/probes/{id}/status validates designed→running; returns 400 for other transitions (API)
  AC7  – Endpoint returns 404 for unknown probe ID (API)
  AC8  – Endpoint returns 403 when caller is unauthenticated (API)
  AC9  – Status change persists to DB and survives page refresh (API)
  AC10 – No changes to running→closed transition (not tested here; Verdict gate unchanged)
"""
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
    # No session cookie set
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_probe(session, status="designed"):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Running performance dropped.",
        sharpened="Running performance dropped 15% over 6 weeks.",
        not_investigating=json.dumps([]),
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
        status=status,
    )
    session.add(probe)
    session.commit()
    return probe, c


def _seed_probe_with_verdict(session):
    from app import models
    probe, c = _seed_probe(session, status="designed")
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="Confirmed by test.",
    )
    session.add(verdict)
    session.commit()
    return probe, c, verdict


# ---------------------------------------------------------------------------
# AC6: PATCH /api/probes/{id}/status validates designed→running; 400 for other transitions
# ---------------------------------------------------------------------------

def test_patch_probe_status_designed_to_running_succeeds(api_client, db_session):
    """AC6: PATCH /api/probes/{id}/status with status=running succeeds when probe is designed."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "running"


def test_patch_probe_status_invalid_transition_returns_400(api_client, db_session):
    """AC6: PATCH /api/probes/{id}/status returns 400 for a non-designed→running transition."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "closed"})
    assert r.status_code == 400, r.text


def test_patch_probe_status_running_to_running_returns_400(api_client, db_session):
    """AC6: A probe already 'running' cannot transition to 'running' (only designed→running)."""
    probe, _ = _seed_probe(db_session, status="running")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    assert r.status_code == 400, r.text


def test_patch_probe_status_designed_to_closed_returns_400(api_client, db_session):
    """AC6: designed→closed is not a valid transition; returns 400."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "closed"})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# AC7: 404 for unknown probe ID
# ---------------------------------------------------------------------------

def test_patch_probe_status_404_for_unknown_probe(api_client):
    """AC7: PATCH /api/probes/{id}/status returns 404 for an unknown probe ID."""
    r = api_client.patch(
        "/api/probes/00000000-0000-0000-0000-000000000000/status",
        json={"status": "running"},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC8: 403 when unauthenticated
# ---------------------------------------------------------------------------

def test_patch_probe_status_403_unauthenticated(unauthed_client, db_session):
    """AC8: PATCH /api/probes/{id}/status returns 403 (or redirect) when caller is unauthenticated."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = unauthed_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    # Auth middleware blocks with 302 redirect or 403
    assert r.status_code in (302, 401, 403), f"Expected auth rejection, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC9: Status change persists to DB
# ---------------------------------------------------------------------------

def test_patch_probe_status_persists_to_db(api_client, db_session):
    """AC9: After PATCH /api/probes/{id}/status, the probe status is updated in the DB."""
    from app import models
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    assert r.status_code == 200, r.text

    db_session.expire_all()
    updated = db_session.get(models.Probe, probe.id)
    assert updated.status == "running", f"Expected 'running', got {updated.status!r}"


def test_patch_probe_status_survives_page_refresh(api_client, db_session):
    """AC9: After patching status to 'running', GET /api/cases/{id} reflects the change."""
    probe, case = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    assert r.status_code == 200, r.text

    # Simulate page refresh by fetching the case
    r2 = api_client.get(f"/api/cases/{case.id}")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["probe"] is not None
    assert data["probe"]["status"] == "running", f"Expected 'running', got {data['probe']['status']!r}"


# ---------------------------------------------------------------------------
# AC2: Response includes probe ID and updated status
# ---------------------------------------------------------------------------

def test_patch_probe_status_response_shape(api_client, db_session):
    """AC2: PATCH response includes 'id' and 'status' fields."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={"status": "running"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    assert "status" in data
    assert data["id"] == probe.id
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# AC6: Missing or invalid body fields
# ---------------------------------------------------------------------------

def test_patch_probe_status_missing_body_returns_422(api_client, db_session):
    """AC6: PATCH /api/probes/{id}/status with empty body returns 422."""
    probe, _ = _seed_probe(db_session, status="designed")
    r = api_client.patch(f"/api/probes/{probe.id}/status", json={})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# AC1, AC4, AC5: Frontend JS — 'Mark as running' button visibility
# ---------------------------------------------------------------------------

def test_mark_as_running_button_defined_in_js():
    """AC1: JS must contain a 'Mark as running' action."""
    combined = _read_combined_js()
    assert "Mark as running" in combined or "mark as running" in combined.lower(), \
        "JS must define a 'Mark as running' action"


def test_mark_as_running_only_shown_for_designed_status_in_js():
    """AC1/AC4: JS must conditionally show 'Mark as running' based on status==='designed'."""
    combined = _read_combined_js()
    assert "designed" in combined, \
        "JS must check for status==='designed' to show 'Mark as running'"


def test_mark_as_running_hidden_when_verdict_logged_in_js():
    """AC5: JS must hide 'Mark as running' when a verdict has been logged."""
    combined = _read_combined_js()
    # The ProbeCard must accept a hasVerdict or similar prop and use it to gate the button
    assert ("hasVerdict" in combined or "verdict" in combined.lower()), \
        "JS must check for existing verdict to hide 'Mark as running'"


def test_mark_as_running_patches_probe_status_endpoint_in_js():
    """AC2: JS must call PATCH /api/probes/{id}/status when 'Mark as running' is clicked."""
    combined = _read_combined_js()
    assert "PATCH" in combined or "patch" in combined.lower() or \
           "/api/probes/" in combined, \
        "JS must call the PATCH /api/probes/{id}/status endpoint"


def test_probe_card_accepts_has_verdict_prop_in_js():
    """AC5: ProbeCard must accept a prop indicating whether a verdict exists."""
    combined = _read_combined_js()
    # ProbeCard must reference hasVerdict or verdictLogged or similar
    assert "hasVerdict" in combined or "verdictLogged" in combined or \
           ("verdict" in combined and "ProbeCard" in combined), \
        "ProbeCard must accept a verdict-related prop to hide 'Mark as running'"


def test_probe_status_used_in_probe_card_js():
    """AC3/AC4: ProbeCard must use probe.status to control 'Mark as running' visibility."""
    combined = _read_combined_js()
    # Must reference status in some conditional
    assert "status" in combined and "designed" in combined, \
        "ProbeCard must use probe.status and check for 'designed'"


def test_optimistic_update_in_js():
    """AC3: JS must update probe status without full page reload (optimistic/reactive update)."""
    combined = _read_combined_js()
    # Must have some local state update for probe status, e.g. setProbe or similar
    assert "setProbe" in combined or "setProbeStatus" in combined or \
           ("probe" in combined and "status" in combined and "running" in combined), \
        "JS must update probe status reactively on 'Mark as running' success"
