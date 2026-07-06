"""Tests for issue #140: Resolve weigh context validation mismatch.

Decision: Option 1 — whitespace-only `context` is rejected with HTTP 422.
The `not_blank` validator on RerankRequest enforces this before any trim logic.

AC coverage:
  AC1 — Decision is documented in code via schema validation (not_blank validator).
  AC2 — POST /api/cases/{id}/rerank with whitespace-only context returns 422.
  AC3 — N/A (option 2 not chosen).
  AC4 — No other tests broken (verified by running full suite).
  AC5 — Behavior is consistent: whitespace-only rejected same as other optional fields.
"""
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


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
    from app import models

    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is performance dropping?",
        sharpened="Performance dropped 15% over 6 weeks.",
        stage=stage,
    )
    session.add(c)
    session.flush()
    for label, rank in [("A", 1), ("B", 2)]:
        session.add(
            models.Plan(
                id=str(uuid.uuid4()),
                case_id=c.id,
                label=label,
                name=f"Plan {label}",
                mechanism="Some mechanism.",
                prior="0.5",
                current_rank=rank,
            )
        )
    session.commit()
    return c


# ---------------------------------------------------------------------------
# AC1: Decision documented in code — not_blank validator exists and rejects blank
# ---------------------------------------------------------------------------

def test_not_blank_validator_rejects_whitespace_only():
    """AC1: RerankRequest.not_blank raises ValueError for whitespace-only context."""
    from app.routers.cases import RerankRequest
    import pytest as _pytest

    with _pytest.raises(Exception):
        RerankRequest(context="   ")


def test_not_blank_validator_accepts_none():
    """AC1: RerankRequest.not_blank allows None (optional field)."""
    from app.routers.cases import RerankRequest

    req = RerankRequest(context=None)
    assert req.context is None


def test_not_blank_validator_converts_empty_string_to_none():
    """AC1: RerankRequest.not_blank converts '' to None (treat as not provided)."""
    from app.routers.cases import RerankRequest

    req = RerankRequest(context="")
    assert req.context is None


# ---------------------------------------------------------------------------
# AC2: POST /rerank with whitespace-only context returns 422
# ---------------------------------------------------------------------------

def test_rerank_whitespace_only_spaces_returns_422(api_client, db_session):
    """AC2: Three spaces returns 422 (whitespace-only is rejected)."""
    c = _seed_case_with_plans(db_session)
    r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "   "})
    assert r.status_code == 422, (
        f"Whitespace-only context must be rejected with 422; got {r.status_code}: {r.text}"
    )


def test_rerank_whitespace_only_tabs_returns_422(api_client, db_session):
    """AC2: Tab-only context also returns 422."""
    c = _seed_case_with_plans(db_session)
    r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "\t\t"})
    assert r.status_code == 422, (
        f"Tab-only context must be rejected with 422; got {r.status_code}: {r.text}"
    )


def test_rerank_whitespace_only_newlines_returns_422(api_client, db_session):
    """AC2: Newline-only context also returns 422."""
    c = _seed_case_with_plans(db_session)
    r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "\n\n"})
    assert r.status_code == 422, (
        f"Newline-only context must be rejected with 422; got {r.status_code}: {r.text}"
    )


def test_rerank_422_response_has_validation_detail(api_client, db_session):
    """AC2: 422 response body contains validation error detail."""
    c = _seed_case_with_plans(db_session)
    r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "   "})
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body, "422 response must include a 'detail' field"


# ---------------------------------------------------------------------------
# AC5: Consistent behavior — same trim rule applies across optional string fields
# ---------------------------------------------------------------------------

def test_patch_case_rejects_whitespace_only_sharpened(api_client, db_session):
    """AC5: PATCH /cases/{id} with whitespace-only sharpened also returns 422 (consistent)."""
    c = _seed_case_with_plans(db_session, stage="gather")
    r = api_client.patch(f"/api/cases/{c.id}", json={"sharpened": "   "})
    assert r.status_code == 422, (
        f"Whitespace-only sharpened must be rejected the same way as context; got {r.status_code}"
    )


def test_rerank_non_whitespace_context_still_accepted(api_client, db_session):
    """AC5: A real context value (non-whitespace) is still accepted with 200."""
    _MOCK_RERANK = [
        {"label": "A", "rank": 1, "standing": "ruled-in"},
        {"label": "B", "rank": 2, "standing": None},
    ]
    c = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock, return_value=_MOCK_RERANK):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "Some real context."})
    assert r.status_code == 200, (
        f"Valid context must still return 200; got {r.status_code}: {r.text}"
    )
