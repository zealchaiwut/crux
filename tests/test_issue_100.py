"""Tests for issue #100: Colour SourceChip by support_status with Verify actions.

AC coverage:
  AC1  – SourceChip accepts support_status: supports | partial | contradicts | unverified
         (mapped to/from DB values: supports | contradicts | neutral | inconclusive | null)
  AC2  – Source API endpoints return support_status + rationale
  AC3  – No new colour tokens introduced (colour logic only in frontend; backend just stores status)
  AC4  – Expanding SourceChip reveals rationale from the data layer
         (GET /api/sources returns rationale field)
  AC5  – POST /api/sources/{id}/run-verify triggers verification and returns updated source
  AC6  – POST /api/plans/{id}/run-verify-all triggers verification for every source on a plan
  AC7  – After run-verify, support_status and rationale are set in the DB
  AC8  – PATCH /api/sources/{id}/status-override persists manual override
  AC9  – manually_overridden=True survives re-fetch (AC9: override persists)
  AC10 – Sources without support_status return manually_overridden=False, support_status=null
  AC11 – GET /api/sources includes support_status, rationale, manually_overridden
  AC12 – Case detail endpoint includes support_status, rationale, manually_overridden in sources
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


def _seed_case_with_plan_and_sources(session, n_sources=2):
    """Return (case_id, plan_id, [source_id, ...])."""
    from app import models

    case_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    case = models.Case(
        id=case_id,
        raw_problem="Test problem",
        sharpened="Sharpened test problem",
        stage="gather",
    )
    plan = models.Plan(
        id=plan_id,
        case_id=case_id,
        label="A",
        name="Plan A",
        mechanism="mechanism",
        prior="0.50",
    )
    session.add(case)
    session.add(plan)

    source_ids = []
    for i in range(n_sources):
        sid = str(uuid.uuid4())
        src = models.Source(
            id=sid,
            plan_id=plan_id,
            kind="article",
            title=f"Source {i + 1}",
            url=f"https://example.com/source-{i + 1}",
            claim=f"Claim for source {i + 1}",
            citation=f"Citation {i + 1}",
        )
        session.add(src)
        source_ids.append(sid)

    session.commit()
    return case_id, plan_id, source_ids


# ---------------------------------------------------------------------------
# AC11 — GET /api/sources includes support_status, rationale, manually_overridden
# ---------------------------------------------------------------------------

class TestGetSourcesIncludesVerificationFields:
    def test_unverified_source_returns_null_support_status(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        resp = api_client.get(f"/api/sources?plan_id={plan_id}")
        assert resp.status_code == 200
        data = resp.json()
        src = next(s for s in data["sources"] if s["id"] == source_ids[0])
        assert src["support_status"] == "unverified"
        assert src["rationale"] is None
        assert src["manually_overridden"] is False

    def test_verified_source_returns_status_and_rationale(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "supports", "rationale": "Strongly supports the claim."},
        )
        resp = api_client.get(f"/api/sources?plan_id={plan_id}")
        assert resp.status_code == 200
        src = next(s for s in resp.json()["sources"] if s["id"] == sid)
        assert src["support_status"] == "supports"
        assert src["rationale"] == "Strongly supports the claim."
        assert src["manually_overridden"] is False


# ---------------------------------------------------------------------------
# AC12 — Case detail endpoint includes support_status, rationale, manually_overridden
# ---------------------------------------------------------------------------

class TestCaseDetailIncludesVerificationFields:
    def test_case_detail_sources_include_verification_fields(self, api_client, db_session):
        case_id, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        api_client.post(
            f"/api/sources/{sid}/verify",
            json={"support_status": "contradicts", "rationale": "Does not align."},
        )
        resp = api_client.get(f"/api/cases/{case_id}")
        assert resp.status_code == 200
        plans = resp.json()["plans"]
        sources = next(p for p in plans if p["id"] == plan_id)["sources"]
        verified_src = next(s for s in sources if s["id"] == sid)
        assert verified_src["support_status"] == "contradicts"
        assert verified_src["rationale"] == "Does not align."
        assert verified_src["manually_overridden"] is False

    def test_case_detail_unverified_source_shows_null_status(self, api_client, db_session):
        case_id, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        resp = api_client.get(f"/api/cases/{case_id}")
        assert resp.status_code == 200
        plans = resp.json()["plans"]
        sources = next(p for p in plans if p["id"] == plan_id)["sources"]
        for src in sources:
            assert src["support_status"] == "unverified"
            assert src["rationale"] is None
            assert src["manually_overridden"] is False


# ---------------------------------------------------------------------------
# AC5 — POST /api/sources/{id}/run-verify triggers verification + returns source
# ---------------------------------------------------------------------------

class TestRunVerifySingle:
    def test_run_verify_returns_200_with_support_status(self, api_client, db_session):
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        resp = api_client.post(f"/api/sources/{sid}/run-verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sid
        assert data["support_status"] is not None
        assert data["rationale"] is not None
        assert data["manually_overridden"] is False

    def test_run_verify_persists_to_db(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        api_client.post(f"/api/sources/{sid}/run-verify")
        get_resp = api_client.get(f"/api/sources?plan_id={plan_id}")
        src = next(s for s in get_resp.json()["sources"] if s["id"] == sid)
        assert src["support_status"] is not None

    def test_run_verify_returns_404_for_unknown_source(self, api_client, db_session):
        resp = api_client.post(f"/api/sources/{uuid.uuid4()}/run-verify")
        assert resp.status_code == 404

    def test_run_verify_does_not_set_manually_overridden(self, api_client, db_session):
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        resp = api_client.post(f"/api/sources/{sid}/run-verify")
        assert resp.json()["manually_overridden"] is False


# ---------------------------------------------------------------------------
# AC6 — POST /api/plans/{id}/run-verify-all triggers verification for all sources
# ---------------------------------------------------------------------------

class TestRunVerifyAll:
    def test_run_verify_all_returns_200_with_results(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session, n_sources=3)
        resp = api_client.post(f"/api/plans/{plan_id}/run-verify-all")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 3

    def test_run_verify_all_each_result_has_support_status(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session, n_sources=2)
        resp = api_client.post(f"/api/plans/{plan_id}/run-verify-all")
        for result in resp.json()["results"]:
            assert result["support_status"] is not None
            assert result["rationale"] is not None
            assert result["manually_overridden"] is False

    def test_run_verify_all_persists_all_sources(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session, n_sources=2)
        api_client.post(f"/api/plans/{plan_id}/run-verify-all")
        get_resp = api_client.get(f"/api/sources?plan_id={plan_id}")
        for src in get_resp.json()["sources"]:
            assert src["support_status"] is not None

    def test_run_verify_all_returns_404_for_unknown_plan(self, api_client, db_session):
        resp = api_client.post(f"/api/plans/{uuid.uuid4()}/run-verify-all")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC8/AC9 — PATCH /api/sources/{id}/status-override persists manual override
# ---------------------------------------------------------------------------

class TestStatusOverride:
    def test_override_sets_manually_overridden_true(self, api_client, db_session):
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        resp = api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "contradicts", "rationale": "Manually overridden."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["support_status"] == "contradicts"
        assert data["rationale"] == "Manually overridden."
        assert data["manually_overridden"] is True

    def test_override_persists_on_refetch(self, api_client, db_session):
        _, plan_id, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "supports", "rationale": "Human says yes."},
        )
        get_resp = api_client.get(f"/api/sources?plan_id={plan_id}")
        src = next(s for s in get_resp.json()["sources"] if s["id"] == sid)
        assert src["support_status"] == "supports"
        assert src["manually_overridden"] is True

    def test_accepting_ai_result_clears_override_flag(self, api_client, db_session):
        """Confirming (accepting) the AI-assigned status should clear manually_overridden."""
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        # First AI verification sets status
        api_client.post(f"/api/sources/{sid}/run-verify")
        # User manually overrides
        api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "contradicts", "rationale": "Override."},
        )
        # User accepts AI result (clears override)
        resp = api_client.post(f"/api/sources/{sid}/accept-status")
        assert resp.status_code == 200
        assert resp.json()["manually_overridden"] is False

    def test_override_returns_404_for_unknown_source(self, api_client, db_session):
        resp = api_client.patch(
            f"/api/sources/{uuid.uuid4()}/status-override",
            json={"support_status": "supports", "rationale": "test"},
        )
        assert resp.status_code == 404

    def test_override_rejects_invalid_status(self, api_client, db_session):
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        resp = api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "invalid-value", "rationale": "test"},
        )
        assert resp.status_code == 422

    def test_run_verify_after_override_does_not_clear_if_manually_overridden(
        self, api_client, db_session
    ):
        """AI run-verify should NOT overwrite a manually_overridden source."""
        _, _, source_ids = _seed_case_with_plan_and_sources(db_session)
        sid = source_ids[0]
        api_client.patch(
            f"/api/sources/{sid}/status-override",
            json={"support_status": "contradicts", "rationale": "Human override."},
        )
        resp = api_client.post(f"/api/sources/{sid}/run-verify")
        # After run-verify on an overridden source, manually_overridden stays True
        assert resp.json()["manually_overridden"] is True
        assert resp.json()["support_status"] == "contradicts"


# ---------------------------------------------------------------------------
# AC10 — New sources default to unverified (support_status=null, manually_overridden=False)
# ---------------------------------------------------------------------------

class TestNewSourceDefaults:
    def test_newly_created_source_has_null_support_status(self, api_client, db_session):
        _, plan_id, _ = _seed_case_with_plan_and_sources(db_session, n_sources=0)
        resp = api_client.post(
            "/api/sources",
            json={
                "plan_id": plan_id,
                "kind": "article",
                "title": "Brand new source",
                "claim": "Some claim",
                "citation": "Some citation",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["support_status"] == "unverified"
        assert data["rationale"] is None
        assert data["manually_overridden"] is False
