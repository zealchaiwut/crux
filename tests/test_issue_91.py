"""Regression tests for issue #91: WeighPanel rendering and rerank API call.

AC coverage:
  AC1  – Test file exists under tests/ following the per-issue naming convention
  AC2  – CaseDetailScreen renders WeighPanel when case stage is 'gather' (stage=2)
  AC3  – CaseDetailScreen renders WeighPanel when case stage is 'weigh' (stage=3)
  AC4  – CaseDetailScreen does NOT render WeighPanel when case stage is neither
          'gather' nor 'weigh' (e.g. verdict/closed = stage 5, probe = stage 4)
  AC5  – Submitting context from WeighPanel fires POST /api/cases/{id}/rerank
          with the correct case id
  AC6  – All new tests pass with no skips
  AC7  – No existing tests are broken
"""
import json
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _read_combined_js() -> str:
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


def _seed_case(session, stage: str = "gather"):
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why has my energy dropped?",
        sharpened="Energy dropped 30% over 3 months despite adequate sleep.",
        not_investigating=json.dumps([]),
        stage=stage,
    )
    session.add(c)
    session.flush()
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
        name="Iron deficiency",
        mechanism="Low ferritin impairs oxygen transport",
        prior="0.55",
        current_rank=1,
    )
    session.add(plan)
    session.commit()
    return c


_MOCK_RERANK_RESULT = [
    {"label": "A", "rank": 1, "standing": "ruled-in"},
]


# ---------------------------------------------------------------------------
# AC2: CaseDetailScreen renders WeighPanel when case stage is 'gather'
# ---------------------------------------------------------------------------

def test_weighpanel_gating_includes_gather_stage_2():
    """AC2: JS gating must include stage 2 (gather) so WeighPanel renders at gather."""
    combined = _read_combined_js()
    assert "WeighPanel" in combined, "WeighPanel component must be defined in JS"

    # Find the region near the WeighPanel usage inside CaseDetailScreen.
    # The gating expression should include an explicit check for stage 2 (gather).
    weigh_usage_idx = combined.rfind("WeighPanel")
    context = combined[max(0, weigh_usage_idx - 600) : weigh_usage_idx + 100]
    includes_gather = "stage === 2" in context or ">= 2" in context
    assert includes_gather, (
        "WeighPanel must be gated to render at stage 2 (gather). "
        f"Expected 'stage === 2' or '>= 2' near the WeighPanel usage. "
        f"Context window: {context!r}"
    )


def test_api_gather_stage_returns_string(api_client, db_session):
    """AC2: GET /api/cases/{id} returns stage='gather' for a case in 'gather' stage."""
    c = _seed_case(db_session, stage="gather")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] == "gather", (
        f"gather stage must be the string 'gather', got {data['stage']}"
    )


# ---------------------------------------------------------------------------
# AC3: CaseDetailScreen renders WeighPanel when case stage is 'weigh'
# ---------------------------------------------------------------------------

def test_weighpanel_gating_includes_weigh_stage_3():
    """AC3: JS gating must include stage 3 (weigh) so WeighPanel renders at weigh."""
    combined = _read_combined_js()
    weigh_usage_idx = combined.rfind("WeighPanel")
    context = combined[max(0, weigh_usage_idx - 600) : weigh_usage_idx + 100]
    includes_weigh = (
        "stage === 3" in context
        or ">= 3" in context
        or ">= 2" in context  # also covers weigh
    )
    assert includes_weigh, (
        "WeighPanel must be gated to render at stage 3 (weigh). "
        f"Expected 'stage === 3', '>= 3', or '>= 2' near WeighPanel usage. "
        f"Context window: {context!r}"
    )


def test_api_weigh_stage_returns_string(api_client, db_session):
    """AC3: GET /api/cases/{id} returns stage='weigh' for a case in 'weigh' stage."""
    c = _seed_case(db_session, stage="weigh")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] == "weigh", (
        f"weigh stage must be the string 'weigh', got {data['stage']}"
    )


# ---------------------------------------------------------------------------
# AC4: WeighPanel NOT rendered when stage is neither gather nor weigh
# ---------------------------------------------------------------------------

def test_weighpanel_gating_excludes_stages_above_weigh():
    """AC4: WeighPanel must NOT render at probe (4) or verdict/closed (5).

    The gating expression must be bounded — 'stage >= 2' alone would allow
    WeighPanel to bleed into probe and verdict screens.  The fix (issue #90)
    uses 'stage === 2 || stage === 3', which is explicitly bounded above.
    """
    combined = _read_combined_js()
    weigh_usage_idx = combined.rfind("WeighPanel")
    context = combined[max(0, weigh_usage_idx - 600) : weigh_usage_idx + 100]

    # Accept: explicit equality pair (stage === 2 || stage === 3)
    # Accept: range with explicit upper bound (stage >= 2 && stage <= 3 / stage < 4)
    # Reject: unbounded '>= 2' or '>= 3' without an upper bound
    bounded_equality = "stage === 2" in context and "stage === 3" in context
    bounded_range = ">= 2" in context and ("<= 3" in context or "< 4" in context)
    assert bounded_equality or bounded_range, (
        "WeighPanel rendering must be bounded to exclude probe (4) and verdict (5). "
        "Expected 'stage === 2 || stage === 3' or an equivalent bounded range. "
        f"Context window: {context!r}"
    )


def test_api_verdict_stage_returns_string(api_client, db_session):
    """AC4: GET /api/cases/{id} returns stage='verdict' for a case in 'verdict' (closed) stage."""
    c = _seed_case(db_session, stage="verdict")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] == "verdict", (
        f"verdict/closed stage must be the string 'verdict', got {data['stage']}"
    )


# ---------------------------------------------------------------------------
# AC5: Submitting context fires POST /api/cases/{id}/rerank with correct case id
# ---------------------------------------------------------------------------

def test_weighpanel_builds_rerank_url_from_case_id():
    """AC5: WeighPanel must call POST /api/cases/{caseId}/rerank using the caseId prop."""
    combined = _read_combined_js()
    # Find WeighPanel function body
    start = combined.find("function WeighPanel")
    assert start != -1, "WeighPanel function must be defined in JS"
    # Grab the first ~2 kB of the function body
    body = combined[start : start + 2000]
    assert "/api/cases/" in body and "rerank" in body, (
        "WeighPanel must build the POST URL as /api/cases/{caseId}/rerank"
    )
    assert "caseId" in body, (
        "WeighPanel must use the caseId prop in the rerank fetch URL"
    )


def test_rerank_endpoint_returns_200_for_correct_case_id(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank returns 200 when called with the correct case id."""
    c = _seed_case(db_session, stage="weigh")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_RESULT,
    ):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "HRV score 42, resting HR 68, sleep 6h average."},
        )
    assert r.status_code == 200, (
        f"POST /api/cases/{c.id}/rerank must return 200 for a valid case; got {r.status_code}: {r.text}"
    )


def test_rerank_endpoint_returns_404_for_wrong_case_id(api_client):
    """AC5: POST /api/cases/{id}/rerank returns 404 when the case id does not exist."""
    nonexistent_id = str(uuid.uuid4())
    r = api_client.post(
        f"/api/cases/{nonexistent_id}/rerank",
        json={"context": "Some context."},
    )
    assert r.status_code == 404, (
        f"POST /api/cases/{{nonexistent}}/rerank must return 404, got {r.status_code}"
    )


def test_rerank_is_case_specific_does_not_affect_sibling_case(api_client, db_session):
    """AC5: Calling rerank on case A must not mutate the weigh_context of case B."""
    from app import models

    case_a = _seed_case(db_session, stage="weigh")
    case_b = _seed_case(db_session, stage="weigh")

    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_RESULT,
    ):
        r = api_client.post(
            f"/api/cases/{case_a.id}/rerank",
            json={"context": "Context intended only for case A."},
        )
    assert r.status_code == 200

    db_session.expire_all()
    updated_b = db_session.get(models.Case, case_b.id)
    assert not updated_b.weigh_context, (
        "Posting rerank with case A's id must not write weigh_context to case B"
    )
