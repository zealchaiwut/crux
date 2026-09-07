"""Tests for issue #204: content-post probe type and numeric verdict.

AC coverage:
  AC1 – content-post probe type exists in the enum, migration, prompt, and probe card UI.
  AC2 – A verdict can be settled by submitting a numeric result, evaluated server-side.
  AC3 – The resulting verdict records the metric value alongside the outcome.
  AC4 – An external caller can settle a content-post verdict with a real engagement figure.
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


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


def _seed_content_post_probe(session, decision_rule="if views >= 1000 → confirmed; else killed"):
    """Seed a Case at probe stage with a content-post probe."""
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Which content angle gets more views?",
        sharpened="Will variant A get at least 1000 views in 7 days?",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(c)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Hook-first angle",
        mechanism="Lead with the surprising stat to maximise watch time.",
        prior="0.6",
        current_rank=1,
    )
    session.add(plan)

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="content-post",
        target_metric="7-day view count",
        cost="free",
        time="7 days",
        note="Post variant A and track views for 7 days.",
        status="running",
        decision_rule=decision_rule,
    )
    session.add(probe)
    session.commit()
    return c, probe


# ---------------------------------------------------------------------------
# AC1: content-post enum exists in the model
# ---------------------------------------------------------------------------

def test_content_post_in_probe_type_enum():
    """AC1: _PROBE_TYPE must include 'content-post'."""
    from app import models
    assert "content-post" in models._PROBE_TYPE, (
        "'content-post' must be a valid probe type in models._PROBE_TYPE"
    )


def test_content_post_probe_can_be_created(db_session):
    """AC1: A Probe with type='content-post' must persist without error."""
    from app import models
    c, probe = _seed_content_post_probe(db_session)
    db_session.expire_all()
    reloaded = db_session.query(models.Probe).get(probe.id)
    assert reloaded is not None
    assert reloaded.type == "content-post"


def test_content_post_in_probe_generation_prompt():
    """AC1: The probe generation system prompt must mention 'content-post'."""
    from app import probe as probe_module
    assert "content-post" in probe_module._SYSTEM or "content-post" in probe_module._SYSTEM_THREE, (
        "Probe generation prompt must include the 'content-post' type"
    )


def test_content_post_in_probe_generation_valid_types():
    """AC1: The probe generation valid types must include 'content-post'."""
    from app import probe as probe_module
    assert "content-post" in probe_module._VALID_TYPES, (
        "'content-post' must be in probe._VALID_TYPES so the validator accepts it"
    )


def test_content_post_label_in_js():
    """AC1: The probe card JS must render a human-readable label for content-post."""
    js = _read_combined_js()
    assert "content-post" in js, (
        "cases.js must include 'content-post' in TYPE_LABELS so the probe card "
        "renders a human-readable label"
    )


# ---------------------------------------------------------------------------
# AC3: Verdict model has metric_value column
# ---------------------------------------------------------------------------

def test_verdict_has_metric_value_column():
    """AC3: Verdict model must have a metric_value column to record the engagement figure."""
    from app import models
    assert hasattr(models.Verdict, "metric_value"), (
        "Verdict model must have a metric_value column (AC3)"
    )


def test_verdict_metric_value_nullable(db_session):
    """AC3: metric_value must be nullable so existing text verdicts are unaffected."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Old case",
        sharpened="Old sharpened",
        not_investigating="[]",
        stage="probe",
    )
    db_session.add(c)
    db_session.flush()
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="weight",
        status="running",
    )
    db_session.add(probe)
    db_session.flush()
    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome="confirmed",
        notes="Old-style verdict, no metric value.",
    )
    db_session.add(verdict)
    db_session.commit()
    db_session.expire_all()
    v = db_session.query(models.Verdict).get(verdict.id)
    assert v.metric_value is None


# ---------------------------------------------------------------------------
# AC2 + AC4: POST /api/probes/{id}/verdict/numeric endpoint
# ---------------------------------------------------------------------------

def test_numeric_verdict_endpoint_exists(api_client, db_session):
    """AC4: POST /api/probes/{id}/verdict/numeric must exist and return 200."""
    _, probe = _seed_content_post_probe(db_session)
    with patch(
        "app.routers.probes.evaluate_numeric_verdict",
        new_callable=AsyncMock,
        return_value="confirmed",
    ):
        r = api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 1500.0},
        )
    assert r.status_code == 200, r.text


def test_numeric_verdict_stores_metric_value(api_client, db_session):
    """AC3: The numeric verdict endpoint must persist metric_value on the Verdict row."""
    from app import models
    _, probe = _seed_content_post_probe(db_session)
    with patch(
        "app.routers.probes.evaluate_numeric_verdict",
        new_callable=AsyncMock,
        return_value="confirmed",
    ):
        r = api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 1500.0},
        )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict is not None
    assert verdict.metric_value == 1500.0


def test_numeric_verdict_outcome_from_evaluation(api_client, db_session):
    """AC2: The outcome is set from server-side evaluation of the decision rule."""
    from app import models
    _, probe = _seed_content_post_probe(db_session)
    with patch(
        "app.routers.probes.evaluate_numeric_verdict",
        new_callable=AsyncMock,
        return_value="killed",
    ):
        r = api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 400.0},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["outcome"] == "killed"
    db_session.expire_all()
    verdict = db_session.query(models.Verdict).filter_by(probe_id=probe.id).first()
    assert verdict.outcome == "killed"
    assert verdict.metric_value == 400.0


def test_numeric_verdict_response_includes_metric_value(api_client, db_session):
    """AC3: The endpoint response must include metric_value so the caller can confirm what was stored."""
    _, probe = _seed_content_post_probe(db_session)
    with patch(
        "app.routers.probes.evaluate_numeric_verdict",
        new_callable=AsyncMock,
        return_value="confirmed",
    ):
        r = api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 2000.0},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["metric_value"] == 2000.0
    assert data["outcome"] == "confirmed"


def test_numeric_verdict_updates_probe_status(api_client, db_session):
    """AC2: After a numeric verdict, the probe status must match the outcome."""
    from app import models
    _, probe = _seed_content_post_probe(db_session)
    with patch(
        "app.routers.probes.evaluate_numeric_verdict",
        new_callable=AsyncMock,
        return_value="confirmed",
    ):
        api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 1500.0},
        )
    db_session.expire_all()
    updated = db_session.query(models.Probe).get(probe.id)
    assert updated.status == "confirmed"


def test_numeric_verdict_404_unknown_probe(api_client):
    """AC4: POST to unknown probe returns 404."""
    r = api_client.post(
        "/api/probes/00000000-0000-0000-0000-000000000000/verdict/numeric",
        json={"metric_value": 100.0},
    )
    assert r.status_code == 404


def test_numeric_verdict_requires_metric_value(api_client, db_session):
    """AC4: Missing metric_value returns 422."""
    _, probe = _seed_content_post_probe(db_session)
    r = api_client.post(
        f"/api/probes/{probe.id}/verdict/numeric",
        json={},
    )
    assert r.status_code == 422


def test_evaluate_numeric_verdict_called_with_rule_and_value(api_client, db_session):
    """AC2: The evaluation function receives the probe's decision_rule and the submitted value."""
    _, probe = _seed_content_post_probe(
        db_session, decision_rule="if views >= 1000 → confirmed; else killed"
    )
    mock_eval = AsyncMock(return_value="confirmed")
    with patch("app.routers.probes.evaluate_numeric_verdict", mock_eval):
        api_client.post(
            f"/api/probes/{probe.id}/verdict/numeric",
            json={"metric_value": 1200.0},
        )
    mock_eval.assert_called_once_with(
        "if views >= 1000 → confirmed; else killed", 1200.0
    )
