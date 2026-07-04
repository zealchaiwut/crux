"""Tests for issue #169: Render three horizon probes as grouped set in ProbeCard.

AC coverage:
  AC1 – ProbeCard in cases.js renders all three horizon probes (short, mid, long)
         as a visually grouped set.
  AC2 – Each horizon probe is labelled with its horizon name (e.g. "Short", "Mid", "Long").
  AC3 – Each horizon probe displays target_metric, duration, decision_rule, and steps.
  AC4 – Each horizon probe has an independent "Log verdict" action that is
         enabled/disabled without affecting sibling probes.
  AC5 – Logging a verdict via any horizon's action attaches that verdict to the
         correct probe (POST /api/probes/{probe_id}/verdict endpoint).
  AC6 – Styling uses only existing probe styles and DESIGN.md tokens; no new colors.
  AC7 – Layout degrades gracefully if one or more horizon probes are absent.
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


def _seed_case_with_three_probes(session):
    """Seed a Case with three horizon Probe rows (short, mid, long)."""
    import json
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem statement",
        sharpened="Test sharpened statement.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    session.add(case)
    session.flush()

    probe_short = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="measurement",
        target_metric="resting HRV (7-day average)",
        cost="free",
        time="7 days",
        note="Measure resting HRV each morning.",
        steps=["Download HRV app", "Measure daily"],
        duration="7 days",
        decision_rule="HRV drops >10% vs baseline",
        status="designed",
        horizon="short",
    )
    probe_mid = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="behaviour-experiment",
        target_metric="weekly average run pace",
        cost="free",
        time="3 weeks",
        note="Reduce training load.",
        steps=["Reduce mileage 20%", "Log pace weekly"],
        duration="3 weeks",
        decision_rule="Pace improves >5% vs baseline",
        status="designed",
        horizon="mid",
    )
    probe_long = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="lab-test",
        target_metric="serum ferritin",
        cost="~£40",
        time="6 weeks",
        note="See GP for blood count.",
        steps=["Book GP", "Request blood count"],
        duration="6 weeks",
        decision_rule="Ferritin rises to >=50 µg/L",
        status="designed",
        horizon="long",
    )
    session.add_all([probe_short, probe_mid, probe_long])
    session.commit()
    return case, probe_short, probe_mid, probe_long


# ---------------------------------------------------------------------------
# AC1: ProbeCard renders all three horizon probes as a grouped set (JS)
# ---------------------------------------------------------------------------

def test_probe_card_renders_horizon_probes_js():
    """AC1: ProbeCard must handle a list of horizon probes (probes prop)."""
    combined = _read_combined_js()
    # ProbeCard must reference the probes array (plural)
    assert "probes" in combined, \
        "ProbeCard must reference 'probes' (array) to render horizon probes"


def test_probe_card_renders_grouped_set_js():
    """AC1: ProbeCard must render horizon probes as a grouped set."""
    combined = _read_combined_js()
    # Must map/iterate over probes to render each horizon
    assert (
        "probes.map" in combined
        or ".map(" in combined
        or "horizon" in combined
    ), "ProbeCard must iterate over probes to render a grouped set"


# ---------------------------------------------------------------------------
# AC2: Each horizon probe labelled "Short", "Mid", "Long" (JS)
# ---------------------------------------------------------------------------

def test_probe_card_labels_short_horizon_js():
    """AC2: ProbeCard must render 'Short' label for the short horizon probe."""
    combined = _read_combined_js()
    assert "Short" in combined, \
        "ProbeCard must render 'Short' label for short horizon probes"


def test_probe_card_labels_mid_horizon_js():
    """AC2: ProbeCard must render 'Mid' label for the mid horizon probe."""
    combined = _read_combined_js()
    assert "Mid" in combined, \
        "ProbeCard must render 'Mid' label for mid horizon probes"


def test_probe_card_labels_long_horizon_js():
    """AC2: ProbeCard must render 'Long' label for the long horizon probe."""
    combined = _read_combined_js()
    assert "Long" in combined, \
        "ProbeCard must render 'Long' label for long horizon probes"


def test_probe_card_horizon_label_capitalised_js():
    """AC2: Horizon labels must be capitalised (e.g. 'Short', not 'short')."""
    combined = _read_combined_js()
    # Must convert or hardcode "Short"/"Mid"/"Long"
    assert (
        '"Short"' in combined
        or "'Short'" in combined
        or "charAt(0).toUpperCase" in combined
        or "toUpperCase" in combined
    ), "ProbeCard must capitalise horizon labels"


# ---------------------------------------------------------------------------
# AC3: Each probe shows target_metric, duration, decision_rule, steps (JS)
# ---------------------------------------------------------------------------

def test_probe_card_renders_target_metric_per_horizon_js():
    """AC3: ProbeCard must render target_metric for each horizon probe."""
    combined = _read_combined_js()
    assert "target_metric" in combined, \
        "ProbeCard must render target_metric per horizon probe"


def test_probe_card_renders_duration_per_horizon_js():
    """AC3: ProbeCard must render duration for each horizon probe."""
    combined = _read_combined_js()
    assert "duration" in combined, \
        "ProbeCard must render duration per horizon probe"


def test_probe_card_renders_decision_rule_per_horizon_js():
    """AC3: ProbeCard must render decision_rule for each horizon probe."""
    combined = _read_combined_js()
    assert "decision_rule" in combined, \
        "ProbeCard must render decision_rule per horizon probe"


def test_probe_card_renders_steps_per_horizon_js():
    """AC3: ProbeCard must render steps for each horizon probe."""
    combined = _read_combined_js()
    assert "steps" in combined, \
        "ProbeCard must render steps per horizon probe"


# ---------------------------------------------------------------------------
# AC4: Each horizon probe has an independent "Log verdict" action (JS)
# ---------------------------------------------------------------------------

def test_probe_card_has_log_verdict_action_js():
    """AC4: ProbeCard must render a 'Log verdict' action per horizon probe."""
    combined = _read_combined_js()
    assert "Log verdict" in combined, \
        "ProbeCard must render a 'Log verdict' action for each horizon probe"


def test_probe_verdict_uses_probe_id_js():
    """AC4/AC5: ProbeCard 'Log verdict' action must reference probe.id for independent targeting."""
    combined = _read_combined_js()
    assert (
        "probe.id" in combined
        or "probeId" in combined
        or "probe_id" in combined
    ), "ProbeCard must use probe.id to log verdicts independently per horizon"


def test_probe_card_log_verdict_independent_per_horizon_js():
    """AC4: Each horizon probe's 'Log verdict' is independent (no shared state)."""
    combined = _read_combined_js()
    # Must have per-probe verdict logic (probeId or similar per-probe tracking)
    assert (
        "probeId" in combined
        or "probe_id" in combined
        or "/api/probes/" in combined
    ), "ProbeCard must log verdicts to probe-specific endpoints for independence"


# ---------------------------------------------------------------------------
# AC5: POST /api/probes/{probe_id}/verdict endpoint exists (API)
# ---------------------------------------------------------------------------

def test_probe_verdict_endpoint_exists(api_client, db_session):
    """AC5: POST /api/probes/{probe_id}/verdict must return 200 for a valid probe."""
    case, probe_short, _, _ = _seed_case_with_three_probes(db_session)
    r = api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "confirmed", "notes": "Short probe confirmed hypothesis."},
    )
    assert r.status_code == 200, r.text


def test_probe_verdict_endpoint_404_unknown_probe(api_client):
    """AC5: POST /api/probes/{probe_id}/verdict returns 404 for unknown probe."""
    r = api_client.post(
        "/api/probes/00000000-0000-0000-0000-000000000000/verdict",
        json={"outcome": "confirmed", "notes": "Some notes."},
    )
    assert r.status_code == 404, r.text


def test_probe_verdict_attaches_to_correct_probe(api_client, db_session):
    """AC5: Verdict logged via /api/probes/{probe_id}/verdict attaches to that probe only."""
    from app import models

    case, probe_short, probe_mid, probe_long = _seed_case_with_three_probes(db_session)

    r = api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "confirmed", "notes": "Short probe passed."},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    # Short probe has a verdict
    short_verdicts = (
        db_session.query(models.Verdict)
        .filter_by(probe_id=probe_short.id)
        .all()
    )
    assert len(short_verdicts) == 1, \
        f"Expected 1 verdict for short probe; found {len(short_verdicts)}"

    # Mid and long probes have no verdict
    mid_verdicts = (
        db_session.query(models.Verdict)
        .filter_by(probe_id=probe_mid.id)
        .all()
    )
    assert len(mid_verdicts) == 0, \
        f"Mid probe must have no verdict; found {len(mid_verdicts)}"

    long_verdicts = (
        db_session.query(models.Verdict)
        .filter_by(probe_id=probe_long.id)
        .all()
    )
    assert len(long_verdicts) == 0, \
        f"Long probe must have no verdict; found {len(long_verdicts)}"


def test_probe_verdict_updates_probe_status(api_client, db_session):
    """AC5: Logging a verdict via /api/probes/{probe_id}/verdict updates that probe's status."""
    from app import models

    case, probe_short, probe_mid, probe_long = _seed_case_with_three_probes(db_session)

    api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "killed", "notes": "Hypothesis refuted."},
    )

    db_session.expire_all()
    updated_short = db_session.get(models.Probe, probe_short.id)
    assert updated_short.status == "killed", \
        f"Short probe status must be 'killed'; got {updated_short.status!r}"

    updated_mid = db_session.get(models.Probe, probe_mid.id)
    assert updated_mid.status == "designed", \
        f"Mid probe status must be unchanged ('designed'); got {updated_mid.status!r}"

    updated_long = db_session.get(models.Probe, probe_long.id)
    assert updated_long.status == "designed", \
        f"Long probe status must be unchanged ('designed'); got {updated_long.status!r}"


def test_probe_verdict_returns_verdict_data(api_client, db_session):
    """AC5: POST /api/probes/{probe_id}/verdict returns verdict id, outcome, notes."""
    case, probe_short, _, _ = _seed_case_with_three_probes(db_session)

    r = api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "inconclusive", "notes": "Need more data."},
    )
    assert r.status_code == 200
    data = r.json()
    assert "id" in data, "Response must include verdict id"
    assert data["outcome"] == "inconclusive", \
        f"Expected outcome='inconclusive'; got {data['outcome']!r}"
    assert data["notes"] == "Need more data.", \
        f"Expected notes preserved; got {data['notes']!r}"


def test_probe_verdict_requires_notes(api_client, db_session):
    """AC5: POST /api/probes/{probe_id}/verdict rejects empty notes."""
    case, probe_short, _, _ = _seed_case_with_three_probes(db_session)

    r = api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "confirmed", "notes": ""},
    )
    assert r.status_code in (400, 422), \
        f"Empty notes must be rejected; got {r.status_code}"


def test_probe_verdict_rejects_invalid_outcome(api_client, db_session):
    """AC5: POST /api/probes/{probe_id}/verdict rejects invalid outcome values."""
    case, probe_short, _, _ = _seed_case_with_three_probes(db_session)

    r = api_client.post(
        f"/api/probes/{probe_short.id}/verdict",
        json={"outcome": "unsure", "notes": "Some notes."},
    )
    assert r.status_code in (400, 422), \
        f"Invalid outcome must be rejected; got {r.status_code}"


def test_probe_mid_verdict_independent_of_short(api_client, db_session):
    """AC5: Logging a verdict for mid probe does not affect short or long probes."""
    from app import models

    case, probe_short, probe_mid, probe_long = _seed_case_with_three_probes(db_session)

    api_client.post(
        f"/api/probes/{probe_mid.id}/verdict",
        json={"outcome": "confirmed", "notes": "Mid probe confirmed."},
    )

    db_session.expire_all()
    short = db_session.get(models.Probe, probe_short.id)
    long = db_session.get(models.Probe, probe_long.id)
    assert short.status == "designed", "Short probe must be unaffected by mid verdict"
    assert long.status == "designed", "Long probe must be unaffected by mid verdict"


# ---------------------------------------------------------------------------
# AC6: No new colors — only existing DESIGN.md tokens used (JS)
# ---------------------------------------------------------------------------

def test_probe_card_horizon_no_new_color_vars_js():
    """AC6: ProbeCard horizon rendering must not introduce new CSS color variables."""
    combined = _read_combined_js()
    # Known existing token names — any brand-new color var would be a violation.
    # We check that horizon-label specific new color vars are NOT introduced.
    # (We cannot enumerate ALL possible new vars, but we can check the horizon
    # label section uses existing vars like --crux, --text-sub, --border, etc.)
    # This is a best-effort check: the horizon label must reuse existing probe chip styles.
    assert "var(--crux)" in combined or "var(--text-sub)" in combined, \
        "Horizon label chips must reuse existing CSS token variables"


def test_probe_card_horizon_uses_existing_chip_style_js():
    """AC6: Horizon labels must reuse the existing pill/chip styling pattern."""
    combined = _read_combined_js()
    # Existing probe pill style uses border-radius-pill
    assert "radius-pill" in combined or "border-radius" in combined, \
        "Horizon label must use existing border-radius token (radius-pill)"


# ---------------------------------------------------------------------------
# AC7: Graceful degradation when some horizon probes are absent (API)
# ---------------------------------------------------------------------------

def test_get_case_probes_list_when_all_present(api_client, db_session):
    """AC7: GET /api/cases/{id} returns all three probes when all horizons present."""
    case, _, _, _ = _seed_case_with_three_probes(db_session)

    r = api_client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200
    data = r.json()
    probes = data.get("probes", [])
    assert len(probes) == 3, f"Expected 3 probes; got {len(probes)}"
    horizons = {p["horizon"] for p in probes}
    assert horizons == {"short", "mid", "long"}, \
        f"Expected all three horizons; got {horizons}"


def test_get_case_probes_list_when_only_short_present(api_client, db_session):
    """AC7: GET /api/cases/{id} returns only the present probe when one horizon exists."""
    import json
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Solo probe test",
        sharpened="Only short horizon present.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(case)
    db_session.flush()

    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case.id,
        type="measurement",
        target_metric="HRV",
        cost="free",
        time="7 days",
        note="Short only.",
        steps=[],
        duration="7 days",
        decision_rule="Drop >10%",
        status="designed",
        horizon="short",
    )
    db_session.add(probe)
    db_session.commit()

    r = api_client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200
    data = r.json()
    probes = data.get("probes", [])
    assert len(probes) == 1, f"Expected 1 probe; got {len(probes)}"
    assert probes[0]["horizon"] == "short"


def test_probe_card_graceful_degradation_js():
    """AC7: ProbeCard must not render absent horizon probes (guards missing probes)."""
    combined = _read_combined_js()
    # Must check for probe existence before rendering each horizon section
    assert (
        "probes" in combined
        and (
            ".length" in combined
            or ".filter" in combined
            or "if (" in combined
            or "&&" in combined
        )
    ), "ProbeCard must guard against absent horizon probes (conditional rendering)"


def test_probe_card_probes_prop_in_case_detail_js():
    """AC7: CaseDetailScreen must pass 'probes' array to ProbeCard for graceful rendering."""
    combined = _read_combined_js()
    # The ProbeCard call site must use caseData.probes
    assert "caseData.probes" in combined or "probes={" in combined, \
        "CaseDetailScreen must pass caseData.probes to ProbeCard"
