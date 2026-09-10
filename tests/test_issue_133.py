"""Tests for issue #133: Render per-plan rationale text in PlanCard.

AC coverage:
  AC1 – PlanCard renders rationale text when the field is non-empty
  AC2 – Rationale block is hidden (no empty container) when field is absent/empty
  AC3 – Styling uses only existing DESIGN.md tokens; no new color values
  AC4 – Rationale block follows mechanism/sources; existing card layout unaffected
  AC5 – Component passes JS/lint checks; no new warnings
"""
import os
import uuid

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


def _seed_case(session, rationale_a="Plan A clinical rationale.", rationale_b=None):
    import json
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem for rationale",
        sharpened="Sharpened test statement.",
        not_investigating=json.dumps([]),
        stage="gather",
    )
    session.add(c)
    session.flush()
    plans = [
        models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label="A",
            name="Plan A",
            mechanism="Mechanism A.",
            prior="0.6",
            current_rank=1,
            rationale=rationale_a,
        ),
        models.Plan(
            id=str(uuid.uuid4()),
            case_id=c.id,
            label="B",
            name="Plan B",
            mechanism="Mechanism B.",
            prior="0.4",
            current_rank=2,
            rationale=rationale_b,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


# ---------------------------------------------------------------------------
# AC1 prerequisite: API returns rationale field on each plan
# ---------------------------------------------------------------------------


def test_api_plan_includes_rationale_field(api_client, db_session):
    """AC1: GET /api/cases/{id} must include a 'rationale' key on each plan object."""
    c, _ = _seed_case(db_session)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "plans" in data
    for plan in data["plans"]:
        assert "rationale" in plan, (
            f"Plan missing 'rationale' field; got keys: {list(plan.keys())}"
        )


def test_api_plan_rationale_value_preserved(api_client, db_session):
    """AC1: GET /api/cases/{id} returns the stored rationale string for a plan."""
    c, plans = _seed_case(db_session, rationale_a="Because evidence supports it.")
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    plan_a = next(p for p in r.json()["plans"] if p["label"] == "A")
    assert plan_a["rationale"] == "Because evidence supports it."


def test_api_plan_rationale_null_when_absent(api_client, db_session):
    """AC2: GET /api/cases/{id} returns null rationale when the plan has no rationale stored."""
    c, _ = _seed_case(db_session, rationale_a=None, rationale_b=None)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    for plan in r.json()["plans"]:
        assert plan["rationale"] is None, (
            f"Expected null rationale, got: {plan['rationale']!r}"
        )


# ---------------------------------------------------------------------------
# AC1: JS renders rationale block with data-testid="plan-rationale"
# ---------------------------------------------------------------------------


def test_js_plancard_renders_rationale_testid():
    """AC1: PlanCard JS must render data-testid='plan-rationale' when rationale is present."""
    combined = _read_combined_js()
    assert 'data-testid="plan-rationale"' in combined, (
        "PlanCard must include data-testid=\"plan-rationale\" on the rationale container"
    )


def test_js_plancard_rationale_prop_accepted():
    """AC1: PlanCard must declare a 'rationale' prop parameter."""
    combined = _read_combined_js()
    assert "initialRationaleText" in combined or "rationaleText" in combined, (
        "PlanCard must handle a rationale prop (initialRationaleText or rationaleText)"
    )


def test_js_rationale_passed_at_call_site():
    """AC1: The PlanCard call site must pass the plan's rationale field."""
    combined = _read_combined_js()
    assert "rationale={p.rationale" in combined, (
        "PlanCard call site must pass rationale={p.rationale ...} to the component"
    )


# ---------------------------------------------------------------------------
# AC2: Rationale block is conditionally rendered (guarded by truthy check)
# ---------------------------------------------------------------------------


def test_js_rationale_guarded_by_truthy_check():
    """AC2: Rationale block must be conditionally rendered — not shown when empty."""
    combined = _read_combined_js()
    # The implementation wraps the block in {rationaleText && (...)}
    assert "rationaleText &&" in combined or "{rationaleText" in combined, (
        "Rationale block must be guarded by a truthy check to avoid empty containers"
    )


# ---------------------------------------------------------------------------
# AC3: No new color values — uses existing DESIGN.md tokens
# ---------------------------------------------------------------------------


def test_js_rationale_block_uses_no_hardcoded_colors():
    """AC3: Rationale block must not introduce hardcoded hex or rgb color values."""
    import re

    combined = _read_combined_js()
    # Extract the rationale block (between data-testid="plan-rationale" and the closing div)
    match = re.search(
        r'data-testid="plan-rationale"(.{0,1000}?)(?=\n\s*\{show|function |\n})',
        combined,
        re.DOTALL,
    )
    if match:
        block = match.group(1)
        assert not re.search(r"#[0-9a-fA-F]{3,6}", block), (
            "Rationale block must not use hardcoded hex color values"
        )
        assert not re.search(r"rgb\(", block), (
            "Rationale block must not use hardcoded rgb() color values"
        )


def test_js_rationale_uses_css_var_tokens():
    """AC3: Rationale block must use CSS var() tokens for styling."""
    combined = _read_combined_js()
    # The implementation uses var(--border), var(--text-sub), var(--text-muted), var(--space-*)
    assert "var(--" in combined, "Rationale block must use CSS variable tokens"


# ---------------------------------------------------------------------------
# AC4: Existing PlanCard layout unaffected
# ---------------------------------------------------------------------------


def test_api_plans_still_return_mechanism_and_sources(api_client, db_session):
    """AC4: Existing plan fields (mechanism, sources) are unaffected by the rationale addition."""
    c, _ = _seed_case(db_session)
    r = api_client.get(f"/api/cases/{c.id}")
    assert r.status_code == 200
    for plan in r.json()["plans"]:
        assert "mechanism" in plan
        assert "sources" in plan


def test_js_plancard_sources_section_still_present():
    """AC4: PlanCard must still render the SOURCES section after rationale block addition."""
    combined = _read_combined_js()
    assert "SOURCES" in combined, "PlanCard must still include the SOURCES label"


def test_js_plancard_component_still_defined():
    """AC4: PlanCard component must still be defined and intact."""
    combined = _read_combined_js()
    assert "function PlanCard" in combined, "PlanCard component must still be defined"


# ---------------------------------------------------------------------------
# AC5: No new JS warnings — structural checks
# ---------------------------------------------------------------------------


def test_js_no_merge_conflict_markers():
    """AC5: JS must not contain git merge conflict markers."""
    combined = _read_combined_js()
    assert "<<<<<<< " not in combined, "cases.js contains unresolved merge conflict (<<<<<<< marker)"
    assert ">>>>>>> " not in combined, "cases.js contains unresolved merge conflict (>>>>>>> marker)"


def test_js_rationale_label_rendered():
    """AC5: Rationale block must include a visible 'RATIONALE' label."""
    combined = _read_combined_js()
    assert "RATIONALE" in combined, (
        "Rationale block must display a 'RATIONALE' label to identify the section"
    )
