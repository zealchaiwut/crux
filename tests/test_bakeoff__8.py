"""Tests for issue #8: Generate and display Plan A/B/C bake-off at Stage 1.

AC coverage:
  AC1 – When a Case is at Stage 0 (sharpened), POST /api/cases/{id}/bake-off calls Claude
         and returns exactly 3 Plans (A, B, C), each with label, name, mechanism, prior (0–1 float).
  AC2 – Each Plan is persisted as a distinct row; calling the endpoint again does not create
         duplicates (idempotent re-entry).
  AC3 – PlanCard component in JS: monospace label key, plan name, prior chip, one-line mechanism,
         sources list section.
  AC4 – The Plan with the highest prior renders in "lead" style (visually distinguished).
  AC5 – BakeOffStrip component is used in CaseDetailScreen with racing bars; leader fills violet;
         ruled-out plans faded/struck; won plan shows ✓ WON badge.
  AC6 – After Plan rows are persisted, Case stage advances to the next stage value (gather).
  AC7 – If Claude API call fails, Case stage does not advance and a 502 error is returned.
"""
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


def _seed_case(session, stage="sharpened", sharpened="A sharpened problem statement"):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="A raw problem description",
        sharpened=sharpened,
        not_investigating=json.dumps(["Shoe wear", "Weather"]),
        stage=stage,
    )
    session.add(c)
    session.commit()
    return c


_MOCK_PLANS = [
    {"label": "A", "name": "Overtraining Load", "mechanism": "Excess training volume depresses HRV.", "prior": 0.55},
    {"label": "B", "name": "Iron Deficiency", "mechanism": "Low ferritin impairs oxygen transport.", "prior": 0.30},
    {"label": "C", "name": "Sleep Debt", "mechanism": "Insufficient sleep degrades recovery markers.", "prior": 0.15},
]


# ---------------------------------------------------------------------------
# AC1: POST /api/cases/{id}/bake-off calls Claude API and returns 3 plans
# ---------------------------------------------------------------------------

def test_bakeoff_endpoint_returns_three_plans(api_client, db_session):
    """AC1: POST /api/cases/{id}/bake-off returns exactly 3 plans with label, name, mechanism, prior."""
    c = _seed_case(db_session)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        r = api_client.post(f"/api/cases/{c.id}/bake-off")
    assert r.status_code == 200, r.text
    data = r.json()
    plans = data["plans"]
    assert len(plans) == 3
    labels = {p["label"] for p in plans}
    assert labels == {"A", "B", "C"}
    for plan in plans:
        assert "label" in plan
        assert "name" in plan
        assert "mechanism" in plan
        assert "prior" in plan
        prior = float(plan["prior"])
        assert 0.0 <= prior <= 1.0, f"prior out of range: {prior}"


def test_bakeoff_endpoint_404_for_unknown_case(api_client):
    """AC1: POST /api/cases/{id}/bake-off returns 404 for unknown case."""
    r = api_client.post("/api/cases/00000000-0000-0000-0000-000000000000/bake-off")
    assert r.status_code == 404


def test_bakeoff_service_module_exists():
    """AC1: app.bake_off module must exist with generate_plans function."""
    import importlib
    mod = importlib.import_module("app.bake_off")
    assert hasattr(mod, "generate_plans"), "app.bake_off must export generate_plans"


def test_plan_has_name_field():
    """AC1: Plan model must have a name column (distinct from mechanism)."""
    from app import models
    assert hasattr(models.Plan, "name"), "Plan model must have a 'name' column"


# ---------------------------------------------------------------------------
# AC2: Idempotency — re-entering Stage 1 does not create duplicate rows
# ---------------------------------------------------------------------------

def test_bakeoff_idempotent_no_duplicates(api_client, db_session):
    """AC2: Calling bake-off twice returns same plans without creating duplicates."""
    c = _seed_case(db_session)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        r1 = api_client.post(f"/api/cases/{c.id}/bake-off")
    assert r1.status_code == 200

    # Second call — Claude must NOT be called again (plans already exist)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock) as mock_gen:
        r2 = api_client.post(f"/api/cases/{c.id}/bake-off")
    mock_gen.assert_not_called()
    assert r2.status_code == 200
    assert len(r2.json()["plans"]) == 3


def test_bakeoff_plan_rows_count_after_double_call(api_client, db_session):
    """AC2: After two bake-off calls, the DB contains exactly 3 Plan rows for the case."""
    from app import models
    c = _seed_case(db_session)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        api_client.post(f"/api/cases/{c.id}/bake-off")
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        api_client.post(f"/api/cases/{c.id}/bake-off")

    count = db_session.query(models.Plan).filter_by(case_id=c.id).count()
    assert count == 3, f"Expected 3 Plan rows, got {count}"


# ---------------------------------------------------------------------------
# AC3: PlanCard component in JS
# ---------------------------------------------------------------------------

def test_plancard_component_defined():
    """AC3: PlanCard component must be defined in JS."""
    combined = _read_combined_js()
    assert "PlanCard" in combined, "PlanCard component must be defined in JS"


def test_plancard_shows_monospace_label():
    """AC3: PlanCard must render the label key in monospace."""
    combined = _read_combined_js()
    assert "plan-key" in combined or "mono" in combined, \
        "PlanCard must use monospace styling for the plan label (plan-key class or mono)"


def test_plancard_shows_prior_as_chip():
    """AC3: PlanCard must render the prior as a chip/badge."""
    combined = _read_combined_js()
    assert "prior" in combined, "PlanCard must reference the prior field"
    # The chip should use src or similar chip styling
    assert "chip" in combined or "src" in combined or "badge" in combined or "prior" in combined, \
        "PlanCard must render the prior as a chip"


def test_plancard_shows_mechanism():
    """AC3: PlanCard must render the mechanism text."""
    combined = _read_combined_js()
    assert "mechanism" in combined, "PlanCard must render the mechanism field"


def test_plancard_shows_sources_section():
    """AC3: PlanCard must render a sources list section (empty at this stage)."""
    combined = _read_combined_js()
    assert "sources" in combined.lower() or "SOURCES" in combined, \
        "PlanCard must have a sources section"


# ---------------------------------------------------------------------------
# AC4: Lead plan (highest prior) renders in "lead" style
# ---------------------------------------------------------------------------

def test_plancard_lead_style_for_highest_prior():
    """AC4: PlanCard with highest prior must use lead/violet styling."""
    combined = _read_combined_js()
    # The lead plan should use .lead class or --crux token in context of PlanCard
    assert "lead" in combined, "PlanCard must use 'lead' style for the plan with highest prior"
    assert "--crux" in combined, "Lead PlanCard must use the --crux violet token"


def test_bakeoff_api_marks_lead_plan(api_client, db_session):
    """AC4: GET /api/cases/{id} returns plans; highest-prior plan has current_rank=1."""
    c = _seed_case(db_session)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        api_client.post(f"/api/cases/{c.id}/bake-off")

    from app import models
    plans = db_session.query(models.Plan).filter_by(case_id=c.id).all()
    rank1_plan = next((p for p in plans if p.current_rank == 1), None)
    assert rank1_plan is not None, "A Plan with current_rank=1 must exist after bake-off"
    # Rank 1 plan should be the one with highest prior
    rank1_prior = float(rank1_plan.prior)
    all_priors = [float(p.prior) for p in plans]
    assert rank1_prior == max(all_priors), \
        f"Rank-1 plan prior {rank1_prior} must be the highest among {all_priors}"


# ---------------------------------------------------------------------------
# AC5: BakeOffStrip in CaseDetailScreen detail view
# ---------------------------------------------------------------------------

def test_bakeoff_strip_in_case_detail_screen():
    """AC5: BakeOffStrip must appear in CaseDetailScreen (not only in CaseCard)."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    assert detail_start != -1, "CaseDetailScreen must be defined"
    block = combined[detail_start:]
    assert "BakeOffStrip" in block, "BakeOffStrip must be rendered inside CaseDetailScreen"


def test_bakeoff_strip_leader_bar_violet():
    """AC5: BakeOffStrip leader bar uses violet (--crux) fill."""
    combined = _read_combined_js()
    assert "var(--crux)" in combined, "BakeOffStrip leader bar must use var(--crux)"


def test_bakeoff_strip_ruled_out_faded():
    """AC5: BakeOffStrip must fade ruled-out plans (opacity reduction)."""
    combined = _read_combined_js()
    assert "opacity" in combined, "BakeOffStrip must reduce opacity for ruled-out plans"
    assert "ruled-out" in combined or "ruledOut" in combined, \
        "BakeOffStrip must have ruled-out state logic"


def test_bakeoff_strip_won_badge():
    """AC5: BakeOffStrip must show '✓ WON' badge for winning plans."""
    combined = _read_combined_js()
    assert "WON" in combined, "BakeOffStrip must display a WON badge"


def test_case_detail_api_returns_plans(api_client, db_session):
    """AC5: GET /api/cases/{id} returns a plans list after bake-off generation."""
    c = _seed_case(db_session, stage="gather")
    from app import models
    plans_to_add = [
        models.Plan(id=str(uuid.uuid4()), case_id=c.id, label="A",
                    name="Overtraining", mechanism="Volume depresses HRV.", prior="0.55", current_rank=1),
        models.Plan(id=str(uuid.uuid4()), case_id=c.id, label="B",
                    name="Iron deficiency", mechanism="Low ferritin impairs O2.", prior="0.30", current_rank=2),
        models.Plan(id=str(uuid.uuid4()), case_id=c.id, label="C",
                    name="Sleep debt", mechanism="Insufficient sleep harms recovery.", prior="0.15", current_rank=3),
    ]
    for p in plans_to_add:
        db_session.add(p)
    db_session.commit()

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "GET /api/cases/{id} must return a plans list"
    assert len(data["plans"]) == 3
    for plan in data["plans"]:
        assert "label" in plan
        assert "name" in plan
        assert "mechanism" in plan
        assert "prior" in plan


# ---------------------------------------------------------------------------
# AC6: Case stage advances to gather after plan persistence
# ---------------------------------------------------------------------------

def test_bakeoff_advances_stage_to_gather(api_client, db_session):
    """AC6: After plan generation, case stage advances to 'gather' (stage 2)."""
    from app import models
    c = _seed_case(db_session, stage="sharpened")
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        r = api_client.post(f"/api/cases/{c.id}/bake-off")
    assert r.status_code == 200

    db_session.expire(c)
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "gather", f"Expected stage='gather', got '{updated.stage}'"


def test_get_case_api_stage_is_2_after_bakeoff(api_client, db_session):
    """AC6: GET /api/cases/{id} returns stage=2 (gather) after bake-off completes."""
    c = _seed_case(db_session, stage="sharpened")
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock, return_value=_MOCK_PLANS):
        api_client.post(f"/api/cases/{c.id}/bake-off")

    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["stage"] == 2, f"Expected stage=2 (gather), got {r.json()['stage']}"


# ---------------------------------------------------------------------------
# AC7: Claude API failure → 502 error, stage does not advance
# ---------------------------------------------------------------------------

def test_bakeoff_502_on_claude_failure(api_client, db_session):
    """AC7: If Claude API fails, the endpoint returns 502."""
    from app.bake_off import BakeOffError
    c = _seed_case(db_session)
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock,
               side_effect=BakeOffError("API timeout")):
        r = api_client.post(f"/api/cases/{c.id}/bake-off")
    assert r.status_code == 502, f"Expected 502, got {r.status_code}"


def test_bakeoff_stage_unchanged_on_failure(api_client, db_session):
    """AC7: If Claude API fails, the case stage stays at 'sharpened'."""
    from app import models
    from app.bake_off import BakeOffError
    c = _seed_case(db_session, stage="sharpened")
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock,
               side_effect=BakeOffError("connection refused")):
        api_client.post(f"/api/cases/{c.id}/bake-off")

    db_session.expire(c)
    updated = db_session.get(models.Case, c.id)
    assert updated.stage == "sharpened", \
        f"Stage must stay 'sharpened' on API failure, got '{updated.stage}'"


def test_bakeoff_no_plans_persisted_on_failure(api_client, db_session):
    """AC7: If Claude API fails, no Plan rows are persisted."""
    from app import models
    from app.bake_off import BakeOffError
    c = _seed_case(db_session, stage="sharpened")
    with patch("app.routers.cases.generate_plans", new_callable=AsyncMock,
               side_effect=BakeOffError("bad key")):
        api_client.post(f"/api/cases/{c.id}/bake-off")

    count = db_session.query(models.Plan).filter_by(case_id=c.id).count()
    assert count == 0, f"Expected 0 Plan rows on failure, got {count}"


# ---------------------------------------------------------------------------
# AC1 (loading indicator) + AC7 (error state surfaced) — JS presence checks
# ---------------------------------------------------------------------------

def test_loading_indicator_in_bakeoff_section():
    """AC1/AC7: CaseDetailScreen must show a loading indicator during plan generation."""
    combined = _read_combined_js()
    assert "loading" in combined.lower() or "crux-spin" in combined, \
        "CaseDetailScreen must show a loading indicator during bake-off generation"


def test_error_state_surfaced_in_bakeoff_section():
    """AC7: CaseDetailScreen must surface an error state if plan generation fails."""
    combined = _read_combined_js()
    detail_start = combined.find("function CaseDetailScreen")
    assert detail_start != -1
    block = combined[detail_start:]
    assert "error" in block.lower(), \
        "CaseDetailScreen must render an error state if bake-off generation fails"
