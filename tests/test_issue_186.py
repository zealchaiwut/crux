"""Tests for issue #186: Consolidate duplicate rationale field in VerifySourceRequest.

Design decision: Remove the drive-by `rationale` field from VerifySourceRequest.
The verify endpoint exposes a single text field — `support_rationale` — and mirrors
it to source.rationale so the response/UI display remains consistent.

AC1 – VerifySourceRequest does not expose a `rationale` field; extra keys in
      the request body are ignored.
AC2 – Calling POST /api/sources/{id}/verify with support_rationale sets both
      source.support_rationale and source.rationale in the response.
AC3 – Passing a `rationale` key to the verify endpoint does not update
      source.rationale (the field is no longer part of the model).
AC4 – support_status is still required; support_rationale remains optional.
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_engine():
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
    engine = _make_engine()
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


def _seed_source(session):
    from app import models

    case_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    sid = str(uuid.uuid4())

    case = models.Case(
        id=case_id,
        raw_problem="Test problem",
        sharpened="Sharpened",
        stage="gather",
    )
    plan = models.Plan(
        id=plan_id,
        case_id=case_id,
        label="A",
        name="Plan A",
        mechanism="mech",
        prior="0.50",
    )
    src = models.Source(
        id=sid,
        plan_id=plan_id,
        kind="article",
        title="Source",
        url="https://example.com/s",
        claim="The claim",
        citation="Cite",
    )
    session.add_all([case, plan, src])
    session.commit()
    return sid


# ---------------------------------------------------------------------------
# AC1 — VerifySourceRequest model has no `rationale` field
# ---------------------------------------------------------------------------

class TestVerifySourceRequestModel:
    def test_model_has_no_rationale_field(self):
        """AC1: VerifySourceRequest must not declare a `rationale` field."""
        from app.routers.sources import VerifySourceRequest
        assert "rationale" not in VerifySourceRequest.model_fields, (
            "VerifySourceRequest must not expose a `rationale` field; "
            "use support_rationale as the single text field."
        )

    def test_model_has_support_rationale_field(self):
        """AC1: VerifySourceRequest retains support_rationale as the single text field."""
        from app.routers.sources import VerifySourceRequest
        assert "support_rationale" in VerifySourceRequest.model_fields


# ---------------------------------------------------------------------------
# AC2 — support_rationale is mirrored to source.rationale in the response
# ---------------------------------------------------------------------------

class TestVerifyMirrorsRationale:
    def test_support_rationale_appears_in_rationale_response_field(
        self, api_client, db_session
    ):
        """AC2: verify with support_rationale sets source.rationale in response."""
        sid = _seed_source(db_session)
        resp = api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "supports", "support_rationale": "Clear evidence."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rationale"] == "Clear evidence."
        assert data["support_rationale"] == "Clear evidence."

    def test_null_support_rationale_sets_null_rationale(self, api_client, db_session):
        """AC2: verify with no support_rationale leaves source.rationale as None."""
        sid = _seed_source(db_session)
        resp = api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "unverified"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rationale"] is None
        assert data["support_rationale"] is None


# ---------------------------------------------------------------------------
# AC3 — Passing legacy `rationale` key to verify does not set source.rationale
# ---------------------------------------------------------------------------

class TestLegacyRationaleIgnored:
    def test_rationale_key_in_body_is_ignored(self, api_client, db_session):
        """AC3: extra `rationale` key in verify body is ignored; source.rationale stays None."""
        sid = _seed_source(db_session)
        resp = api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "contradicts", "rationale": "should be ignored"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # rationale must NOT be set from the extra field
        assert data["rationale"] is None


# ---------------------------------------------------------------------------
# AC4 — support_status required; support_rationale optional
# ---------------------------------------------------------------------------

class TestVerifyValidation:
    def test_missing_support_status_returns_422(self, api_client, db_session):
        """AC4: support_status is required."""
        sid = _seed_source(db_session)
        resp = api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_rationale": "some text"},
        )
        assert resp.status_code == 422

    def test_support_rationale_is_optional(self, api_client, db_session):
        """AC4: verify without support_rationale is valid."""
        sid = _seed_source(db_session)
        resp = api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "partial"},
        )
        assert resp.status_code == 200
