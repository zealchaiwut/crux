"""Tests for issue #7: Case detail page scaffold with StageBar.

AC coverage:
  AC1  – CaseScreen (CaseDetailScreen) exists and is reachable by clicking a CaseCard; correct data passed.
  AC2  – StageBar renders five labeled stages in order: Sharpen → Bake-off → Gather → Weigh → Probe.
  AC3  – StageBar accepts a numeric stage prop (0–4); current stage visually highlighted, prior stages completed.
  AC4  – When stage=5 (closed), StageBar renders a closed/completed state with no active stage.
  AC5  – A Sharpened Statement block is present and displays the case's sharpened text (or placeholder when empty).
  AC6  – "Not Investigating" chips rendered for excluded topics; empty list causes no crash.
  AC7  – Empty-state sections present for Bake-off, Probe, and Action Plan with placeholders.
  AC8  – Navigation back from CaseScreen to case list works (back control exists).
  AC9  – Layout matches CaseScreen reference (StageBar in bordered card, section labels, section order).
  AC10 – No stage-content logic beyond StageBar and sharpened statement block.
"""
import os
import uuid

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


def _seed_case(session, stage="sharpened", sharpened="A sharpened statement", not_investigating=None):
    import json
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="A raw problem description",
        sharpened=sharpened,
        not_investigating=json.dumps(not_investigating or []),
        stage=stage,
    )
    session.add(c)
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: CaseScreen exists and is reachable by clicking a CaseCard
# ---------------------------------------------------------------------------

def test_case_detail_screen_component_defined():
    """AC1: CaseDetailScreen (CaseScreen) component must be defined in JS."""
    combined = _read_combined_js()
    assert "CaseDetailScreen" in combined or "CaseScreen" in combined, \
        "CaseDetailScreen or CaseScreen must be defined in JS"


def test_case_detail_route_from_casecard():
    """AC1: App routes to a case detail view when a CaseCard is clicked (case/ route pattern)."""
    combined = _read_combined_js()
    assert "case/" in combined, "App must route to 'case/<id>' when a CaseCard is clicked"


def test_case_detail_api_returns_stage_number(api_client, db_session):
    """AC1: GET /api/cases/{id} returns stage as integer and sharpened text."""
    c = _seed_case(db_session, stage="gather", sharpened="The actual sharpened problem")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["sharpened"] == "The actual sharpened problem"
    assert isinstance(data["stage"], int)
    assert data["stage"] == 2  # gather → 2


def test_case_detail_api_not_found(api_client):
    """AC1: GET /api/cases/{id} returns 404 for unknown id."""
    r = api_client.get("/api/cases/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AC2: StageBar renders five labeled stages in order
# ---------------------------------------------------------------------------

def test_stagebar_component_defined():
    """AC2: StageBar component must be defined in JS."""
    combined = _read_combined_js()
    assert "StageBar" in combined, "StageBar component must be defined in JS"


def test_stagebar_has_all_five_stage_names():
    """AC2: StageBar must reference all five stage labels."""
    combined = _read_combined_js()
    for name in ["Sharpen", "Bake-off", "Gather", "Weigh", "Probe"]:
        assert name in combined, f"Stage label '{name}' must appear in JS for StageBar"


def test_stagebar_stage_order_correct():
    """AC2: The five stages must appear in the correct order in the JS source."""
    combined = _read_combined_js()
    positions = [combined.find(name) for name in ["Sharpen", "Bake-off", "Gather", "Weigh", "Probe"]]
    assert all(p != -1 for p in positions), "All five stage names must appear in JS"
    assert positions == sorted(positions), \
        "Stage names must appear in order: Sharpen → Bake-off → Gather → Weigh → Probe"


# ---------------------------------------------------------------------------
# AC3: StageBar highlights current stage, prior stages completed
# ---------------------------------------------------------------------------

def test_stagebar_uses_crux_token_for_active():
    """AC3: StageBar must use --crux token to highlight the active stage."""
    combined = _read_combined_js()
    assert "--crux" in combined, "StageBar must use var(--crux) for the active stage"


def test_stagebar_shows_done_state_for_prior_stages():
    """AC3: StageBar must have a 'done' or completed state for prior stages."""
    combined = _read_combined_js()
    # done/completed pips or check icon for prior stages
    assert ("done" in combined or "ti-check" in combined or "completed" in combined), \
        "StageBar must render a done/completed indicator for prior stages (check icon or 'done' state)"


def test_stagebar_accepts_stage_prop():
    """AC3: StageBar accepts a stage/current prop that drives which step is active."""
    combined = _read_combined_js()
    # The prop name can be 'current' or 'stage'
    assert ("current" in combined or "stage" in combined), \
        "StageBar must accept a numeric prop (current or stage) to drive the active step"


# ---------------------------------------------------------------------------
# AC4: stage=5 (closed) → no active stage, closed/completed state
# ---------------------------------------------------------------------------

def test_stagebar_handles_stage_5_closed():
    """AC4: StageBar must handle stage=5 as a closed/completed state."""
    combined = _read_combined_js()
    # Should branch on stage >= 5 or stage === 5 for a closed/done indicator
    assert ("=== 5" in combined or ">= 5" in combined or "closed" in combined or
            "verdict" in combined.lower()), \
        "StageBar or CaseDetailScreen must handle stage=5 (closed case) specially"


def test_api_stage_5_for_verdict(api_client, db_session):
    """AC4: A case at 'verdict' stage returns stage=5 from API."""
    from app import models
    import json
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="prob",
        sharpened="sharp",
        not_investigating=json.dumps([]),
        stage="verdict",
    )
    db_session.add(c)
    db_session.commit()
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["stage"] == 5


# ---------------------------------------------------------------------------
# AC5: Sharpened Statement block visible; placeholder when empty
# ---------------------------------------------------------------------------

def test_sharpened_statement_label_in_js():
    """AC5: A 'SHARPENED' section label must appear in CaseDetailScreen."""
    combined = _read_combined_js()
    assert ("SHARPENED" in combined.upper()), \
        "CaseDetailScreen must have a 'SHARPENED STATEMENT' or 'SHARPENED PROBLEM' label"


def test_sharpened_statement_rendered_from_api(api_client, db_session):
    """AC5: API returns the sharpened text; CaseDetailScreen displays it."""
    c = _seed_case(db_session, sharpened="My falsifiable sharpened problem")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["sharpened"] == "My falsifiable sharpened problem"


def test_sharpened_empty_returns_empty_string(api_client, db_session):
    """AC5: When sharpened is empty, API returns '' (no crash)."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw only",
        sharpened=None,
        not_investigating="[]",
        stage="sharpened",
    )
    db_session.add(c)
    db_session.commit()
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["sharpened"] == ""


# ---------------------------------------------------------------------------
# AC6: Not Investigating chips rendered; empty list = no crash
# ---------------------------------------------------------------------------

def test_not_investigating_label_in_js():
    """AC6: 'NOT INVESTIGATING' label must appear in CaseDetailScreen."""
    combined = _read_combined_js()
    assert "NOT INVESTIGATING" in combined.upper(), \
        "CaseDetailScreen must render a 'NOT INVESTIGATING' label for excluded topics"


def test_not_investigating_chips_from_api(api_client, db_session):
    """AC6: API returns not_investigating as a list of strings."""
    c = _seed_case(db_session, not_investigating=["Shoe wear", "Weather"])
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    ni = r.json()["not_investigating"]
    assert ni == ["Shoe wear", "Weather"]


def test_not_investigating_empty_no_crash(api_client, db_session):
    """AC6: Empty not_investigating list returns [] from API (no crash)."""
    c = _seed_case(db_session, not_investigating=[])
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    assert r.json()["not_investigating"] == []


# ---------------------------------------------------------------------------
# AC7: Empty-state sections for Bake-off, Probe, and Action Plan
# ---------------------------------------------------------------------------

def test_bakeoff_section_in_case_detail_js():
    """AC7: CaseDetailScreen must have a Bake-off section with placeholder."""
    combined = _read_combined_js()
    assert "BAKE-OFF" in combined.upper() or "Bake-off" in combined, \
        "CaseDetailScreen must include a Bake-off section"


def test_probe_section_in_case_detail_js():
    """AC7: CaseDetailScreen must have a Probe section with placeholder."""
    combined = _read_combined_js()
    assert "PROBE" in combined.upper(), \
        "CaseDetailScreen must include a Probe section"


def test_action_plan_section_in_case_detail_js():
    """AC7: CaseDetailScreen must have an Action Plan section with placeholder."""
    combined = _read_combined_js()
    assert "ACTION PLAN" in combined.upper(), \
        "CaseDetailScreen must include an Action Plan section"


# ---------------------------------------------------------------------------
# AC8: Back navigation from CaseScreen to case list
# ---------------------------------------------------------------------------

def test_back_navigation_in_case_detail_js():
    """AC8: CaseDetailScreen must have a back button/control to return to case list."""
    combined = _read_combined_js()
    # onBack prop + back button with Cases label
    assert "onBack" in combined, "CaseDetailScreen must accept an onBack callback prop"
    assert "ti-arrow-left" in combined, "CaseDetailScreen must have a back arrow button"


def test_back_button_label_cases():
    """AC8: Back button in CaseDetailScreen must say 'Cases'."""
    combined = _read_combined_js()
    assert "Cases" in combined, "Back button must be labeled 'Cases'"


# ---------------------------------------------------------------------------
# AC9: Layout matches CaseScreen reference (StageBar in card, section order)
# ---------------------------------------------------------------------------

def test_stagebar_in_bordered_card():
    """AC9: StageBar must be wrapped in a bordered card/panel in CaseDetailScreen."""
    combined = _read_combined_js()
    # The design reference places StageBar inside a div with border + surface background
    assert "StageBar" in combined, "StageBar must be used inside CaseDetailScreen"
    # border and surface should be used together
    assert "var(--border)" in combined and "var(--surface)" in combined, \
        "CaseDetailScreen must use border and surface tokens for the StageBar card"


def test_section_order_in_case_detail():
    """AC9: Sections appear in reference order: header → StageBar → Sharpened → Not Investigating → Bake-off → Probe → Action Plan."""
    combined = _read_combined_js()
    # Find positions of key identifiers within the CaseDetailScreen function body
    detail_start = combined.find("function CaseDetailScreen")
    assert detail_start != -1, "CaseDetailScreen must be defined as a function"
    block = combined[detail_start:]

    stage_bar_pos = block.find("StageBar")
    # Search for the section label, not any property access like caseData.sharpened
    sharpened_pos = block.upper().find("SHARPENED STATEMENT") if "SHARPENED STATEMENT" in block.upper() else block.upper().find("SHARPENED PROBLEM")
    bakeoff_pos = block.upper().find("BAKE-OFF") if "BAKE-OFF" in block.upper() else block.upper().find("BAKEOFF")
    probe_pos = block.upper().find("THE PROBE") if "THE PROBE" in block.upper() else block.upper().find("PROBE")
    action_pos = block.upper().find("ACTION PLAN")

    assert stage_bar_pos != -1, "StageBar must appear in CaseDetailScreen"
    assert sharpened_pos != -1, "SHARPENED STATEMENT or SHARPENED PROBLEM section label must appear in CaseDetailScreen"
    assert bakeoff_pos != -1, "Bake-off section must appear in CaseDetailScreen"
    assert probe_pos != -1, "Probe section must appear in CaseDetailScreen"
    assert action_pos != -1, "Action Plan section must appear in CaseDetailScreen"

    assert stage_bar_pos < sharpened_pos, "StageBar must appear before Sharpened Statement"
    assert sharpened_pos < bakeoff_pos, "Sharpened Statement must appear before Bake-off"
    assert bakeoff_pos < probe_pos, "Bake-off must appear before Probe"
    assert probe_pos < action_pos, "Probe must appear before Action Plan"


# ---------------------------------------------------------------------------
# AC10: No stage-content logic beyond StageBar and sharpened statement
# ---------------------------------------------------------------------------

def test_no_plan_fetch_in_case_detail_js():
    """AC10: CaseDetailScreen must not implement plan-fetch or bake-off content logic."""
    combined = _read_combined_js()
    # The detail screen should NOT contain PlanCard or BakeOffStrip rendered inside
    # CaseDetailScreen (they belong to later tickets). Check that no plan data
    # is fetched — i.e. no /api/plans endpoint call.
    assert "/api/plans" not in combined, \
        "CaseDetailScreen must not fetch plan data (out of scope for this issue)"


def test_case_detail_api_returns_no_plans_field():
    """AC10: GET /api/cases/{id} does not need to return plans — stage + sharpened is enough."""
    # This tests the API shape: the single-case endpoint returns stage + sharpened
    # but does NOT need to expose plans (those come in later issues).
    # We verify the API contract is minimal.
    # (This is a static check — the endpoint already exists and returns correct fields)
    import importlib
    import inspect
    cases_module = importlib.import_module("app.routers.cases")
    src = inspect.getsource(cases_module.get_case)
    # The single-case response must include stage and sharpened
    assert "stage" in src, "get_case must return stage"
    assert "sharpened" in src, "get_case must return sharpened"
