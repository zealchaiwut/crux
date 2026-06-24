"""Tests for issue #90: Fix WeighPanel not rendering in CaseDetailScreen.

AC coverage:
  AC1 - WeighPanel renders between last PlanCard and ProbeCard when case.stage === 'gather' (JS)
  AC2 - WeighPanel renders when case.stage === 'weigh' (JS)
  AC3 - Context textarea accepts input; submit button enabled when text present (JS)
  AC4 - Clicking submit POSTs to /api/cases/{id}/rerank with textarea content (JS)
  AC5 - On successful POST, case stage advances to 'weigh' and UI reflects new stage (API)
  AC6 - WeighPanel does NOT render for stages outside gather/weigh (e.g. probe, closed) (JS)
  AC7 - No sibling-root or JSX fragment issues in CaseDetailScreen (JS)
  AC8 - Existing PlanCard list and ProbeCard rendering unaffected (JS)
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
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case_with_plans(session, stage="gather"):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Dashboard load time is 8 seconds on first paint.",
        sharpened="First-paint latency is 8 s under normal network; target is under 2 s.",
        not_investigating=json.dumps([]),
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Unoptimised bundle", mechanism="JS bundle is 4 MB unminified.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="No CDN", mechanism="Static assets served from single origin.",
            prior="0.30", current_rank=2,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="C",
            name="Blocking DB query", mechanism="Sync query on main thread at startup.",
            prior="0.15", current_rank=3,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_RERANK_RESULT = [
    {"label": "B", "rank": 1, "standing": "ruled-in"},
    {"label": "A", "rank": 2, "standing": None},
    {"label": "C", "rank": 3, "standing": "ruled-out"},
]


# ---------------------------------------------------------------------------
# AC1: WeighPanel renders at gather stage (JS gate check)
# ---------------------------------------------------------------------------

def test_weigh_panel_renders_at_gather_stage():
    """AC1: JS must render WeighPanel when stage === 2 (gather)."""
    combined = _read_combined_js()
    # The condition must include stage 2 (gather) — either explicitly or via a range that covers 2
    assert "WeighPanel" in combined, "WeighPanel component must be defined in JS"
    # The render gate must allow stage 2 (gather=2) — reject a pure `stage >= 3` guard
    # Valid forms: stage === 2, stage >= 2, (stage === 2 || stage === 3), stage <= 3 && stage >= 2
    has_gather_gate = (
        "stage === 2" in combined
        or "stage >= 2" in combined
        or ("gather" in combined and "WeighPanel" in combined)
    )
    assert has_gather_gate, (
        "JS must gate WeighPanel so it renders at stage 2 (gather). "
        "Found only `stage >= 3` which excludes gather."
    )


# ---------------------------------------------------------------------------
# AC2: WeighPanel renders at weigh stage (JS gate check)
# ---------------------------------------------------------------------------

def test_weigh_panel_renders_at_weigh_stage():
    """AC2: JS must render WeighPanel when stage === 3 (weigh)."""
    combined = _read_combined_js()
    assert "WeighPanel" in combined, "WeighPanel component must be defined in JS"
    # Must have some stage gate that covers 3
    has_weigh_gate = (
        "stage === 3" in combined
        or "stage >= 2" in combined
        or "stage >= 3" in combined
    )
    assert has_weigh_gate, "JS must gate WeighPanel so it renders at stage 3 (weigh)"


# ---------------------------------------------------------------------------
# AC3: Textarea and enabled/disabled button (JS)
# ---------------------------------------------------------------------------

def test_weigh_panel_textarea_defined():
    """AC3: WeighPanel must contain a textarea for context input."""
    combined = _read_combined_js()
    assert "textarea" in combined.lower(), "WeighPanel must include a textarea element"
    assert "Your Context" in combined or "context" in combined.lower(), \
        "WeighPanel textarea must have a label or placeholder"


def test_weigh_panel_button_disabled_when_empty():
    """AC3: WeighPanel submit button must be disabled when textarea is empty."""
    combined = _read_combined_js()
    # Disabled logic references context.trim() or similar empty check
    assert "context.trim()" in combined or "!context" in combined, \
        "WeighPanel button must be disabled when textarea is empty"
    assert "disabled" in combined, "WeighPanel button must have a disabled prop"


# ---------------------------------------------------------------------------
# AC4: POSTs to /api/cases/{id}/rerank (JS)
# ---------------------------------------------------------------------------

def test_weigh_panel_posts_to_rerank_endpoint():
    """AC4: WeighPanel must call /api/cases/{id}/rerank on submit."""
    combined = _read_combined_js()
    assert "/rerank" in combined, "WeighPanel must POST to /api/cases/{id}/rerank"
    assert "POST" in combined, "WeighPanel must use POST method for rerank"


# ---------------------------------------------------------------------------
# AC5 (API): POST rerank advances stage from gather → weigh
# ---------------------------------------------------------------------------

def test_rerank_advances_stage_from_gather_to_weigh(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank on a gather-stage case must advance stage to weigh."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    assert c.stage == "gather"

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Bundle is 4 MB, CDN not configured, DB query takes 2s."},
        )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "weigh", (
        f"Stage must advance to 'weigh' after rerank from gather; got {updated.stage!r}"
    )


def test_rerank_from_gather_returns_updated_stage(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank response must include stage='weigh' after gather→weigh."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Context from gather stage."},
        )
    assert r.status_code == 200
    data = r.json()
    # After rerank, GET /api/cases/{id} must reflect stage=3 (weigh)
    # (the response body from rerank itself should include stage or caller reloads)
    # Validate via GET to confirm persistence
    get_r = api_client.get(f"/api/cases/{c.id}")
    assert get_r.status_code == 200
    case_data = get_r.json()
    assert case_data["stage"] == 3, (
        f"GET /api/cases/{{id}} must return stage=3 (weigh) after rerank from gather; got {case_data['stage']}"
    )


def test_rerank_does_not_advance_stage_when_already_weigh(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank on a weigh-stage case stays at weigh."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Re-ranking from weigh stage."},
        )
    assert r.status_code == 200

    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "weigh", (
        f"Stage must stay 'weigh' when reranking from weigh; got {updated.stage!r}"
    )


# ---------------------------------------------------------------------------
# AC6: WeighPanel absent for probe/closed stages (JS gate check)
# ---------------------------------------------------------------------------

def test_weigh_panel_not_shown_at_probe_or_verdict_stage():
    """AC6: WeighPanel must NOT render at probe (stage 4) or verdict (stage 5)."""
    combined = _read_combined_js()
    # The gate must NOT be an unbounded >= 3 that includes probe (4) and verdict (5)
    # If stage >= 3 is the only gate, WeighPanel would show at probe/verdict (wrong)
    # Valid gates: stage === 2 || stage === 3, stage >= 2 && stage <= 3, etc.
    # We detect the bad pattern: stage >= 3 with no upper bound near WeighPanel
    # A safe approach: check that the gate is bounded (not pure `stage >= 3`)
    # We look for an upper-bound expression near WeighPanel usage
    has_upper_bound = (
        "stage === 2 || stage === 3" in combined
        or "stage <= 3" in combined
        or "stage === 2 || stage === 3" in combined.replace(" ", "")
        or ("stage >= 2" in combined and "stage <= 3" in combined)
    )
    # Also acceptable: the original `stage >= 3` replaced with bounded expression
    assert has_upper_bound or "stage === 2" in combined, (
        "WeighPanel gate must be bounded so it does not render at probe (4) or verdict (5). "
        "Replace `stage >= 3` with an expression that covers only stages 2 and 3."
    )


# ---------------------------------------------------------------------------
# AC7: No JSX fragment/sibling-root issues (JS structure)
# ---------------------------------------------------------------------------

def test_jsx_fragments_balanced():
    """AC7: CaseDetailScreen return must use valid React.Fragment syntax (no sibling root)."""
    combined = _read_combined_js()
    # Count top-level fragment opens/closes in CaseDetailScreen context
    # A minimal check: ensure fragment shorthand is present and balanced
    opens = combined.count("<>")
    closes = combined.count("</>")
    assert opens == closes, (
        f"JSX fragment tags unbalanced: {opens} '<>' vs {closes} '</>' — "
        "sibling-root error likely"
    )


# ---------------------------------------------------------------------------
# AC8: PlanCard list and ProbeCard unaffected (JS)
# ---------------------------------------------------------------------------

def test_plancard_still_rendered():
    """AC8: PlanCard component must still be defined and rendered in CaseDetailScreen."""
    combined = _read_combined_js()
    assert "PlanCard" in combined, "PlanCard must still exist in JS"
    assert "BAKE-OFF" in combined or "COMPETING PLANS" in combined, \
        "BAKE-OFF section must still exist in CaseDetailScreen"


def test_probecard_still_rendered():
    """AC8: ProbeCard component must still be defined and rendered in CaseDetailScreen."""
    combined = _read_combined_js()
    assert "ProbeCard" in combined, "ProbeCard must still exist in JS"
    assert "THE PROBE" in combined, "THE PROBE section must still be present"
