"""Tests for issue #72: Verify outcome chip verdict values match API response.

AC coverage:
  AC1 – /api/cases returns exact verdict strings for open cases:
          "awaiting" (no probe or probe not running) and "progress" (probe running, no verdict).
  AC2 – OUTCOME_CHIP_DEFS "Open" entry in cases.js maps to those exact strings.
  AC3 – No mismatch: every API open-verdict string is covered by the "Open" chip mapping.
  AC4 – Open cases are visible via /api/cases when filtering by their verdict value.
  AC5 – Non-open verdicts (confirmed, killed, inconclusive) appear under their respective
         chip values and not under the "Open" values.
"""
import os
import pathlib
import re
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cases_js() -> str:
    return (STATIC_JS / "cases.js").read_text()


def _open_chip_values() -> list[str]:
    """Extract the values array from OUTCOME_CHIP_DEFS "Open" entry in cases.js."""
    src = _cases_js()
    # Find OUTCOME_CHIP_DEFS block
    match = re.search(r'OUTCOME_CHIP_DEFS\s*=\s*\[(.+?)\];', src, re.DOTALL)
    assert match, "OUTCOME_CHIP_DEFS must be defined in cases.js"
    block = match.group(1)
    # Find the "Open" entry
    open_match = re.search(
        r'\{\s*label\s*:\s*["\']Open["\'].*?values\s*:\s*\[([^\]]+)\]',
        block,
        re.DOTALL,
    )
    assert open_match, 'OUTCOME_CHIP_DEFS must contain an "Open" entry with a values array'
    raw_values = open_match.group(1)
    return [v.strip().strip('"\'') for v in raw_values.split(",") if v.strip()]


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
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _add_case(db_session, **kwargs):
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem=kwargs.get("raw_problem", "test problem"),
        sharpened=kwargs.get("sharpened", "sharpened problem"),
        stage=kwargs.get("stage", "sharpened"),
    )
    db_session.add(c)
    db_session.flush()
    return c


def _add_probe(db_session, case_id, status="running"):
    from app import models

    p = models.Probe(
        id=str(uuid.uuid4()),
        case_id=case_id,
        type="measurement",
        status=status,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _add_verdict(db_session, probe_id, outcome):
    from app import models

    v = models.Verdict(
        id=str(uuid.uuid4()),
        probe_id=probe_id,
        outcome=outcome,
    )
    db_session.add(v)
    db_session.flush()
    return v


# ---------------------------------------------------------------------------
# AC1 – API returns "awaiting" for cases with no probe
# ---------------------------------------------------------------------------

def test_api_returns_awaiting_for_case_without_probe(api_client, db_session):
    """AC1: /api/cases returns verdict="awaiting" when a case has no probe."""
    _add_case(db_session, sharpened="No probe case")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "awaiting", (
        f"Expected verdict='awaiting' for case with no probe, got {cases[0]['verdict']!r}"
    )


def test_api_returns_awaiting_for_case_with_designed_probe(api_client, db_session):
    """AC1: /api/cases returns verdict="awaiting" when probe status is not 'running'."""
    c = _add_case(db_session, sharpened="Designed probe case")
    _add_probe(db_session, c.id, status="designed")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "awaiting", (
        f"Expected verdict='awaiting' for designed probe, got {cases[0]['verdict']!r}"
    )


def test_api_returns_progress_for_running_probe_without_verdict(api_client, db_session):
    """AC1: /api/cases returns verdict="progress" when probe is running but has no logged verdict."""
    c = _add_case(db_session, sharpened="Running probe case")
    _add_probe(db_session, c.id, status="running")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == "progress", (
        f"Expected verdict='progress' for running probe, got {cases[0]['verdict']!r}"
    )


# ---------------------------------------------------------------------------
# AC2 – OUTCOME_CHIP_DEFS "Open" maps to the exact API strings
# ---------------------------------------------------------------------------

def test_open_chip_contains_awaiting():
    """AC2: OUTCOME_CHIP_DEFS "Open" values array must include "awaiting"."""
    values = _open_chip_values()
    assert "awaiting" in values, (
        f'"awaiting" must be in OUTCOME_CHIP_DEFS "Open" values; got {values}'
    )


def test_open_chip_contains_progress():
    """AC2: OUTCOME_CHIP_DEFS "Open" values array must include "progress"."""
    values = _open_chip_values()
    assert "progress" in values, (
        f'"progress" must be in OUTCOME_CHIP_DEFS "Open" values; got {values}'
    )


# ---------------------------------------------------------------------------
# AC3 – No mismatch: API open verdicts are fully covered by the chip mapping
# ---------------------------------------------------------------------------

def test_open_chip_covers_all_api_open_verdicts(api_client, db_session):
    """AC3: Every verdict string the API returns for open cases is in the Open chip mapping."""
    # Create one case per open-verdict scenario
    _add_case(db_session, sharpened="No probe")
    c2 = _add_case(db_session, sharpened="Running probe")
    _add_probe(db_session, c2.id, status="running")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]

    api_open_verdicts = {c["verdict"] for c in cases}
    chip_values = set(_open_chip_values())

    uncovered = api_open_verdicts - chip_values
    assert not uncovered, (
        f"API returns open verdicts {uncovered!r} that are NOT in OUTCOME_CHIP_DEFS 'Open' values {chip_values!r}. "
        "Silent filtering bug: these cases would not appear under the 'Open' chip."
    )


# ---------------------------------------------------------------------------
# AC4 – Open cases appear when filtered by their verdict values
# ---------------------------------------------------------------------------

def test_open_cases_visible_under_open_filter(api_client, db_session):
    """AC4: Open cases with verdict="awaiting" or "progress" are returned by /api/cases."""
    _add_case(db_session, sharpened="Awaiting case")
    c2 = _add_case(db_session, sharpened="Progress case")
    _add_probe(db_session, c2.id, status="running")
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]

    open_verdicts = _open_chip_values()
    open_cases = [c for c in cases if c["verdict"] in open_verdicts]
    assert len(open_cases) == 2, (
        f"Expected 2 open cases visible via 'Open' chip values {open_verdicts!r}, "
        f"got {len(open_cases)}: {[c['verdict'] for c in cases]}"
    )


# ---------------------------------------------------------------------------
# AC5 – Non-open verdicts appear under their respective chips (no regression)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("outcome", ["confirmed", "killed", "inconclusive"])
def test_closed_verdicts_not_in_open_chip(api_client, db_session, outcome):
    """AC5: Cases with verdict={outcome} must NOT appear under the "Open" chip values."""
    c = _add_case(db_session, sharpened=f"{outcome} case")
    p = _add_probe(db_session, c.id, status="running")
    _add_verdict(db_session, p.id, outcome)
    db_session.commit()

    resp = api_client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["verdict"] == outcome, (
        f"Expected verdict={outcome!r}, got {cases[0]['verdict']!r}"
    )

    open_chip_values = set(_open_chip_values())
    assert cases[0]["verdict"] not in open_chip_values, (
        f"Verdict {outcome!r} must not appear under the 'Open' chip (open values: {open_chip_values!r})"
    )


@pytest.mark.parametrize("outcome", ["confirmed", "killed", "inconclusive"])
def test_closed_chip_label_covers_its_verdict(outcome):
    """AC5: OUTCOME_CHIP_DEFS must include a chip whose values cover the {outcome} verdict."""
    src = _cases_js()
    match = re.search(r'OUTCOME_CHIP_DEFS\s*=\s*\[(.+?)\];', src, re.DOTALL)
    assert match, "OUTCOME_CHIP_DEFS must be defined in cases.js"
    block = match.group(1)
    assert f'"{outcome}"' in block or f"'{outcome}'" in block, (
        f'OUTCOME_CHIP_DEFS must include a chip covering the "{outcome}" verdict'
    )
