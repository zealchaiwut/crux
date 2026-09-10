"""Tests for issue #168: Add horizon enum and generate three probes per case.

AC coverage:
  AC1 – Probe.horizon column exists as nullable enum (short/mid/long) in the DB model
  AC2 – Existing probe rows with horizon=NULL remain valid (migration safe)
  AC3 – Designing a probe creates exactly three Probe rows, one per horizon
  AC4 – Each probe has distinct, non-empty target_metric, duration, decision_rule, steps
  AC5 – Re-running probe design replaces existing three probes (not appending)
  AC6 – All three Probe rows persisted via routers/cases.py with horizon correctly set
  AC7 – design_probes output contains exactly three probes with short/mid/long horizons
  AC8 – Each probe's fields differ across horizons (no copy-paste identical rows)
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


def _mock_probes_provider(probes_list):
    """Mock provider (issue #199): design_probes now routes through call_stage,
    which expects a text-completion response wrapped as {"probes": [...]}."""
    p = MagicMock()
    p.supports_structured_output = False
    p.complete = AsyncMock(return_value=json.dumps({"probes": probes_list}))
    p.complete_structured = AsyncMock()
    return p


# ---------------------------------------------------------------------------
# Helpers
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


def _seed_case_with_plans(session, stage="weigh"):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my running performance dropping?",
        sharpened="Running performance has dropped 15% over 6 weeks despite consistent training.",
        not_investigating=json.dumps(["Shoe wear", "Weather"]),
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Overtraining Load", mechanism="Excess training volume depresses HRV.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Iron Deficiency", mechanism="Low ferritin impairs oxygen transport.",
            prior="0.30", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_THREE_PROBES = [
    {
        "horizon": "short",
        "type": "measurement",
        "target_metric": "resting HRV (7-day average)",
        "cost": "free",
        "time": "7 days",
        "note": "Measure resting HRV each morning for 7 days.",
        "steps": ["Download HRV app", "Measure each morning at wake-up", "Log readings"],
        "duration": "7 days",
        "decision_rule": "If HRV drops >10% vs baseline → early signal of overtraining",
    },
    {
        "horizon": "mid",
        "type": "behaviour-experiment",
        "target_metric": "weekly average run pace at same effort",
        "cost": "free",
        "time": "3 weeks",
        "note": "Reduce training load by 20% for 3 weeks and track pace.",
        "steps": ["Reduce weekly mileage by 20%", "Keep heart rate zones identical", "Log pace weekly"],
        "duration": "3 weeks",
        "decision_rule": "If pace improves >5% vs baseline week → training overload confirmed",
    },
    {
        "horizon": "long",
        "type": "lab-test",
        "target_metric": "serum ferritin + full blood count",
        "cost": "~£40",
        "time": "6 weeks",
        "note": "See GP for full blood count; supplement if ferritin < 30 µg/L for 6 weeks.",
        "steps": ["Book GP appointment", "Request full blood count", "If ferritin low, start supplement", "Retest after 6 weeks"],
        "duration": "6 weeks",
        "decision_rule": "If ferritin rises to ≥50 µg/L and pace recovers → iron deficiency confirmed",
    },
]


# ---------------------------------------------------------------------------
# AC1: Probe.horizon column exists as nullable enum in the model
# ---------------------------------------------------------------------------

def test_probe_model_has_horizon_column():
    """AC1: Probe model must have a 'horizon' column."""
    from app import models
    assert hasattr(models.Probe, "horizon"), "Probe model must have a 'horizon' column"


def test_probe_horizon_enum_values():
    """AC1: _PROBE_HORIZON must contain exactly short, mid, long."""
    from app import models
    assert hasattr(models, "_PROBE_HORIZON"), "models must define _PROBE_HORIZON constant"
    assert set(models._PROBE_HORIZON) == {"short", "mid", "long"}, (
        f"_PROBE_HORIZON must be ('short', 'mid', 'long'), got {models._PROBE_HORIZON}"
    )


def test_probe_horizon_is_nullable(db_session):
    """AC1: horizon column must be nullable — existing rows without it remain valid."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test",
        sharpened="Test problem",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(c)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="some metric",
        cost="free",
        time="1 week",
        note="some note",
        status="designed",
        # horizon intentionally omitted
    )
    db_session.add(probe)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(models.Probe, probe.id)
    assert stored is not None
    assert stored.horizon is None, "horizon must default to NULL when not set"


# ---------------------------------------------------------------------------
# AC2: Existing probe rows with horizon=NULL remain valid
# ---------------------------------------------------------------------------

def test_existing_probe_null_horizon_readable(db_session):
    """AC2: A probe row with horizon=NULL can be read back without error."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Existing problem",
        sharpened="Sharpened existing",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(c)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="old metric",
        cost="free",
        time="1 day",
        note="old note",
        status="designed",
        horizon=None,
    )
    db_session.add(probe)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.query(models.Probe).filter_by(case_id=c.id).first()
    assert stored is not None
    assert stored.horizon is None


# ---------------------------------------------------------------------------
# AC3 + AC6: POST /probe creates exactly three Probe rows with horizon set
# ---------------------------------------------------------------------------

def test_probe_endpoint_creates_three_rows(api_client, db_session):
    """AC3: POST /api/cases/{id}/probe creates exactly three Probe rows."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200, r.text

    db_session.expire_all()
    count = db_session.query(models.Probe).filter_by(case_id=c.id).count()
    assert count == 3, f"Expected exactly 3 Probe rows, got {count}"


def test_probe_endpoint_returns_three_probes(api_client, db_session):
    """AC3: POST /api/cases/{id}/probe response includes 'probes' list of length 3."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    data = r.json()
    assert "probes" in data, "Response must have a 'probes' key"
    assert len(data["probes"]) == 3, f"Expected 3 probes in response, got {len(data['probes'])}"


def test_probe_response_has_all_three_horizons(api_client, db_session):
    """AC6: Response probes have horizon values short, mid, and long."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    horizons = {p["horizon"] for p in r.json()["probes"]}
    assert horizons == {"short", "mid", "long"}, f"Expected horizons short/mid/long, got {horizons}"


def test_probe_db_rows_have_correct_horizons(api_client, db_session):
    """AC6: All three Probe rows in DB have correct horizon values."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    horizons = {p.horizon for p in probes}
    assert horizons == {"short", "mid", "long"}, (
        f"DB probes must have horizons short/mid/long, got {horizons}"
    )


# ---------------------------------------------------------------------------
# AC4: Each probe has distinct, non-empty required fields
# ---------------------------------------------------------------------------

def test_probe_fields_non_empty(api_client, db_session):
    """AC4: Each probe has non-empty target_metric, duration, decision_rule, and steps."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 200
    for probe in r.json()["probes"]:
        horizon = probe["horizon"]
        assert probe["target_metric"], f"Probe {horizon}: target_metric must be non-empty"
        assert probe["duration"], f"Probe {horizon}: duration must be non-empty"
        assert probe["decision_rule"], f"Probe {horizon}: decision_rule must be non-empty"
        assert probe["steps"], f"Probe {horizon}: steps must be non-empty"


def test_probe_db_fields_non_empty(api_client, db_session):
    """AC4: DB rows have non-empty target_metric, duration, decision_rule, steps."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        api_client.post(f"/api/cases/{c.id}/probe")

    db_session.expire_all()
    probes = db_session.query(models.Probe).filter_by(case_id=c.id).all()
    for probe in probes:
        assert probe.target_metric, f"Probe {probe.horizon}: target_metric must be non-empty in DB"
        assert probe.duration, f"Probe {probe.horizon}: duration must be non-empty in DB"
        assert probe.decision_rule, f"Probe {probe.horizon}: decision_rule must be non-empty in DB"
        assert probe.steps, f"Probe {probe.horizon}: steps must be non-empty in DB"


# ---------------------------------------------------------------------------
# AC5: Re-running probe design replaces (not appends) probes
# ---------------------------------------------------------------------------

def test_reprobe_replaces_not_appends(api_client, db_session):
    """AC5: Re-running probe design results in exactly 3 probes total, not 6."""
    from app import models
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        api_client.post(f"/api/cases/{c.id}/probe")

    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r2 = api_client.post(f"/api/cases/{c.id}/probe")
    assert r2.status_code == 200

    db_session.expire_all()
    count = db_session.query(models.Probe).filter_by(case_id=c.id).count()
    assert count == 3, f"After re-probe, exactly 3 Probe rows must exist; got {count}"


def test_reprobe_returns_three_probes(api_client, db_session):
    """AC5: Re-running probe design returns 3 probes with correct horizons."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        api_client.post(f"/api/cases/{c.id}/probe")
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r2 = api_client.post(f"/api/cases/{c.id}/probe")
    data = r2.json()
    assert len(data["probes"]) == 3
    horizons = {p["horizon"] for p in data["probes"]}
    assert horizons == {"short", "mid", "long"}


# ---------------------------------------------------------------------------
# AC7: design_probes service returns exactly three probes with correct horizons
# ---------------------------------------------------------------------------

def test_design_probes_module_exists():
    """AC7: app.probe module must export design_probes function."""
    import importlib
    mod = importlib.import_module("app.probe")
    assert hasattr(mod, "design_probes"), "app.probe must export design_probes"


def test_design_probes_returns_three(db_session):
    """AC7: design_probes service must return exactly 3 probe dicts."""
    from app.probe import design_probes

    provider = _mock_probes_provider(_MOCK_THREE_PROBES)
    with patch("app.llm_providers.get_provider", return_value=provider):
        import asyncio
        result = asyncio.run(
            design_probes("Test problem", [{"label": "A", "name": "Plan A",
                                            "mechanism": "mechanism", "current_rank": 1}])
        )
    assert len(result) == 3, f"design_probes must return 3 items, got {len(result)}"


def test_design_probes_has_all_horizons(db_session):
    """AC7: design_probes returns probes with horizons short, mid, and long."""
    from app.probe import design_probes

    provider = _mock_probes_provider(_MOCK_THREE_PROBES)
    with patch("app.llm_providers.get_provider", return_value=provider):
        import asyncio
        result = asyncio.run(
            design_probes("Test problem", [{"label": "A", "name": "Plan A",
                                            "mechanism": "mechanism", "current_rank": 1}])
        )
    horizons = {p["horizon"] for p in result}
    assert horizons == {"short", "mid", "long"}, f"Horizons must be short/mid/long, got {horizons}"


# ---------------------------------------------------------------------------
# AC8: Each probe's fields differ across horizons
# ---------------------------------------------------------------------------

def test_probe_fields_differ_across_horizons(api_client, db_session):
    """AC8: target_metric, duration, and decision_rule must all differ across horizons."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    probes = r.json()["probes"]

    target_metrics = {p["target_metric"] for p in probes}
    assert len(target_metrics) == 3, (
        f"target_metric must differ across all three probes, got {target_metrics}"
    )

    durations = {p["duration"] for p in probes}
    assert len(durations) == 3, (
        f"duration must differ across all three probes, got {durations}"
    )

    decision_rules = {p["decision_rule"] for p in probes}
    assert len(decision_rules) == 3, (
        f"decision_rule must differ across all three probes, got {decision_rules}"
    )


def test_design_probes_fields_differ(db_session):
    """AC8: design_probes service output has distinct fields across horizons."""
    from app.probe import design_probes

    provider = _mock_probes_provider(_MOCK_THREE_PROBES)
    with patch("app.llm_providers.get_provider", return_value=provider):
        import asyncio
        result = asyncio.run(
            design_probes("Test problem", [{"label": "A", "name": "Plan A",
                                            "mechanism": "mechanism", "current_rank": 1}])
        )

    target_metrics = {p["target_metric"] for p in result}
    assert len(target_metrics) == 3, "design_probes must return probes with distinct target_metrics"

    decision_rules = {p["decision_rule"] for p in result}
    assert len(decision_rules) == 3, "design_probes must return probes with distinct decision_rules"


# ---------------------------------------------------------------------------
# Error handling: 502 on Claude failure, no probes persisted
# ---------------------------------------------------------------------------

def test_probe_502_on_claude_failure(api_client, db_session):
    """Existing safety: Claude failure returns 502 and no probes are persisted."""
    from app import models
    from app.probe import ProbeError
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               side_effect=ProbeError("API timeout")):
        r = api_client.post(f"/api/cases/{c.id}/probe")
    assert r.status_code == 502

    db_session.expire_all()
    count = db_session.query(models.Probe).filter_by(case_id=c.id).count()
    assert count == 0, f"No probes must be persisted on failure, got {count}"


# ---------------------------------------------------------------------------
# GET /api/cases/{id} returns probes list
# ---------------------------------------------------------------------------

def test_get_case_returns_probes_list(api_client, db_session):
    """AC6: GET /api/cases/{id} includes a 'probes' list with all three probes."""
    c, _ = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.design_probes", new_callable=AsyncMock,
               return_value=_MOCK_THREE_PROBES):
        api_client.post(f"/api/cases/{c.id}/probe")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "probes" in data, "GET /api/cases/{id} must include 'probes' list"
    assert len(data["probes"]) == 3, f"Expected 3 probes in GET response, got {len(data['probes'])}"
    horizons = {p["horizon"] for p in data["probes"]}
    assert horizons == {"short", "mid", "long"}


def test_get_case_probes_empty_before_design(api_client, db_session):
    """Before probe design, probes list in GET /api/cases/{id} is empty."""
    c, _ = _seed_case_with_plans(db_session)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    probes = data.get("probes", [])
    assert probes == [], f"Before probe design, probes must be empty list, got {probes}"
