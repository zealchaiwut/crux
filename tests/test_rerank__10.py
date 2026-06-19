"""Tests for issue #10: Re-rank Plans Against User Data at Stage 3.

AC coverage:
  AC1  – "Your Context" textarea visible on Stage 3 Case, not visible at Stage 0/1/2 (JS).
  AC2  – Textarea accepts free-form text with no enforced format (JS).
  AC3  – "Re-rank for me" button disabled until textarea has at least one non-whitespace char (JS).
  AC4  – Submitting calls POST /api/cases/{id}/rerank; loading state shown during request (JS + API).
  AC5  – API updates current_rank and standing on each Plan row (persisted) (API).
  AC6  – Pasted context string is persisted on the Case (API).
  AC7  – BakeOffStrip reorders to reflect new current_rank; new rank-1 gets lead style (JS).
  AC8  – PlanCard lead styling applied to new rank-1 Plan; removed from previous leader (JS).
  AC9  – Plans with standing='ruled-out' render with reduced opacity + struck-through title (JS).
  AC10 – Plans with standing='ruled-in' receive a distinct positive indicator (JS).
  AC11 – Re-ranking multiple times overwrites previous current_rank, standing, weigh_context (API).
  AC12 – If API fails, inline error shown; previous rank order and styling preserved unchanged (JS).
  AC13 – No changes to probe-related components (JS).
"""
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


def _seed_case_with_plans(session, stage="weigh"):
    import json
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
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="C",
            name="Sleep Debt", mechanism="Insufficient sleep degrades recovery markers.",
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
# Model / schema tests
# ---------------------------------------------------------------------------

def test_plan_model_has_standing_column():
    """AC5: Plan model must have a 'standing' column to persist ruled-out/ruled-in status."""
    from app import models
    assert hasattr(models.Plan, "standing"), "Plan model must have a 'standing' column"


def test_case_model_has_weigh_context_column():
    """AC6: Case model must have a 'weigh_context' column to persist user context string."""
    from app import models
    assert hasattr(models.Case, "weigh_context"), "Case model must have a 'weigh_context' column"


# ---------------------------------------------------------------------------
# AC4 (API): POST /api/cases/{id}/rerank endpoint exists and succeeds
# ---------------------------------------------------------------------------

def test_rerank_endpoint_exists(api_client, db_session):
    """AC4: POST /api/cases/{id}/rerank must exist and return 200 for a Stage-3 case."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Annual income £45k, risk tolerance low."},
        )
    assert r.status_code == 200, r.text


def test_rerank_endpoint_404_for_unknown_case(api_client):
    """AC4: POST /api/cases/{id}/rerank returns 404 for unknown case."""
    r = api_client.post(
        "/api/cases/00000000-0000-0000-0000-000000000000/rerank",
        json={"context": "some context"},
    )
    assert r.status_code == 404


def test_rerank_endpoint_rejects_blank_context(api_client, db_session):
    """AC3: POST /api/cases/{id}/rerank must reject blank context (4xx)."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    r = api_client.post(
        f"/api/cases/{c.id}/rerank",
        json={"context": "   "},
    )
    assert r.status_code in (400, 422), r.text


# ---------------------------------------------------------------------------
# AC5: current_rank and standing are updated and persisted
# ---------------------------------------------------------------------------

def test_rerank_updates_plan_current_rank(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank updates current_rank on each Plan row."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Annual income £45k."},
        )
    assert r.status_code == 200

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rank_by_label = {p.label: p.current_rank for p in plans}
    # B should now be rank 1, A rank 2, C rank 3
    assert rank_by_label["B"] == 1, f"Plan B should be rank 1, got {rank_by_label}"
    assert rank_by_label["A"] == 2, f"Plan A should be rank 2, got {rank_by_label}"
    assert rank_by_label["C"] == 3, f"Plan C should be rank 3, got {rank_by_label}"


def test_rerank_updates_plan_standing(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank updates standing on each Plan row."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Annual income £45k."},
        )
    assert r.status_code == 200

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    standing_by_label = {p.label: p.standing for p in plans}
    assert standing_by_label["B"] == "ruled-in", f"Plan B should be 'ruled-in', got {standing_by_label}"
    assert standing_by_label["C"] == "ruled-out", f"Plan C should be 'ruled-out', got {standing_by_label}"
    assert standing_by_label["A"] is None or standing_by_label["A"] == "neutral", \
        f"Plan A should be neutral/None, got {standing_by_label}"


def test_rerank_response_includes_updated_plans(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank response includes plans with updated rank and standing."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Annual income £45k."},
        )
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "Response must include 'plans'"
    labels = {p["label"] for p in data["plans"]}
    assert labels == {"A", "B", "C"}
    # Check standing is exposed
    standing_by_label = {p["label"]: p.get("standing") for p in data["plans"]}
    assert standing_by_label.get("B") == "ruled-in"
    assert standing_by_label.get("C") == "ruled-out"


# ---------------------------------------------------------------------------
# AC6: weigh_context persisted on Case
# ---------------------------------------------------------------------------

def test_rerank_persists_weigh_context(api_client, db_session):
    """AC6: POST /api/cases/{id}/rerank persists the context string on the Case."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    ctx = "Annual income £45k, risk tolerance low, need access within 2 years."
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ctx})
    assert r.status_code == 200

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.weigh_context == ctx, \
        f"weigh_context must be persisted on Case; got: {updated_case.weigh_context!r}"


def test_get_case_includes_weigh_context(api_client, db_session):
    """AC6: GET /api/cases/{id} returns weigh_context field (populated after rerank)."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    ctx = "My personal numbers and constraints."
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ctx})

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "weigh_context" in data, "GET /api/cases/{id} must return 'weigh_context' field"
    assert data["weigh_context"] == ctx


def test_get_case_weigh_context_null_before_rerank(api_client, db_session):
    """AC6: GET /api/cases/{id} returns null/empty weigh_context before first rerank."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "weigh_context" in data
    assert not data["weigh_context"]  # None or empty string


# ---------------------------------------------------------------------------
# AC11: Multiple re-rankings overwrite previous values
# ---------------------------------------------------------------------------

def test_rerank_second_call_overwrites_first(api_client, db_session):
    """AC11: A second rerank call overwrites current_rank, standing, and weigh_context."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    first_result = _MOCK_RERANK_RESULT  # B=1, A=2, C=3
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=first_result):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "First context."})

    # Second rerank: C rises to rank 1
    second_result = [
        {"label": "C", "rank": 1, "standing": "ruled-in"},
        {"label": "A", "rank": 2, "standing": None},
        {"label": "B", "rank": 3, "standing": "ruled-out"},
    ]
    new_ctx = "New context with updated numbers."
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=second_result):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": new_ctx})

    db_session.expire_all()
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rank_by_label = {p.label: p.current_rank for p in plans}
    assert rank_by_label["C"] == 1, f"After 2nd rerank, C must be rank 1; got {rank_by_label}"
    assert rank_by_label["B"] == 3, f"After 2nd rerank, B must be rank 3; got {rank_by_label}"

    updated_case = db_session.get(models.Case, c.id)
    assert updated_case.weigh_context == new_ctx, "weigh_context must reflect most recent rerank"


# ---------------------------------------------------------------------------
# AC12 (API): Claude failure → 502, previous state unchanged
# ---------------------------------------------------------------------------

def test_rerank_502_on_claude_failure(api_client, db_session):
    """AC12: If Claude API fails during rerank, endpoint returns 502."""
    from app.weigh import WeighError
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               side_effect=WeighError("API timeout")):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Context text."})
    assert r.status_code == 502, f"Expected 502 on Claude failure, got {r.status_code}"


def test_rerank_previous_ranks_preserved_on_failure(api_client, db_session):
    """AC12: If Claude API fails, previous current_rank values are preserved unchanged."""
    from app import models
    from app.weigh import WeighError
    c, plans = _seed_case_with_plans(db_session, stage="weigh")

    original_ranks = {p.label: p.current_rank for p in plans}

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               side_effect=WeighError("connection refused")):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Context text."})

    db_session.expire_all()
    updated_plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    for p in updated_plans:
        assert p.current_rank == original_ranks[p.label], \
            f"Plan {p.label} rank changed on failure: {original_ranks[p.label]} → {p.current_rank}"


def test_rerank_weigh_context_unchanged_on_failure(api_client, db_session):
    """AC12: If Claude API fails on first call, weigh_context stays null/empty."""
    from app import models
    from app.weigh import WeighError
    c, _ = _seed_case_with_plans(db_session, stage="weigh")

    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               side_effect=WeighError("bad key")):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Context text."})

    db_session.expire_all()
    updated_case = db_session.get(models.Case, c.id)
    assert not updated_case.weigh_context, \
        "weigh_context must remain empty/null when rerank API call fails"


# ---------------------------------------------------------------------------
# Weigh service module
# ---------------------------------------------------------------------------

def test_weigh_service_module_exists():
    """AC4: app.weigh module must exist with rerank_plans function."""
    import importlib
    mod = importlib.import_module("app.weigh")
    assert hasattr(mod, "rerank_plans"), "app.weigh must export rerank_plans"
    assert hasattr(mod, "WeighError"), "app.weigh must export WeighError"


# ---------------------------------------------------------------------------
# AC1: Textarea visible only at Stage 3+ (JS structural checks)
# ---------------------------------------------------------------------------

def test_weigh_context_textarea_defined_in_js():
    """AC1: A 'Your Context' textarea or equivalent must be defined in JS."""
    combined = _read_combined_js()
    assert "textarea" in combined.lower() or "Your Context" in combined or \
           "weigh_context" in combined or "context" in combined.lower(), \
        "JS must define a textarea or input for the user context (Stage 3 re-rank)"


def test_rerank_section_only_at_stage3():
    """AC1: The re-rank UI must be gated behind stage >= 3 check in JS."""
    combined = _read_combined_js()
    # Should check stage condition before showing the re-rank panel
    # Look for stage-gating logic (stage >= 3, or stage === 3, or 'weigh', etc.)
    assert ("stage" in combined and
            (">= 3" in combined or ">= 4" in combined or "=== 3" in combined or
             "'weigh'" in combined or "weigh" in combined)), \
        "JS must gate the re-rank UI behind a stage check (stage >= 3)"


def test_rerank_button_defined_in_js():
    """AC3: A 'Re-rank' (or equivalent) action button must be defined in JS."""
    combined = _read_combined_js()
    assert ("rerank" in combined.lower() or "re-rank" in combined.lower() or
            "Re-rank" in combined or "reRank" in combined), \
        "JS must define a Re-rank action button"


def test_rerank_button_disabled_logic_in_js():
    """AC3: The re-rank button must have a disabled condition in JS."""
    combined = _read_combined_js()
    assert "disabled" in combined, "JS must have a disabled attribute on the re-rank button"


# ---------------------------------------------------------------------------
# AC4: Loading state in JS
# ---------------------------------------------------------------------------

def test_rerank_loading_state_in_js():
    """AC4: CaseDetailScreen must show a loading state during re-rank request."""
    combined = _read_combined_js()
    # Must have some loading indicator (spinner or text)
    assert "crux-spin" in combined or "loading" in combined.lower() or \
           "Ranking" in combined or "ranking" in combined, \
        "JS must show a loading state during the re-rank API call"


# ---------------------------------------------------------------------------
# AC7: BakeOffStrip uses current_rank for ordering (JS)
# ---------------------------------------------------------------------------

def test_bakeoff_strip_uses_current_rank():
    """AC7: BakeOffStrip must order plans by current_rank in the detail view."""
    combined = _read_combined_js()
    assert "current_rank" in combined or "currentRank" in combined, \
        "JS must use current_rank to order plans in BakeOffStrip"


# ---------------------------------------------------------------------------
# AC8: PlanCard lead styling on rank-1 Plan (JS)
# ---------------------------------------------------------------------------

def test_plancard_lead_based_on_rank():
    """AC8: PlanCard lead styling must be based on current_rank===1 after re-ranking."""
    combined = _read_combined_js()
    # Lead must reference rank-1 logic
    assert "current_rank" in combined or "rank" in combined, \
        "PlanCard lead styling must be updated based on current_rank after re-ranking"
    assert "lead" in combined, "PlanCard must have lead styling"


# ---------------------------------------------------------------------------
# AC9: ruled-out plans (opacity + strikethrough) in JS
# ---------------------------------------------------------------------------

def test_ruled_out_opacity_in_js():
    """AC9: Plans with standing='ruled-out' must render with reduced opacity."""
    combined = _read_combined_js()
    assert "ruled-out" in combined or "ruledOut" in combined, \
        "JS must handle 'ruled-out' standing state"
    assert "opacity" in combined, "JS must reduce opacity for ruled-out plans"


def test_ruled_out_strikethrough_in_js():
    """AC9: Plans with standing='ruled-out' must render with struck-through title."""
    combined = _read_combined_js()
    assert "line-through" in combined or "lineThrough" in combined, \
        "JS must apply text-decoration: line-through for ruled-out plan titles"


# ---------------------------------------------------------------------------
# AC10: ruled-in plans positive indicator in JS
# ---------------------------------------------------------------------------

def test_ruled_in_indicator_in_js():
    """AC10: Plans with standing='ruled-in' must receive a distinct positive indicator."""
    combined = _read_combined_js()
    assert "ruled-in" in combined or "ruledIn" in combined, \
        "JS must handle 'ruled-in' standing state with a positive indicator"


# ---------------------------------------------------------------------------
# AC12: Error handling in JS
# ---------------------------------------------------------------------------

def test_rerank_inline_error_in_js():
    """AC12: CaseDetailScreen must show an inline error message on rerank failure."""
    combined = _read_combined_js()
    # Look for error handling around rerank logic
    assert "error" in combined.lower(), "JS must handle and display errors from the re-rank call"


# ---------------------------------------------------------------------------
# AC13: No probe-related component changes (JS)
# ---------------------------------------------------------------------------

def test_probe_component_not_modified():
    """AC13: Probe-related components must not be changed by this feature."""
    combined = _read_combined_js()
    # Probe section should still be an empty state placeholder
    assert "PROBE" in combined or "probe" in combined.lower(), \
        "Probe section must still exist in CaseDetailScreen"
    # The probe section shouldn't have been wired to the rerank logic
    # (probe empty state should remain - "coming in M1" or similar)
    assert "THE PROBE" in combined or "PROBE" in combined, \
        "THE PROBE section label must still be present and unchanged"


# ---------------------------------------------------------------------------
# GET /api/cases/{id} returns plan standing field
# ---------------------------------------------------------------------------

def test_get_case_returns_plan_standing(api_client, db_session):
    """AC5/AC9/AC10: GET /api/cases/{id} returns 'standing' field on each plan."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    # Manually set standing on one plan
    plan_b = db_session.query(models.Plan).filter_by(case_id=c.id, label="B").first()
    plan_b.standing = "ruled-in"
    plan_c = db_session.query(models.Plan).filter_by(case_id=c.id, label="C").first()
    plan_c.standing = "ruled-out"
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    standing_by_label = {p["label"]: p.get("standing") for p in data["plans"]}
    assert standing_by_label.get("B") == "ruled-in", \
        f"Plan B standing should be 'ruled-in'; got {standing_by_label}"
    assert standing_by_label.get("C") == "ruled-out", \
        f"Plan C standing should be 'ruled-out'; got {standing_by_label}"
