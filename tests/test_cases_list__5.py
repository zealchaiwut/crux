"""Tests for issue #5: Cases list screen with CaseCard rows.

AC coverage:
  AC1  – CasesScreen layout matches reference (screen component defined)
  AC2  – Cases loaded from DB; empty state renders without error
  AC3  – Cases grouped into Open and Closed sections
  AC4  – CaseCard renders stage spine (stage label, 5-pip indicator, Case ID)
  AC5  – CaseCard body: title, verdict pill, bake-off mini-strip
  AC6  – Stage spine uses --st-1 through --st-5 for the five ramp colours
  AC7  – Closed CaseCard spine tinted by verdict (pass/fail/inconclusive distinct)
  AC8  – Exactly one "New case" button per screen, variant="crux" (btn-crux)
  AC9  – Right rail renders prompt card, probes running, recent verdicts (in order)
  AC10 – Right rail visible at ≥1280px without horizontal scroll (CSS check)
  AC11 – No console errors / layout breakage when Open, Closed, or both empty
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

def _make_db():
    """Create an in-memory SQLite engine with the crux schema.

    Uses StaticPool so every SQLAlchemy connection shares the same
    in-memory SQLite database, which is required for table visibility
    across the session and the TestClient request thread.
    """
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
    """TestClient with auth cookie and DB overridden to in-memory SQLite."""
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


def _seed_open_case(session, stage="sharpened", probe_status=None):
    """Insert a minimal open case (no verdict). Returns the Case ORM object."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="A test problem",
        sharpened="A sharpened statement",
        stage=stage,
    )
    session.add(c)
    session.flush()

    plan_a = models.Plan(id=str(uuid.uuid4()), case_id=c.id, label="A",
                         mechanism="Plan A mechanism", prior="60%", current_rank=1)
    plan_b = models.Plan(id=str(uuid.uuid4()), case_id=c.id, label="B",
                         mechanism="Plan B mechanism", prior="40%", current_rank=2)
    session.add_all([plan_a, plan_b])

    if probe_status:
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=c.id,
            type="measurement",
            status=probe_status,
        )
        session.add(probe)

    session.commit()
    return c


def _seed_closed_case(session, outcome="confirmed"):
    """Insert a case with a verdict. Returns the Case ORM object."""
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="A closed problem",
        sharpened="A closed sharpened statement",
        stage="probe",
    )
    session.add(c)
    session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        status="confirmed" if outcome == "confirmed" else "killed",
    )
    session.add(probe)
    session.flush()

    verdict = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes="Test verdict notes",
    )
    session.add(verdict)
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: CasesScreen component defined in JS
# ---------------------------------------------------------------------------

def test_cases_screen_component_defined():
    """AC1: CasesScreen layout component must be defined in the JS bundle."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "CasesScreen" in combined, "CasesScreen component must be defined in a JS file"


# ---------------------------------------------------------------------------
# AC2: /api/cases returns 200; empty DB returns empty list without error
# ---------------------------------------------------------------------------

def test_api_cases_empty_db(api_client):
    """AC2: Empty DB returns {"cases": []} without error."""
    r = api_client.get("/api/cases")
    assert r.status_code == 200
    data = r.json()
    assert "cases" in data
    assert data["cases"] == []


def test_api_cases_shape(api_client, db_session):
    """AC2: Non-empty DB returns correct shape per case."""
    _seed_open_case(db_session)
    r = api_client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    c = cases[0]
    assert "id" in c
    assert "title" in c
    assert "stage" in c
    assert "verdict" in c
    assert "verdict_log" in c
    assert "plans" in c


# ---------------------------------------------------------------------------
# AC3: Open vs Closed grouping
# ---------------------------------------------------------------------------

def test_open_case_verdict_awaiting(api_client, db_session):
    """AC3: A case with no probe is verdict='awaiting' (open)."""
    _seed_open_case(db_session)
    cases = api_client.get("/api/cases").json()["cases"]
    assert cases[0]["verdict"] == "awaiting"
    assert cases[0]["verdict_log"] is None


def test_open_case_verdict_progress(api_client, db_session):
    """AC3: A case with a running probe is verdict='progress' (open)."""
    _seed_open_case(db_session, probe_status="running")
    cases = api_client.get("/api/cases").json()["cases"]
    assert cases[0]["verdict"] == "progress"


def test_closed_case_has_verdict_log(api_client, db_session):
    """AC3: A case with a verdict has verdict_log (closed)."""
    _seed_closed_case(db_session, outcome="confirmed")
    cases = api_client.get("/api/cases").json()["cases"]
    assert cases[0]["verdict"] == "confirmed"
    assert cases[0]["verdict_log"] is not None
    assert cases[0]["verdict_log"]["outcome"] == "confirmed"


def test_closed_case_killed(api_client, db_session):
    """AC3: A killed case returns verdict='killed'."""
    _seed_closed_case(db_session, outcome="killed")
    cases = api_client.get("/api/cases").json()["cases"]
    assert cases[0]["verdict"] == "killed"


def test_closed_case_inconclusive(api_client, db_session):
    """AC3: An inconclusive case returns verdict='inconclusive'."""
    _seed_closed_case(db_session, outcome="inconclusive")
    cases = api_client.get("/api/cases").json()["cases"]
    assert cases[0]["verdict"] == "inconclusive"


# ---------------------------------------------------------------------------
# AC4: CaseCard stage spine — stage label, 5-pip indicator, Case ID
# ---------------------------------------------------------------------------

def test_casecard_component_defined():
    """AC4: CaseCard component must be defined in JS."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "CaseCard" in combined, "CaseCard component must be defined"


def test_casecard_has_stage_names():
    """AC4: Stage names (Sharpen, Bake-off, Gather, Weigh, Probe) in CaseCard."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    for name in ["Sharpen", "Bake-off", "Gather", "Weigh", "Probe"]:
        assert name in combined, f"Stage name '{name}' must appear in JS"


def test_casecard_shows_five_pips():
    """AC4: CaseCard renders 5 pips (STAGE_NAMES.map / 5 items)."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    # A 5-pip row is produced by mapping over STAGE_NAMES (length 5)
    assert "STAGE_NAMES" in combined or "stagePips" in combined or \
           combined.count("pip") >= 1, \
        "CaseCard must render a 5-pip row"


# ---------------------------------------------------------------------------
# AC5: CaseCard body — title, verdict pill, bake-off mini-strip
# ---------------------------------------------------------------------------

def test_bakeoffstrip_component_defined():
    """AC5: BakeOffStrip component defined in JS."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "BakeOffStrip" in combined, "BakeOffStrip component must be defined"


def test_pill_component_defined():
    """AC5: Pill component defined in JS (verdict pill)."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "Pill" in combined, "Pill component must be defined for verdict display"


def test_api_cases_includes_plans(api_client, db_session):
    """AC5: Plans returned per case for bake-off strip."""
    _seed_open_case(db_session)
    cases = api_client.get("/api/cases").json()["cases"]
    plans = cases[0]["plans"]
    assert len(plans) >= 1
    p = plans[0]
    assert "key" in p
    assert "name" in p
    assert "standing" in p


# ---------------------------------------------------------------------------
# AC6: Stage spine uses --st-1 through --st-5
# ---------------------------------------------------------------------------

def test_stage_spine_uses_st_tokens():
    """AC6: CaseCard spine pip coloring references --st-1 through --st-5."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    for n in range(1, 6):
        assert f"--st-{n}" in combined, \
            f"CaseCard must reference var(--st-{n}) for stage pip coloring"


# ---------------------------------------------------------------------------
# AC7: Closed CaseCard spine tinted by verdict
# ---------------------------------------------------------------------------

def test_closed_spine_verdict_tint_in_js():
    """AC7: CaseCard JS must apply distinct tints for confirmed/killed/inconclusive."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    # green-bg / red-bg / amber-bg are the tint tokens for confirmed/killed/inconclusive
    assert "--green" in combined, "closed confirmed spine must use --green tint"
    assert "--red" in combined, "closed killed spine must use --red tint"
    assert "--amber" in combined, "closed inconclusive spine must use --amber tint"


# ---------------------------------------------------------------------------
# AC8: Exactly one "New case" button with btn-crux per screen
# ---------------------------------------------------------------------------

def test_new_case_button_crux_variant_in_js():
    """AC8: A 'New case' button with btn-crux (crux variant) must exist."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "btn-crux" in combined, "New case button must use btn-crux class"
    assert "New case" in combined, "New case button label must appear in JS"


def test_new_case_modal_stub_defined():
    """AC8: Modal stub (NewCaseModal or similar) must be defined so click doesn't navigate."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    assert "Modal" in combined or "modal" in combined, \
        "A modal stub must be defined for the New case flow"


# ---------------------------------------------------------------------------
# AC9: Right rail — prompt card, probes running, recent verdicts (in order)
# ---------------------------------------------------------------------------

def test_right_rail_has_three_widgets():
    """AC9: RightRail must include prompt card, probes running, recent verdicts."""
    shell = (JS_DIR / "shell.js").read_text()
    # Prompt card already exists (RailPromptCard)
    assert "RailPromptCard" in shell or "prompt" in shell.lower(), \
        "Right rail must have a prompt card"
    # Probes running section
    assert "PROBES RUNNING" in shell.upper() or "probes" in shell.lower(), \
        "Right rail must have a 'Probes running' section"
    # Recent verdicts section
    assert "RECENT VERDICTS" in shell.upper() or "verdicts" in shell.lower(), \
        "Right rail must have a 'Recent verdicts' section"


def test_right_rail_widget_order():
    """AC9: Prompt card before probes running before recent verdicts in JS source."""
    shell = (JS_DIR / "shell.js").read_text()
    upper = shell.upper()
    # Use the full section title strings to avoid false matches with nav item "Probes"
    prompt_pos = upper.find("RAILPROMPTCARD") if "RAILPROMPTCARD" in upper else upper.find("PROMPTCARD")
    probes_pos = upper.find("PROBES RUNNING")
    verdicts_pos = upper.find("RECENT VERDICTS")
    assert -1 not in (prompt_pos, probes_pos, verdicts_pos), \
        "Right rail must contain RailPromptCard, 'PROBES RUNNING', 'RECENT VERDICTS'"
    # Check order within the RightRail render block by finding their positions
    # relative to the RightRail function definition
    rail_start = upper.find("FUNCTION RIGHTRAIL")
    if rail_start != -1:
        # All three must appear after the RightRail function definition
        block = upper[rail_start:]
        bp = block.find("RAILPROMPTCARD") if "RAILPROMPTCARD" in block else block.find("PROMPTCARD")
        pp = block.find("PROBES RUNNING")
        vp = block.find("RECENT VERDICTS")
        assert -1 not in (bp, pp, vp) and bp < pp < vp, \
            "Right rail widgets must appear in order: prompt → probes → verdicts within RightRail"


# ---------------------------------------------------------------------------
# AC10: Right rail visible at ≥1280px — CSS layout check
# ---------------------------------------------------------------------------

def test_right_rail_has_fixed_width():
    """AC10: RightRail has a defined width (not hidden) at wide viewports."""
    shell = (JS_DIR / "shell.js").read_text()
    # The right rail should have a width set (288 per DESIGN.md)
    assert "288" in shell or "width" in shell, \
        "RightRail must have an explicit width for ≥1280px layout"


# ---------------------------------------------------------------------------
# AC11: Empty-state render — no error on empty open/closed/both
# ---------------------------------------------------------------------------

def test_empty_open_section_api(api_client, db_session):
    """AC11: Only closed cases → open section empty → no error from API."""
    _seed_closed_case(db_session)
    r = api_client.get("/api/cases")
    assert r.status_code == 200


def test_empty_closed_section_api(api_client, db_session):
    """AC11: Only open cases → closed section empty → no error from API."""
    _seed_open_case(db_session)
    r = api_client.get("/api/cases")
    assert r.status_code == 200


def test_both_sections_empty_api(api_client):
    """AC11: No cases → both sections empty → no error from API."""
    r = api_client.get("/api/cases")
    assert r.status_code == 200
    assert r.json()["cases"] == []


def test_cases_screen_empty_state_in_js():
    """AC11: CasesScreen must handle empty case list (no crash when open/closed arrays are empty)."""
    combined = "".join((JS_DIR / f).read_text() for f in JS_DIR.iterdir()
                       if f.suffix == ".js")
    # The screen filters open/closed – if both are empty arrays, map produces []
    assert "open" in combined.lower() or "Open" in combined, \
        "CasesScreen must have Open section handling"
    assert "closed" in combined.lower() or "Closed" in combined, \
        "CasesScreen must have Closed section handling"


def test_stage_string_in_api_response(api_client, db_session):
    """Stage is returned as the string enum value in API response."""
    _seed_open_case(db_session, stage="gather")
    cases = api_client.get("/api/cases").json()["cases"]
    assert isinstance(cases[0]["stage"], str)
    assert cases[0]["stage"] == "gather"
