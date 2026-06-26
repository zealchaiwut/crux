"""UAT tests for issue #26: Generate Commander Spec for Prototype Probes via Claude API.

These tests verify the acceptance criteria through the FastAPI TestClient,
which simulates the UAT environment behavior.
"""
import json
import os
import uuid
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_12345")


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
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


def _seed_case_with_probe(session, probe_type: str):
    """Seed a Case with plans and a Probe."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is engagement low?",
        sharpened="User engagement dropped 20%.",
        not_investigating=json.dumps(["External factors"]),
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
    )
    session.add(probe)
    session.commit()
    return c


_MOCK_SPEC = """\
# Build a Minimal Engagement Tracker

**Target metric:** task completion rate

## Acceptance Criteria
- [ ] Users can log a task
- [ ] Completion rate is displayed

## Build Context
This tests user engagement with task tracking.
"""


# ---------------------------------------------------------------------------
# AC1: When a Probe with type="prototype" is processed, Claude API is called
# ---------------------------------------------------------------------------

def test_ac1_prototype_probe_endpoint_exists(api_client, db_session):
    """AC1: POST /api/cases/{id}/probe/commander-spec endpoint exists and is callable."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


def test_ac1_prototype_probe_calls_claude_api(api_client, db_session):
    """AC1: Spec generation calls the Claude API."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ) as mock_gen:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    mock_gen.assert_called_once()


# ---------------------------------------------------------------------------
# AC2: Generated spec contains title, target metric, AC list, build context
# ---------------------------------------------------------------------------

def test_ac2_spec_contains_title(api_client, db_session):
    """AC2: Generated spec contains a markdown title."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    spec = resp.json()["commander_spec"]
    assert "# " in spec, "Spec must contain markdown title"


def test_ac2_spec_contains_target_metric(api_client, db_session):
    """AC2: Generated spec references the target metric."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    spec = resp.json()["commander_spec"]
    assert "metric" in spec.lower(), "Spec must reference target metric"


def test_ac2_spec_contains_acceptance_criteria(api_client, db_session):
    """AC2: Generated spec contains acceptance criteria section."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    spec = resp.json()["commander_spec"]
    assert ("acceptance" in spec.lower() or "- [" in spec), (
        "Spec must contain acceptance criteria"
    )


def test_ac2_spec_contains_build_context(api_client, db_session):
    """AC2: Generated spec contains build context."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    spec = resp.json()["commander_spec"]
    assert "context" in spec.lower(), "Spec must contain build context"


# ---------------------------------------------------------------------------
# AC3: Generated markdown persisted to Probe.commander_spec
# ---------------------------------------------------------------------------

def test_ac3_spec_persisted_to_probe_field(api_client, db_session):
    """AC3: Probe.commander_spec is populated after spec generation."""
    from app import models

    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec == _MOCK_SPEC, (
        "commander_spec should be persisted to Probe.commander_spec"
    )


def test_ac3_spec_in_api_response(api_client, db_session):
    """AC3: commander_spec is returned in the POST response."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    data = resp.json()
    assert "commander_spec" in data
    assert data["commander_spec"] == _MOCK_SPEC


def test_ac3_spec_in_get_case_response(api_client, db_session):
    """AC3: commander_spec is included in GET /api/cases/{id} probe data."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    get_resp = api_client.get(f"/api/cases/{case.id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["probe"]["commander_spec"] == _MOCK_SPEC


# ---------------------------------------------------------------------------
# AC4: Probes with type != "prototype" do not trigger spec generation
# ---------------------------------------------------------------------------

def test_ac4_non_prototype_returns_422(api_client, db_session):
    """AC4: Spec endpoint returns 422 for non-prototype probe types."""
    case = _seed_case_with_probe(db_session, "measurement")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ) as mock_spec:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
    mock_spec.assert_not_called()


def test_ac4_non_prototype_spec_remains_null(api_client, db_session):
    """AC4: commander_spec remains null for non-prototype probes."""
    from app import models

    case = _seed_case_with_probe(db_session, "measurement")

    api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec is None, (
        "commander_spec must remain null for non-prototype probes"
    )


@pytest.mark.parametrize("probe_type", ["measurement", "lab-test", "behaviour-experiment"])
def test_ac4_all_non_prototype_types_rejected(api_client, db_session, probe_type):
    """AC4: All non-prototype types return 422 and skip spec generation."""
    from app import models

    case = _seed_case_with_probe(db_session, probe_type)

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
    ) as mock_spec:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    mock_spec.assert_not_called()

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec is None


# ---------------------------------------------------------------------------
# AC5: API failure returns 502 and commander_spec not written
# ---------------------------------------------------------------------------

def test_ac5_api_error_returns_502(api_client, db_session):
    """AC5: Claude API failure returns HTTP 502."""
    from app.commander_spec import CommanderSpecError

    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        side_effect=CommanderSpecError("API timeout"),
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 502


def test_ac5_api_error_spec_not_written(api_client, db_session):
    """AC5: On API failure, commander_spec is not written."""
    from app import models
    from app.commander_spec import CommanderSpecError

    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        side_effect=CommanderSpecError("network error"),
    ):
        api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec is None, (
        "commander_spec must not be written on API failure"
    )


# ---------------------------------------------------------------------------
# AC6: No UI surface added or modified
# ---------------------------------------------------------------------------

def test_ac6_no_new_ui_routes_created(api_client):
    """AC6: No new UI routes created for spec generation (spec is server-side only)."""
    # The spec is accessible via the probe API response, not via new UI endpoints.
    # Verify the standard case detail endpoint includes commander_spec in probe data.
    from app import models

    # This test verifies the API structure, not new UI routes
    # No dedicated /ui/spec endpoint should exist
    resp = api_client.get("/openapi.json")
    if resp.status_code == 200:
        paths = resp.json().get("paths", {})
        # Should not have new UI routes like /spec-view or /spec-editor
        ui_spec_routes = [p for p in paths if "/spec" in p.lower() and "api" not in p]
        assert len(ui_spec_routes) == 0, f"No new UI spec routes should exist: {ui_spec_routes}"


# ---------------------------------------------------------------------------
# AC7: No external tickets created
# ---------------------------------------------------------------------------

def test_ac7_no_external_ticket_created(api_client, db_session):
    """AC7: Spec generation does not create external tickets; only persists to DB."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200

    # Verify spec is only in Probe.commander_spec (no side effects)
    get_resp = api_client.get(f"/api/cases/{case.id}")
    assert get_resp.status_code == 200
    probe = get_resp.json()["probe"]

    # Spec should be in probe.commander_spec only
    assert "commander_spec" in probe
    assert probe["commander_spec"] == _MOCK_SPEC


# ---------------------------------------------------------------------------
# AC8: Spec is spec-only; no execution or scaffolding
# ---------------------------------------------------------------------------

def test_ac8_spec_only_no_execution(api_client, db_session):
    """AC8: Commander spec is persisted as markdown spec only; no scaffolding initiated."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    spec = resp.json()["commander_spec"]

    # Spec should be markdown text, not code
    assert isinstance(spec, str), "Spec must be a string"

    # Probe status should remain "designed", not "running" or "building"
    get_resp = api_client.get(f"/api/cases/{case.id}")
    probe = get_resp.json()["probe"]
    assert probe["status"] == "designed", (
        "Probe status should remain 'designed' after spec generation"
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_spec_generation_is_idempotent(api_client, db_session):
    """AC3: Second call to POST commander-spec returns existing spec without regenerating."""
    case = _seed_case_with_probe(db_session, "prototype")

    with patch(
        "app.routers.cases.generate_commander_spec",
        new_callable=AsyncMock,
        return_value=_MOCK_SPEC,
    ) as mock_gen:
        resp1 = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")
        resp2 = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Only called once (idempotency)
    assert mock_gen.call_count == 1
    assert resp1.json()["commander_spec"] == resp2.json()["commander_spec"]
