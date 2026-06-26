"""Tests for issue #27: Wire 'Send to commander' on ProbeCard to display spec.

AC coverage (backend-testable aspects):
  AC1 – 'Send to commander' button rendered only for type='prototype' → enforced at
         the API layer: POST /probe/commander-spec returns 422 for non-prototype types.
  AC2 – Clicking the button shows commander_spec: the case detail endpoint returns
         commander_spec in the probe payload so the UI can display it.
  AC4 – Regenerate triggers re-generation: POST /probe/commander-spec accepts
         ?force=true and regenerates even when a spec already exists.
  AC5 – Empty-state when no spec: GET /api/cases/{id} returns commander_spec=null
         for a probe that has never had a spec generated.
  AC7 – Errors during regeneration are surfaced; existing spec preserved: when the
         Claude API call fails, the endpoint returns 502 and the probe's existing
         commander_spec is not overwritten.
  AC8 – No changes to ProbeCard behavior for non-prototype types: non-prototype
         probes cannot trigger spec generation (422).
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_12345")


# ---------------------------------------------------------------------------
# Helpers / fixtures
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


def _seed_case_with_probe(session, probe_type="prototype", commander_spec=None):
    """Seed a Case with plans and a probe, optionally with an existing spec."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is performance dropping?",
        sharpened="Running performance dropped 15% over 6 weeks.",
        not_investigating=json.dumps(["Weather"]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    for i, label in enumerate(["A", "B", "C"]):
        p = models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label=label,
            name=f"Plan {label}",
            mechanism=f"Mechanism {label}",
            prior=str(0.55 - i * 0.2),
            current_rank=i + 1,
        )
        session.add(p)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type=probe_type,
        target_metric="task completion rate",
        cost="~10 hours dev",
        time="1 week",
        note="Build a minimal tracker.",
        status="designed",
        commander_spec=commander_spec,
    )
    session.add(probe)
    session.commit()
    return c, probe


_MOCK_SPEC = """\
# Build a Minimal Engagement Tracker

**Target metric:** task completion rate

## Acceptance Criteria
- [ ] Users can log a task as completed
- [ ] Completion rate is displayed as a percentage

## Build Context
This prototype tests whether users engage with explicit task tracking.
"""

_MOCK_SPEC_REGENERATED = """\
# Build a Minimal Engagement Tracker v2

**Target metric:** task completion rate (refreshed)

## Acceptance Criteria
- [ ] Users can log a task as completed
- [ ] Completion rate is displayed as a percentage

## Build Context
Regenerated spec with fresh context.
"""


# ---------------------------------------------------------------------------
# AC2: case detail endpoint returns commander_spec in probe payload
# ---------------------------------------------------------------------------

def test_case_detail_includes_commander_spec_null_when_not_generated(api_client, db_session):
    """AC5/AC2: GET /api/cases/{id} returns commander_spec=null when no spec generated."""
    case, _ = _seed_case_with_probe(db_session, probe_type="prototype", commander_spec=None)
    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "probe" in body
    assert body["probe"] is not None
    assert "commander_spec" in body["probe"], "probe payload must include commander_spec key"
    assert body["probe"]["commander_spec"] is None, (
        "commander_spec must be null when not yet generated (empty-state trigger for UI)"
    )


def test_case_detail_includes_commander_spec_when_present(api_client, db_session):
    """AC2: GET /api/cases/{id} returns the commander_spec markdown when it exists."""
    case, _ = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=_MOCK_SPEC
    )
    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["probe"]["commander_spec"] == _MOCK_SPEC


# ---------------------------------------------------------------------------
# AC1/AC8: non-prototype probes cannot trigger spec generation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("probe_type", ["measurement", "lab-test", "behaviour-experiment"])
def test_spec_generation_rejected_for_non_prototype(api_client, db_session, probe_type):
    """AC1/AC8: POST /probe/commander-spec returns 422 for non-prototype probe types."""
    case, _ = _seed_case_with_probe(db_session, probe_type=probe_type)
    resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")
    assert resp.status_code == 422, (
        f"Expected 422 for probe type={probe_type!r}; got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert probe_type in detail or "prototype" in detail


# ---------------------------------------------------------------------------
# AC4: Regenerate button triggers re-generation (force=true)
# ---------------------------------------------------------------------------

def test_force_regenerate_overwrites_existing_spec(api_client, db_session):
    """AC4: POST /probe/commander-spec?force=true regenerates even when spec exists."""
    case, probe = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=_MOCK_SPEC
    )

    with patch(
        "app.routers.cases.generate_commander_spec",
        new=AsyncMock(return_value=_MOCK_SPEC_REGENERATED),
    ):
        resp = api_client.post(
            f"/api/cases/{case.id}/probe/commander-spec?force=true"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["commander_spec"] == _MOCK_SPEC_REGENERATED, (
        "force=true must regenerate and return the fresh spec"
    )


def test_without_force_returns_cached_spec(api_client, db_session):
    """AC4 (idempotency): POST without force=true returns cached spec without calling Claude."""
    case, _ = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=_MOCK_SPEC
    )

    with patch(
        "app.routers.cases.generate_commander_spec",
        new=AsyncMock(return_value=_MOCK_SPEC_REGENERATED),
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    body = resp.json()
    assert body["commander_spec"] == _MOCK_SPEC, (
        "Without force=true, existing spec must be returned without calling Claude"
    )
    mock_gen.assert_not_called()


def test_force_regenerate_on_probe_with_no_existing_spec(api_client, db_session):
    """AC4: force=true works even when probe has no existing spec (generates fresh)."""
    case, _ = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=None
    )

    with patch(
        "app.routers.cases.generate_commander_spec",
        new=AsyncMock(return_value=_MOCK_SPEC),
    ):
        resp = api_client.post(
            f"/api/cases/{case.id}/probe/commander-spec?force=true"
        )

    assert resp.status_code == 200
    assert resp.json()["commander_spec"] == _MOCK_SPEC


# ---------------------------------------------------------------------------
# AC7: Errors surfaced; existing spec preserved on regeneration failure
# ---------------------------------------------------------------------------

def test_regeneration_error_preserves_existing_spec(api_client, db_session):
    """AC7: 502 returned on Claude API failure; probe.commander_spec is not overwritten."""
    from app.commander_spec import CommanderSpecError

    case, probe = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=_MOCK_SPEC
    )

    with patch(
        "app.routers.cases.generate_commander_spec",
        new=AsyncMock(side_effect=CommanderSpecError("API timeout")),
    ):
        resp = api_client.post(
            f"/api/cases/{case.id}/probe/commander-spec?force=true"
        )

    assert resp.status_code == 502
    assert "API timeout" in resp.json().get("detail", "")

    # Verify existing spec is still in the DB (not overwritten)
    db_session.expire_all()
    from app import models
    refreshed = db_session.query(models.Probe).filter_by(id=probe.id).one()
    assert refreshed.commander_spec == _MOCK_SPEC, (
        "Existing commander_spec must be preserved when regeneration fails"
    )


def test_regeneration_error_on_no_existing_spec_returns_502(api_client, db_session):
    """AC7: 502 returned on Claude API failure; probe.commander_spec stays null."""
    from app.commander_spec import CommanderSpecError

    case, probe = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=None
    )

    with patch(
        "app.routers.cases.generate_commander_spec",
        new=AsyncMock(side_effect=CommanderSpecError("network error")),
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 502

    db_session.expire_all()
    from app import models
    refreshed = db_session.query(models.Probe).filter_by(id=probe.id).one()
    assert refreshed.commander_spec is None, (
        "commander_spec must remain null after failed generation"
    )


# ---------------------------------------------------------------------------
# AC5: Empty-state — probe with no spec returns null commander_spec
# ---------------------------------------------------------------------------

def test_probe_without_spec_exposes_null_commander_spec_field(api_client, db_session):
    """AC5: Newly created prototype probe has null commander_spec; UI shows empty-state."""
    case, probe = _seed_case_with_probe(
        db_session, probe_type="prototype", commander_spec=None
    )
    resp = api_client.get(f"/api/cases/{case.id}")
    assert resp.status_code == 200
    probe_payload = resp.json()["probe"]
    # The field must exist and be null (not absent) so UI can distinguish
    assert "commander_spec" in probe_payload
    assert probe_payload["commander_spec"] is None
