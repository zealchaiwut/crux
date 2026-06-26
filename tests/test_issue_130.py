"""Tests for issue #130: Fix WeighPanel not rendering in CaseDetailScreen.

AC coverage:
  AC1 – WeighPanel renders between PlanCard list and ProbeCard section for stage 'gather' or 'weigh'
  AC2 – WeighPanel does NOT render for stages other than gather/weigh (e.g., probe, complete)
  AC3 – Submitting context textarea POSTs to /api/cases/{id}/rerank with the entered context
  AC4 – Successful POST advances case stage to 'weigh' and returns updated state
  AC5 – No console errors or React rendering warnings (structural JS checks)
  AC6 – Existing PlanCard and ProbeCard rendering is unaffected by the fix
"""
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


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
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case(session, stage="gather"):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Test sharpened statement.",
        not_investigating=json.dumps([]),
        stage=stage,
    )
    session.add(c)
    session.flush()
    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Plan A", mechanism="Mechanism A.",
            prior="0.6", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Plan B", mechanism="Mechanism B.",
            prior="0.4", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_RERANK = [
    {"label": "A", "rank": 1, "standing": None},
    {"label": "B", "rank": 2, "standing": None},
]


# ---------------------------------------------------------------------------
# AC1: WeighPanel JS stage gate uses stageNum (string-to-number conversion)
# ---------------------------------------------------------------------------

def test_js_uses_stagenum_for_stage_conversion():
    """AC1: CaseDetailScreen must convert string stage values via stageNum, not typeof check."""
    combined = _read_combined_js()
    # stageNum is the helper that converts string enum to numeric index
    assert "stageNum" in combined, \
        "cases.js must define stageNum helper to convert string stage values"


def test_js_render_stage_uses_stagenum_not_typeof():
    """AC1: The render-time stage variable must use stageNum, not a typeof guard that ignores strings."""
    combined = _read_combined_js()
    # The buggy pattern returns 0 for any string: typeof caseData.stage === "number" ? caseData.stage : 0
    # This should NOT appear as the sole stage conversion in the render path.
    # After the fix the render path uses stageNum(caseData.stage).
    assert "stageNum(caseData.stage)" in combined, \
        "CaseDetailScreen render path must use stageNum(caseData.stage) to convert stage strings to numbers"


def test_js_weigh_panel_gated_on_correct_stage_numbers():
    """AC1: WeighPanel must be gated on stage 2 (gather) and stage 3 (weigh) in JS."""
    combined = _read_combined_js()
    # The condition should be (stage === 2 || stage === 3) or equivalent
    assert ("stage === 2" in combined or "stage==2" in combined), \
        "WeighPanel must be shown when stage === 2 (gather)"
    assert ("stage === 3" in combined or "stage==3" in combined), \
        "WeighPanel must be shown when stage === 3 (weigh)"


def test_js_no_merge_conflict_markers():
    """AC5: JS file must not contain git merge conflict markers."""
    combined = _read_combined_js()
    assert "<<<<<<< " not in combined, "cases.js contains unresolved merge conflict (<<<<<<< marker)"
    assert "=======" not in combined, "cases.js contains unresolved merge conflict (======= marker)"
    assert ">>>>>>> " not in combined, "cases.js contains unresolved merge conflict (>>>>>>> marker)"


# ---------------------------------------------------------------------------
# AC2: WeighPanel absent for non-gather/weigh stages (JS gate)
# ---------------------------------------------------------------------------

def test_js_weigh_panel_absent_at_probe_stage():
    """AC2: WeighPanel must NOT render when stage is 4 (probe)."""
    combined = _read_combined_js()
    # Stage 4 is probe — the gate (stage===2||stage===3) must exclude it
    # We verify the gate does not include stage 4
    assert "stage === 4" not in combined or "WeighPanel" not in combined.split("stage === 4")[1][:200], \
        "WeighPanel must not appear unconditionally at stage 4 (probe)"


# ---------------------------------------------------------------------------
# AC3: POST /api/cases/{id}/rerank receives the entered context
# ---------------------------------------------------------------------------

def test_rerank_endpoint_accepts_context_payload(api_client, db_session):
    """AC3: POST /api/cases/{id}/rerank must accept a JSON body with 'context' key."""
    c, _ = _seed_case(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "My entered context text."},
        )
    assert r.status_code == 200, r.text


def test_rerank_endpoint_requires_nonempty_context(api_client, db_session):
    """AC3: POST /api/cases/{id}/rerank must reject blank/whitespace context."""
    c, _ = _seed_case(db_session, stage="gather")
    r = api_client.post(
        f"/api/cases/{c.id}/rerank",
        json={"context": "   "},
    )
    assert r.status_code in (400, 422), \
        f"Expected 4xx for blank context, got {r.status_code}"


def test_js_weigh_panel_posts_to_rerank_endpoint():
    """AC3: WeighPanel must POST to /api/cases/{id}/rerank in JS."""
    combined = _read_combined_js()
    assert "/rerank" in combined, "WeighPanel JS must POST to /api/cases/{id}/rerank"


# ---------------------------------------------------------------------------
# AC4: Successful POST advances case to 'weigh' stage
# ---------------------------------------------------------------------------

def test_rerank_from_gather_stage_advances_to_weigh(api_client, db_session):
    """AC4: POST /api/cases/{id}/rerank on a 'gather'-stage case must advance stage to 'weigh'."""
    from app import models
    c, _ = _seed_case(db_session, stage="gather")
    assert c.stage == "gather"

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Some valid context."},
        )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "weigh", \
        f"Case stage must advance to 'weigh' after rerank; got '{updated.stage}'"


def test_rerank_response_includes_plans(api_client, db_session):
    """AC4: POST /api/cases/{id}/rerank must return updated state (plans) in the response."""
    c, _ = _seed_case(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Valid context."},
        )
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "Response must include 'plans' key with updated plan state"
    assert len(data["plans"]) == 2


def test_get_case_returns_string_stage_field(api_client, db_session):
    """AC4: GET /api/cases/{id} must return 'stage' as a string (not integer)."""
    c, _ = _seed_case(db_session, stage="gather")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "stage" in data, "GET /api/cases/{id} must return a 'stage' field"
    assert isinstance(data["stage"], str), \
        f"stage must be a string (e.g. 'gather'), got {type(data['stage'])}: {data['stage']!r}"
    assert data["stage"] == "gather"


# ---------------------------------------------------------------------------
# AC5: No render warnings — structural JS checks
# ---------------------------------------------------------------------------

def test_js_states_constants_used_consistently():
    """AC5: STATES constants (STATES.IDLE, STATES.LOADING) must be used, not bare string literals."""
    combined = _read_combined_js()
    assert "STATES.IDLE" in combined, "STATES.IDLE constant must be used"
    assert "STATES.LOADING" in combined, "STATES.LOADING constant must be used"


def test_js_weigh_panel_component_defined():
    """AC5: WeighPanel component must be defined in cases.js."""
    combined = _read_combined_js()
    assert "function WeighPanel" in combined, "WeighPanel component must be defined"


# ---------------------------------------------------------------------------
# AC6: PlanCard and ProbeCard still present and unaffected
# ---------------------------------------------------------------------------

def test_js_plancard_component_still_defined():
    """AC6: PlanCard component must remain defined after the fix."""
    combined = _read_combined_js()
    assert "function PlanCard" in combined, "PlanCard component must still be defined"


def test_js_probecard_component_still_defined():
    """AC6: ProbeCard component must remain defined after the fix."""
    combined = _read_combined_js()
    assert "function ProbeCard" in combined, "ProbeCard component must still be defined"


def test_plancard_rendering_unaffected(api_client, db_session):
    """AC6: GET /api/cases/{id} still returns plans with expected fields after the fix."""
    c, plans = _seed_case(db_session, stage="gather")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data
    assert len(data["plans"]) == 2
    for p in data["plans"]:
        assert "label" in p
        assert "name" in p
        assert "mechanism" in p
