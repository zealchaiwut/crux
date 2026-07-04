"""Tests for issue #178: Extract duplicated horizon sort-key helper in cases.py.

AC coverage:
  AC1 – _horizon_sort_key (or equivalent) is defined at module level in app/routers/cases.py.
  AC2 – Inline expression at cases.py:286 (get_case) is replaced with the helper.
  AC3 – Inline expression at cases.py:636 (design_probe_for_case) is replaced with the helper.
  AC4 – No other changes to cases.py; logic/return values identical.
  AC5 – Helper returns 0, 1, 2, 99 for "short", "mid", "long", and unknown horizons.
"""
import ast
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

CASES_PY = Path(__file__).parent.parent / "app" / "routers" / "cases.py"


# ---------------------------------------------------------------------------
# AC1: helper is defined at module level
# ---------------------------------------------------------------------------

def test_horizon_sort_key_exists_at_module_level():
    """_horizon_sort_key (or equivalent) must be a module-level function."""
    import app.routers.cases as cases_mod
    assert hasattr(cases_mod, "_horizon_sort_key"), (
        "_horizon_sort_key not found at module level in app/routers/cases.py"
    )
    assert callable(cases_mod._horizon_sort_key)


# ---------------------------------------------------------------------------
# AC5: correct return values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("horizon,expected", [
    ("short", 0),
    ("mid",   1),
    ("long",  2),
    ("",      99),
    (None,    99),
    ("unknown_value", 99),
])
def test_horizon_sort_key_values(horizon, expected):
    from app.routers.cases import _horizon_sort_key
    probe = SimpleNamespace(horizon=horizon)
    assert _horizon_sort_key(probe) == expected


# ---------------------------------------------------------------------------
# AC2 / AC3: inline expression not duplicated — appears only once in source
# ---------------------------------------------------------------------------

def test_horizon_tuple_appears_only_once_in_source():
    """The tuple (\"short\",\"mid\",\"long\").index must appear exactly once (inside the helper)."""
    source = CASES_PY.read_text()
    # Count occurrences of the index call on the horizon tuple
    occurrences = source.count('"short", "mid", "long"') + source.count("'short', 'mid', 'long'")
    assert occurrences == 1, (
        f"Expected the horizon tuple to appear exactly once, found {occurrences} times. "
        "Inline duplicates must be replaced with _horizon_sort_key()."
    )


# ---------------------------------------------------------------------------
# AC2: get_case sorts probes via helper (integration-style unit test)
# ---------------------------------------------------------------------------

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


def _make_case_with_probes(db):
    """Create a case with probes in reverse horizon order and return the case."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test horizon sort",
        stage="probe",
    )
    db.add(case)
    db.flush()

    for horizon in ("long", "short", "mid"):
        probe = models.Probe(
            id=str(uuid.uuid4()),
            case_id=case.id,
            type="measurement",
            target_metric="m",
            cost="low",
            time="1w",
            note="",
            horizon=horizon,
            status="designed",
        )
        db.add(probe)
    db.commit()
    return case


def test_get_case_probes_sorted_by_horizon(db_session):
    """Probes in get_case response must be ordered short → mid → long."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET

    case = _make_case_with_probes(db_session)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set("session", create_session_cookie(AUTH_SECRET))
    try:
        resp = client.get(f"/api/cases/{case.id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        horizons = [p["horizon"] for p in resp.json()["probes"]]
        assert horizons == ["short", "mid", "long"], (
            f"Expected ['short', 'mid', 'long'], got {horizons}"
        )
    finally:
        app.dependency_overrides.clear()
