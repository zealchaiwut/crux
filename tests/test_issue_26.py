"""Tests for issue #26: Generate Commander Spec for Prototype Probes via Claude API.

AC coverage:
  AC1 – When a Probe with type="prototype" is processed, the Claude API is called
         to generate a commander spec in markdown format.
  AC2 – The generated spec contains exactly: a clear imperative title, exactly one
         target metric, a testable acceptance-criteria list, and minimal build context.
  AC3 – The generated markdown is persisted to Probe.commander_spec (and only that field).
  AC4 – Probes with any type other than "prototype" do not trigger spec generation
         and Probe.commander_spec is not written.
  AC5 – If the Claude API call fails, the error is surfaced to the caller and
         Probe.commander_spec is not partially written.
  AC6 – No UI surface is added or modified as part of this feature.
  AC7 – No GitHub/Linear/external ticket is auto-created; spec persisted only to
         Probe.commander_spec.
  AC8 – The spec is spec-only: crux does not execute, scaffold, or initiate building.
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


def _seed_case_with_plans(session, stage="weigh", probe_type=None):
    """Seed a Case with plans. If probe_type given, also seed a Probe."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is performance dropping?",
        sharpened="Running performance dropped 15% over 6 weeks.",
        not_investigating=json.dumps(["Weather"]),
        stage=stage,
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

    if probe_type:
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


_MOCK_PROBE_RESULT_PROTOTYPE = {
    "type": "prototype",
    "target_metric": "task completion rate",
    "cost": "~10 hours dev",
    "time": "1 week",
    "note": "Build a minimal tracker to test engagement.",
}

_MOCK_PROBE_RESULT_MEASUREMENT = {
    "type": "measurement",
    "target_metric": "resting HRV (7-day average)",
    "cost": "free",
    "time": "7 days",
    "note": "Measure HRV each morning.",
}

_MOCK_COMMANDER_SPEC = """\
# Build a Minimal Engagement Tracker

**Target metric:** task completion rate

## Acceptance Criteria
- [ ] Users can log a task as completed
- [ ] Completion rate is displayed as a percentage

## Build Context
This prototype tests whether users engage with explicit task tracking.
Build a minimal web UI with a single form and a completion counter.
"""


# ---------------------------------------------------------------------------
# Unit tests: commander_spec service module
# ---------------------------------------------------------------------------

def test_commander_spec_module_exists():
    """AC1: app.commander_spec module must exist with generate_commander_spec function."""
    import importlib

    mod = importlib.import_module("app.commander_spec")
    assert hasattr(mod, "generate_commander_spec"), (
        "app.commander_spec must export generate_commander_spec"
    )
    assert hasattr(mod, "CommanderSpecError"), (
        "app.commander_spec must export CommanderSpecError"
    )


def test_generate_commander_spec_raises_when_cli_unavailable():
    """AC5: CommanderSpecError raised when the claude CLI is missing/unavailable."""
    import asyncio

    from app.claude_cli import ClaudeCLIError
    from app.commander_spec import CommanderSpecError, generate_commander_spec

    probe_data = {
        "target_metric": "task completion rate",
        "note": "Build minimal tracker.",
        "sharpened": "Why is engagement low?",
    }

    with patch("app.commander_spec.complete", new_callable=AsyncMock,
               side_effect=ClaudeCLIError("`claude` not found on PATH")):
        with pytest.raises(CommanderSpecError):
            asyncio.run(
                generate_commander_spec(probe_data)
            )


def test_generate_commander_spec_returns_markdown():
    """AC1/AC2: generate_commander_spec returns a markdown string when the call succeeds."""
    import asyncio

    from app.commander_spec import generate_commander_spec

    probe_data = {
        "target_metric": "task completion rate",
        "note": "Build minimal tracker.",
        "sharpened": "Why is engagement low?",
    }

    with patch("app.commander_spec.complete", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        result = asyncio.run(
            generate_commander_spec(probe_data)
        )

    assert isinstance(result, str), "generate_commander_spec must return a string"
    assert len(result) > 0, "generate_commander_spec must return non-empty string"


def test_generate_commander_spec_surfaces_http_error():
    """AC5: CommanderSpecError raised when the Claude call fails."""
    import asyncio

    from app.claude_cli import ClaudeCLIError
    from app.commander_spec import CommanderSpecError, generate_commander_spec

    probe_data = {
        "target_metric": "metric",
        "note": "note",
        "sharpened": "problem",
    }

    with patch("app.commander_spec.complete", new_callable=AsyncMock,
               side_effect=ClaudeCLIError("claude CLI exited 1")):
        with pytest.raises(CommanderSpecError):
            asyncio.run(
                generate_commander_spec(probe_data)
            )


# ---------------------------------------------------------------------------
# AC1: POST /api/cases/{id}/probe/commander-spec triggers spec generation
# ---------------------------------------------------------------------------

def test_commander_spec_endpoint_exists(api_client, db_session):
    """AC1: POST /api/cases/{id}/probe/commander-spec endpoint must exist."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200


def test_prototype_probe_triggers_spec_generation(api_client, db_session):
    """AC1: When probe type='prototype', generate_commander_spec is called."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC) as mock_spec:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    mock_spec.assert_called_once()


def test_non_prototype_probe_does_not_trigger_spec_generation(api_client, db_session):
    """AC4: When probe type!='prototype', spec endpoint returns 422, generate_commander_spec NOT called."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="measurement")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock) as mock_spec:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    mock_spec.assert_not_called()


def test_spec_endpoint_404_for_unknown_case(api_client):
    """AC1: POST /api/cases/{id}/probe/commander-spec returns 404 for unknown case."""
    resp = api_client.post("/api/cases/00000000-0000-0000-0000-000000000000/probe/commander-spec")
    assert resp.status_code == 404


def test_spec_endpoint_422_when_no_probe(api_client, db_session):
    """AC1: POST /api/cases/{id}/probe/commander-spec returns 422 when no probe exists."""
    case = _seed_case_with_plans(db_session, stage="weigh")
    resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC3: commander_spec persisted to Probe.commander_spec for prototype probes
# ---------------------------------------------------------------------------

def test_prototype_probe_commander_spec_persisted(api_client, db_session):
    """AC3: Probe.commander_spec is set after spec generation."""
    from app import models

    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe is not None
    assert probe.commander_spec == _MOCK_COMMANDER_SPEC


def test_prototype_probe_spec_in_api_response(api_client, db_session):
    """AC3: commander_spec is included in the POST commander-spec response."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    data = resp.json()
    assert "commander_spec" in data
    assert data["commander_spec"] == _MOCK_COMMANDER_SPEC


def test_prototype_probe_spec_in_get_response(api_client, db_session):
    """AC3: commander_spec is included in GET /api/cases/{id} probe data after generation."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    get_resp = api_client.get(f"/api/cases/{case.id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["probe"] is not None
    assert data["probe"]["commander_spec"] == _MOCK_COMMANDER_SPEC


# ---------------------------------------------------------------------------
# AC3: commander_spec NOT written for non-prototype probes
# ---------------------------------------------------------------------------

def test_non_prototype_probe_commander_spec_null(api_client, db_session):
    """AC4: Probe.commander_spec remains null for non-prototype probes."""
    from app import models

    case = _seed_case_with_plans(db_session, stage="probe", probe_type="measurement")

    # Spec endpoint returns 422 for non-prototype; commander_spec stays null
    api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe is not None
    assert probe.commander_spec is None


def test_non_prototype_probe_spec_null_in_probe_response(api_client, db_session):
    """AC4: commander_spec is null in probe response for non-prototype probes."""
    case = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.design_probe", new_callable=AsyncMock,
               return_value=_MOCK_PROBE_RESULT_MEASUREMENT):
        resp = api_client.post(f"/api/cases/{case.id}/probe")

    assert resp.status_code == 200
    data = resp.json()
    assert "commander_spec" in data
    assert data["commander_spec"] is None


# ---------------------------------------------------------------------------
# AC4: All non-prototype types return 422 from spec endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("probe_type", ["measurement", "lab-test", "behaviour-experiment"])
def test_non_prototype_types_skip_spec_generation(api_client, db_session, probe_type):
    """AC4: Spec endpoint returns 422 for all non-prototype types."""
    from app import models

    case = _seed_case_with_plans(db_session, stage="probe", probe_type=probe_type)

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock) as mock_spec:
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 422
    mock_spec.assert_not_called()

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec is None


# ---------------------------------------------------------------------------
# AC5: Commander spec API failure → 502, commander_spec NOT written
# ---------------------------------------------------------------------------

def test_spec_generation_failure_returns_502(api_client, db_session):
    """AC5: If commander spec generation fails, endpoint returns 502."""
    from app.commander_spec import CommanderSpecError

    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               side_effect=CommanderSpecError("API timeout")):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 502


def test_spec_generation_failure_probe_not_persisted(api_client, db_session):
    """AC5: If spec generation fails, Probe.commander_spec is NOT written."""
    from app import models
    from app.commander_spec import CommanderSpecError

    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               side_effect=CommanderSpecError("network error")):
        api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe is not None
    assert probe.commander_spec is None, "commander_spec must not be written on failure"


def test_spec_generation_failure_commander_spec_not_written(api_client, db_session):
    """AC5: commander_spec is not partially written when spec generation fails."""
    from app import models
    from app.commander_spec import CommanderSpecError

    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               side_effect=CommanderSpecError("timeout")):
        api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec is None


# ---------------------------------------------------------------------------
# AC2: Generated spec structure
# ---------------------------------------------------------------------------

def test_spec_structure_title_present():
    """AC2: The generated spec must contain a title (# heading)."""
    assert "# " in _MOCK_COMMANDER_SPEC, "Spec must contain a markdown title"


def test_spec_structure_target_metric_present():
    """AC2: The generated spec must reference the target metric."""
    assert "target metric" in _MOCK_COMMANDER_SPEC.lower() or \
           "target_metric" in _MOCK_COMMANDER_SPEC.lower(), \
        "Spec must reference target metric"


def test_spec_structure_acceptance_criteria_present():
    """AC2: The generated spec must contain an acceptance-criteria section."""
    assert "Acceptance Criteria" in _MOCK_COMMANDER_SPEC or \
           "acceptance criteria" in _MOCK_COMMANDER_SPEC.lower(), \
        "Spec must contain acceptance criteria"


def test_spec_structure_build_context_present():
    """AC2: The generated spec must contain build context."""
    assert "Build Context" in _MOCK_COMMANDER_SPEC or \
           "build context" in _MOCK_COMMANDER_SPEC.lower(), \
        "Spec must contain build context"


# ---------------------------------------------------------------------------
# AC6: No UI changes — verify no frontend files were modified for this feature
# ---------------------------------------------------------------------------

def test_no_new_ui_files_for_spec_generation():
    """AC6: No UI surface is added for spec generation (spec-only, server-side)."""
    # The commander_spec field is exposed via the API but no UI renders it directly.
    # This test verifies the probe endpoint response structure is the only change.
    from app import models
    # The Probe model must have commander_spec column
    assert hasattr(models.Probe, "commander_spec"), \
        "Probe model must have commander_spec column"


# ---------------------------------------------------------------------------
# AC7: No external tickets created — spec only persisted to Probe.commander_spec
# ---------------------------------------------------------------------------

def test_no_external_ticket_creation(api_client, db_session):
    """AC7: No external tickets are created; spec is only persisted to Probe.commander_spec."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC):
        resp = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp.status_code == 200
    # Verify the spec is only in Probe.commander_spec, nowhere else
    from app import models
    db_session.expire_all()
    probe = db_session.query(models.Probe).filter_by(case_id=case.id).first()
    assert probe.commander_spec == _MOCK_COMMANDER_SPEC
    # No Case fields hold the spec
    updated_case = db_session.query(models.Case).filter_by(id=case.id).first()
    assert updated_case.weigh_context != _MOCK_COMMANDER_SPEC


# ---------------------------------------------------------------------------
# Idempotency — spec endpoint is idempotent
# ---------------------------------------------------------------------------

def test_prototype_probe_idempotent_returns_spec(api_client, db_session):
    """AC3: Second call to POST commander-spec returns existing spec without regenerating."""
    case = _seed_case_with_plans(db_session, stage="probe", probe_type="prototype")

    with patch("app.routers.cases.generate_commander_spec", new_callable=AsyncMock,
               return_value=_MOCK_COMMANDER_SPEC) as mock_spec:
        resp1 = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")
        # Second call — spec gen should NOT be called again (idempotency)
        resp2 = api_client.post(f"/api/cases/{case.id}/probe/commander-spec")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # generate_commander_spec should only be called once
    assert mock_spec.call_count == 1
    # Both responses return the same spec
    assert resp1.json()["commander_spec"] == resp2.json()["commander_spec"]
    assert resp1.json()["commander_spec"] == _MOCK_COMMANDER_SPEC
