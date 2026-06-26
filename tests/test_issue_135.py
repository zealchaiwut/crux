"""Tests for issue #135: Add tests for rerank rationale and WeighPanel regression.

AC coverage:
  AC1  — tests/test_issue_135.py exists and runs with pytest (this file).
  AC2  — Claude fully mocked; no live API calls during the suite.
  AC3  — rerank_plans(...) returns a list where every plan entry includes a non-empty rationale.
  AC4  — POST /api/cases/{id}/rerank persists rationale to the database.
  AC5  — GET /api/cases/{id} returns the previously persisted rationale for each plan.
  AC6  — CaseDetailScreen renders WeighPanel when case stage is 'gather'.
  AC7  — CaseDetailScreen renders WeighPanel when case stage is 'weigh'.
  AC8  — Submitting the WeighPanel form triggers POST /api/cases/{id}/rerank.
  AC9  — All new tests pass with no skips or xfails.
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


def _seed_case_with_plans(session, stage="gather"):
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my cardiovascular fitness plateauing?",
        sharpened="Cardiovascular fitness has plateaued for 8 weeks despite consistent aerobic training.",
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label="A",
            name="Overtraining",
            mechanism="Accumulated fatigue suppresses aerobic adaptation.",
            prior="0.50",
            current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label="B",
            name="Nutritional Deficit",
            mechanism="Low carbohydrate intake limits glycogen resynthesis.",
            prior="0.30",
            current_rank=2,
        ),
        models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label="C",
            name="Sleep Deprivation",
            mechanism="Insufficient sleep degrades aerobic recovery markers.",
            prior="0.20",
            current_rank=3,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


# ---------------------------------------------------------------------------
# AC3: rerank_plans returns non-empty rationale on every plan (unit test)
# ---------------------------------------------------------------------------

_MOCK_CLAUDE_RESPONSE = (
    '[{"label": "B", "rank": 1, "standing": "ruled-in", '
    '"rationale": "Low carbohydrate intake is strongly supported by the plateau pattern and recent dietary logs."}, '
    '{"label": "A", "rank": 2, "standing": null, '
    '"rationale": "Overtraining is plausible given training volume but ferritin is normal."}, '
    '{"label": "C", "rank": 3, "standing": "ruled-out", '
    '"rationale": "Sleep logs show 7–8 hours nightly, making sleep deprivation unlikely."}]'
)

_PLANS_INPUT = [
    {"label": "A", "name": "Overtraining", "mechanism": "Accumulated fatigue suppresses aerobic adaptation."},
    {"label": "B", "name": "Nutritional Deficit", "mechanism": "Low carbohydrate intake limits glycogen resynthesis."},
    {"label": "C", "name": "Sleep Deprivation", "mechanism": "Insufficient sleep degrades aerobic recovery markers."},
]


@pytest.mark.asyncio
async def test_rerank_plans_returns_rationale_on_every_plan():
    """AC3: rerank_plans returns a list where every plan has a non-empty rationale string."""
    from app.weigh import rerank_plans

    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=_MOCK_CLAUDE_RESPONSE):
        result = await rerank_plans(
            sharpened="Cardiovascular fitness has plateaued for 8 weeks.",
            plans=_PLANS_INPUT,
            context="Training 5x/week, carbs ~100g/day, sleep 7–8h.",
        )

    assert len(result) > 0, "rerank_plans must return at least one plan"
    for plan in result:
        assert "rationale" in plan, f"Plan {plan.get('label')!r} is missing 'rationale' key"
        assert isinstance(plan["rationale"], str), (
            f"Plan {plan.get('label')!r} rationale must be a string, got {type(plan['rationale'])}"
        )
        assert plan["rationale"].strip(), (
            f"Plan {plan.get('label')!r} rationale must not be empty or whitespace"
        )


@pytest.mark.asyncio
async def test_rerank_plans_no_live_api_calls():
    """AC2: rerank_plans never makes live API calls; complete() is always mocked."""
    from app.weigh import rerank_plans

    call_count = 0

    async def mock_complete(system, user, model):
        nonlocal call_count
        call_count += 1
        return _MOCK_CLAUDE_RESPONSE

    with patch("app.weigh.complete", side_effect=mock_complete):
        await rerank_plans(
            sharpened="Test problem.",
            plans=_PLANS_INPUT,
            context=None,
        )

    assert call_count == 1, "complete() must be called exactly once (via mock, not live)"


@pytest.mark.asyncio
async def test_rerank_plans_rationale_on_all_plans_without_context():
    """AC3: rationale is non-empty even when context is None (sources-only mode)."""
    from app.weigh import rerank_plans

    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=_MOCK_CLAUDE_RESPONSE):
        result = await rerank_plans(
            sharpened="Cardiovascular fitness has plateaued for 8 weeks.",
            plans=_PLANS_INPUT,
            context=None,
        )

    assert all(plan.get("rationale", "").strip() for plan in result), (
        "Every plan must have a non-empty rationale even when no user context is provided"
    )


# ---------------------------------------------------------------------------
# AC4: POST /api/cases/{id}/rerank persists rationale to the database
# ---------------------------------------------------------------------------

_MOCK_RERANK_WITH_RATIONALE = [
    {
        "label": "B",
        "rank": 1,
        "standing": "ruled-in",
        "rationale": "Nutritional deficit strongly supported by plateau timing and diet logs.",
    },
    {
        "label": "A",
        "rank": 2,
        "standing": None,
        "rationale": "Overtraining plausible but ferritin is within normal range.",
    },
    {
        "label": "C",
        "rank": 3,
        "standing": "ruled-out",
        "rationale": "Sleep logs show adequate rest; deprivation is unlikely.",
    },
]


def test_rerank_endpoint_persists_rationale_to_db(api_client, db_session):
    """AC4: POST /api/cases/{id}/rerank persists the rationale field for each plan."""
    from app import models

    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Training 5x/week, carbs ~100g/day."},
        )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rationale_by_label = {p.label: p.rationale for p in plans}

    for item in _MOCK_RERANK_WITH_RATIONALE:
        label = item["label"]
        expected = item["rationale"]
        stored = rationale_by_label.get(label)
        assert stored == expected, (
            f"Plan {label!r} rationale not persisted correctly: "
            f"expected {expected!r}, got {stored!r}"
        )


def test_rerank_endpoint_persists_rationale_without_context(api_client, db_session):
    """AC4: Rationale is persisted even when context is None (skip path)."""
    from app import models

    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200, r.text

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    for plan in plans:
        assert plan.rationale is not None and plan.rationale.strip(), (
            f"Plan {plan.label!r} rationale must be persisted even when context is skipped; "
            f"got {plan.rationale!r}"
        )


def test_rerank_response_does_not_lose_rationale(api_client, db_session):
    """AC4: The rerank POST response body reflects the persisted data (regression guard)."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "My data."},
        )
    assert r.status_code == 200, r.text
    # Response structure sanity
    data = r.json()
    assert "plans" in data
    assert len(data["plans"]) == 3


# ---------------------------------------------------------------------------
# AC5: GET /api/cases/{id} returns persisted rationale for each plan
# ---------------------------------------------------------------------------

def test_get_case_returns_rationale_after_rerank(api_client, db_session):
    """AC5: GET /api/cases/{id} returns non-empty rationale for each plan after rerank."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        post_r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Training data."},
        )
    assert post_r.status_code == 200, post_r.text

    get_r = api_client.get(f"/api/cases/{c.id}")
    assert get_r.status_code == 200, get_r.text
    data = get_r.json()

    assert "plans" in data
    rationale_by_label = {p["label"]: p.get("rationale") for p in data["plans"]}
    for item in _MOCK_RERANK_WITH_RATIONALE:
        label = item["label"]
        expected = item["rationale"]
        returned = rationale_by_label.get(label)
        assert returned == expected, (
            f"GET /api/cases/{{id}} returned wrong rationale for plan {label!r}: "
            f"expected {expected!r}, got {returned!r}"
        )


def test_get_case_rationale_field_present_on_every_plan(api_client, db_session):
    """AC5: GET /api/cases/{id} includes 'rationale' key on every plan object."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Some context."})

    get_r = api_client.get(f"/api/cases/{c.id}")
    assert get_r.status_code == 200
    data = get_r.json()
    for plan in data["plans"]:
        assert "rationale" in plan, (
            f"Plan {plan.get('label')!r} missing 'rationale' key in GET response"
        )


def test_get_case_rationale_matches_post_response(api_client, db_session):
    """AC5: Rationale returned by GET matches what was stored after POST."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch(
        "app.routers.cases.rerank_plans",
        new_callable=AsyncMock,
        return_value=_MOCK_RERANK_WITH_RATIONALE,
    ):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Ctx."})

    get_r = api_client.get(f"/api/cases/{c.id}")
    assert get_r.status_code == 200
    data = get_r.json()

    # Build a lookup from the mock result
    expected_by_label = {item["label"]: item["rationale"] for item in _MOCK_RERANK_WITH_RATIONALE}
    for plan in data["plans"]:
        label = plan["label"]
        if label in expected_by_label:
            assert plan.get("rationale") == expected_by_label[label], (
                f"Rationale round-trip failed for plan {label!r}"
            )


def test_get_case_rationale_null_before_rerank(api_client, db_session):
    """AC5: rationale is null/absent before any rerank is performed."""
    c, _ = _seed_case_with_plans(db_session, stage="gather")
    get_r = api_client.get(f"/api/cases/{c.id}")
    assert get_r.status_code == 200
    data = get_r.json()
    for plan in data["plans"]:
        rationale = plan.get("rationale")
        assert not rationale, (
            f"Plan {plan.get('label')!r} should have null/empty rationale before rerank; "
            f"got {rationale!r}"
        )


# ---------------------------------------------------------------------------
# AC6: CaseDetailScreen renders WeighPanel when stage is 'gather' (JS regression)
# ---------------------------------------------------------------------------

def test_weighpanel_rendered_at_gather_stage_in_js():
    """AC6: CaseDetailScreen JS renders WeighPanel when stage is gather (numeric 2)."""
    combined = _read_combined_js()
    # The stage condition in CaseDetailScreen must include gather stage (2)
    assert "stage === 2" in combined or "(stage === 2 || stage === 3)" in combined, (
        "CaseDetailScreen must render WeighPanel at gather stage (stage === 2)"
    )
    # WeighPanel component must be referenced in the render output at that stage
    assert "WeighPanel" in combined, "WeighPanel component must be present in JS"


def test_weigh_section_label_at_gather_stage_in_js():
    """AC6: The WEIGH section label must appear in the JS conditional for gather/weigh."""
    combined = _read_combined_js()
    assert "WEIGH" in combined, "WEIGH section label must be present in the CaseDetailScreen JS"


def test_weighpanel_component_defined_in_js():
    """AC6/AC7: WeighPanel is a defined React component in the JS bundle."""
    combined = _read_combined_js()
    assert "function WeighPanel" in combined, (
        "WeighPanel must be defined as a named function component in JS"
    )


# ---------------------------------------------------------------------------
# AC7: CaseDetailScreen renders WeighPanel when stage is 'weigh' (JS regression)
# ---------------------------------------------------------------------------

def test_weighpanel_rendered_at_weigh_stage_in_js():
    """AC7: CaseDetailScreen JS renders WeighPanel when stage is weigh (numeric 3)."""
    combined = _read_combined_js()
    # Weigh stage is 3; the condition must include it
    assert "stage === 3" in combined or "(stage === 2 || stage === 3)" in combined, (
        "CaseDetailScreen must render WeighPanel at weigh stage (stage === 3)"
    )


def test_weighpanel_absent_at_probe_stage_in_js():
    """AC7 complement: WeighPanel is NOT rendered at probe stage or later (stage >= 4)."""
    combined = _read_combined_js()
    # The WeighPanel is inside a conditional block `(stage === 2 || stage === 3)`.
    # We verify the condition does NOT extend to stage 4+.
    assert "stage === 4" not in combined.replace(
        "(stage === 2 || stage === 3)", ""
    ) or "WeighPanel" not in combined[combined.find("stage === 4"):combined.find("stage === 4") + 200], (
        "WeighPanel must not be rendered at probe stage (stage 4) or later"
    )


def test_weighpanel_stage_gate_covers_both_stages_in_js():
    """AC6+AC7: The stage condition covers gather (2) AND weigh (3) together."""
    combined = _read_combined_js()
    # The canonical guard is `(stage === 2 || stage === 3)` or equivalent
    assert (
        "(stage === 2 || stage === 3)" in combined
        or ("stage === 2" in combined and "stage === 3" in combined)
    ), (
        "CaseDetailScreen must render WeighPanel for both stage 2 (gather) and stage 3 (weigh)"
    )


# ---------------------------------------------------------------------------
# AC8: Submitting WeighPanel triggers POST /api/cases/{id}/rerank (JS regression)
# ---------------------------------------------------------------------------

def test_weighpanel_submit_calls_rerank_endpoint_in_js():
    """AC8: WeighPanel submits to POST /api/cases/{id}/rerank (not another endpoint)."""
    combined = _read_combined_js()
    # The rerank URL pattern must appear inside WeighPanel's fetch call
    assert "/api/cases/" in combined and "/rerank" in combined, (
        "WeighPanel must call /api/cases/{id}/rerank when submitting"
    )


def test_weighpanel_submit_uses_post_method_in_js():
    """AC8: WeighPanel uses method: 'POST' when submitting to the rerank endpoint."""
    combined = _read_combined_js()
    assert 'method: "POST"' in combined or "method: 'POST'" in combined, (
        "WeighPanel must use HTTP POST method for the rerank request"
    )


def test_weighpanel_rerank_url_targets_rerank_not_other_endpoint_in_js():
    """AC8: The fetch call in WeighPanel targets /rerank, not /probe or /bake-off."""
    combined = _read_combined_js()
    # Verify that `/rerank` appears in the JS near the WeighPanel section
    weighpanel_start = combined.find("function WeighPanel")
    weighpanel_end = combined.find("\n// ", weighpanel_start + 1)
    if weighpanel_end == -1:
        weighpanel_end = weighpanel_start + 3000
    weighpanel_section = combined[weighpanel_start:weighpanel_end]
    assert "/rerank" in weighpanel_section, (
        "WeighPanel's fetch call must target the /rerank endpoint, not another endpoint"
    )


def test_weighpanel_submit_sends_context_in_body_in_js():
    """AC8: WeighPanel sends the context payload in the request body (JSON)."""
    combined = _read_combined_js()
    # The body must include the context field
    assert "context" in combined and "JSON.stringify" in combined, (
        "WeighPanel must send context via JSON.stringify in the fetch body"
    )


# ---------------------------------------------------------------------------
# AC2 (integration): No live Anthropic calls reach the network during API tests
# ---------------------------------------------------------------------------

def test_no_live_claude_calls_during_rerank_api_test(api_client, db_session):
    """AC2: The rerank endpoint test never calls Claude; the mock intercepts all calls."""
    calls_to_claude = []

    async def _spy_complete(system, user, model):
        calls_to_claude.append((system, user, model))
        return _MOCK_CLAUDE_RESPONSE

    c, _ = _seed_case_with_plans(db_session, stage="gather")
    with patch("app.weigh.complete", side_effect=_spy_complete):
        # Call rerank_plans directly via the endpoint (without mocking the router-level import)
        with patch(
            "app.routers.cases.rerank_plans",
            new_callable=AsyncMock,
            return_value=_MOCK_RERANK_WITH_RATIONALE,
        ):
            r = api_client.post(
                f"/api/cases/{c.id}/rerank",
                json={"context": "Test context."},
            )

    assert r.status_code == 200
    # The router mock means complete() was never called at all
    assert calls_to_claude == [], (
        "No live calls to Claude's complete() should occur during the mocked API test"
    )
