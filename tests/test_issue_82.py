"""Tests for issue #82: Add suggest endpoint for non-persisting candidate sources.

AC coverage:
  AC1  – POST /api/plans/{plan_id}/gather/suggest exists, routed separately from gather
  AC2  – Returns 0-5 candidates; never persists to DB
  AC3  – Each candidate includes: candidate_id (UUID v4), kind, title, url, claim,
          citation, relevance_score (numeric)
  AC4  – Candidates ordered by relevance_score descending
  AC5  – Engine yields no results → 200 OK with empty candidates array
  AC6  – OrchestratorError (LLM/embedding unavailable) → 200 OK with empty candidates array
  AC7  – Existing POST /api/plans/{plan_id}/gather endpoint unchanged
  AC8  – suggest is routed as its own path (AC1 covers this)
  AC9  – Malformed/missing candidate fields → logged warning, candidate dropped, no 500
  AC10 – Integration tests: normal response, empty degradation, LLM-unavailable degradation
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# DB + client fixtures
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
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    cookie = create_session_cookie(AUTH_SECRET)
    client = TestClient(app)
    client.cookies.set("session", cookie)
    yield client
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_plan(db, mechanism="drug X lowers LDL", prior="0.5"):
    from datetime import datetime, timezone

    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        sharpened="test sharpened",
        not_investigating=json.dumps([]),
        stage="sharpened",
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism=mechanism,
        prior=prior,
        current_rank=1,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _make_source(kind="article", title="Test Title", url="https://example.com/a",
                 claim="A factual claim.", citation="Verbatim citation."):
    from app.research.types import Source
    return Source(kind=kind, title=title, url=url, claim=claim, citation=citation)


def _is_uuid4(value: str) -> bool:
    try:
        val = uuid.UUID(value, version=4)
        return str(val) == value
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# AC1 + AC8: Endpoint exists and is routed separately from gather
# ---------------------------------------------------------------------------

class TestSuggestEndpointExists:
    def test_suggest_returns_200_for_valid_plan(self, api_client, db_session):
        """POST /api/plans/{plan_id}/gather/suggest → 200 OK (AC1, AC8)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)

        with patch("app.routers.gather.run_research_for_plan", return_value=[]):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200

    def test_suggest_path_distinct_from_gather_path(self, api_client, db_session):
        """suggest path does not interfere with gather path (AC1, AC8)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)

        with patch("app.routers.gather.run_research_for_plan", return_value=[]) as mock_run:
            api_client.post(f"/api/plans/{plan.id}/gather/suggest")
            suggest_call_count = mock_run.call_count

        with patch("app.routers.gather.run_research_for_plan", return_value=[]) as mock_run:
            api_client.post(f"/api/plans/{plan.id}/gather")
            gather_call_count = mock_run.call_count

        assert suggest_call_count == 1
        assert gather_call_count == 1


# ---------------------------------------------------------------------------
# AC3: Required candidate fields
# ---------------------------------------------------------------------------

class TestCandidateFields:
    def test_candidate_has_all_required_fields(self, api_client, db_session):
        """Each candidate contains candidate_id, kind, title, url, claim, citation,
        relevance_score (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        body = resp.json()
        assert "candidates" in body
        assert len(body["candidates"]) == 1

        c = body["candidates"][0]
        required = {"candidate_id", "kind", "title", "url", "claim", "citation", "relevance_score"}
        assert required.issubset(c.keys()), f"Missing fields: {required - c.keys()}"

    def test_candidate_id_is_uuid_v4(self, api_client, db_session):
        """candidate_id is a UUID v4 string (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        c = resp.json()["candidates"][0]
        assert _is_uuid4(c["candidate_id"]), f"Not a UUID v4: {c['candidate_id']}"

    def test_candidate_kind_is_valid(self, api_client, db_session):
        """candidate kind is one of book/article/youtube (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [
            _make_source(kind="article"),
            _make_source(kind="book", url="https://example.com/b"),
            _make_source(kind="youtube", url="https://youtube.com/c"),
        ]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        kinds = {c["kind"] for c in resp.json()["candidates"]}
        assert kinds.issubset({"book", "article", "youtube"})

    def test_relevance_score_is_numeric(self, api_client, db_session):
        """relevance_score is a number (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        c = resp.json()["candidates"][0]
        assert isinstance(c["relevance_score"], (int, float))

    def test_each_suggest_call_generates_unique_candidate_ids(self, api_client, db_session):
        """candidate_id differs across calls (AC3 — UUIDs are client-generated per call)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            r1 = api_client.post(f"/api/plans/{plan.id}/gather/suggest")
            r2 = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        id1 = r1.json()["candidates"][0]["candidate_id"]
        id2 = r2.json()["candidates"][0]["candidate_id"]
        assert id1 != id2


# ---------------------------------------------------------------------------
# AC4: Ordered by relevance_score descending
# ---------------------------------------------------------------------------

class TestCandidateOrdering:
    def test_candidates_ordered_by_relevance_score_desc(self, api_client, db_session):
        """Candidates are in descending relevance_score order (AC4)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [
            _make_source(url=f"https://example.com/{i}", title=f"Title {i}")
            for i in range(4)
        ]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        scores = [c["relevance_score"] for c in resp.json()["candidates"]]
        assert scores == sorted(scores, reverse=True), f"Scores not descending: {scores}"

    def test_single_candidate_has_max_score(self, api_client, db_session):
        """Single candidate gets highest (1.0) relevance_score (AC4)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        c = resp.json()["candidates"][0]
        assert c["relevance_score"] == 1.0


# ---------------------------------------------------------------------------
# AC2: Never persists to DB; caps at 5
# ---------------------------------------------------------------------------

class TestNoPersistenceAndCap:
    def test_suggest_does_not_persist_sources(self, api_client, db_session):
        """After suggest call, plan sources list is unchanged (AC2)."""
        from unittest.mock import patch

        from app import models

        plan = _create_plan(db_session)
        sources_before = (
            db_session.query(models.Source)
            .filter(models.Source.plan_id == plan.id)
            .count()
        )

        engine_sources = [
            _make_source(url=f"https://example.com/{i}", title=f"T{i}")
            for i in range(3)
        ]

        with patch("app.routers.gather.run_research_for_plan", return_value=engine_sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        sources_after = (
            db_session.query(models.Source)
            .filter(models.Source.plan_id == plan.id)
            .count()
        )
        assert sources_after == sources_before, (
            f"Sources were persisted: before={sources_before}, after={sources_after}"
        )

    def test_suggest_caps_at_five_candidates(self, api_client, db_session):
        """At most 5 candidates returned even when engine produces more (AC2)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        engine_sources = [
            _make_source(url=f"https://example.com/{i}", title=f"T{i}")
            for i in range(10)
        ]

        with patch("app.routers.gather.run_research_for_plan", return_value=engine_sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        candidates = resp.json()["candidates"]
        assert len(candidates) <= 5, f"Returned {len(candidates)} candidates, expected ≤ 5"


# ---------------------------------------------------------------------------
# AC5: Empty engine results → 200 with empty candidates array
# ---------------------------------------------------------------------------

class TestEmptyDegradation:
    def test_empty_engine_result_returns_200_with_empty_array(self, api_client, db_session):
        """Engine yields no results → 200 OK with candidates=[] (AC5, AC10)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)

        with patch("app.routers.gather.run_research_for_plan", return_value=[]):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"candidates": []}


# ---------------------------------------------------------------------------
# AC6: LLM/embedding unavailable → 200 with empty candidates array
# ---------------------------------------------------------------------------

class TestLLMUnavailableDegradation:
    def test_orchestrator_error_returns_200_with_empty_candidates(self, api_client, db_session):
        """OrchestratorError → 200 OK with candidates=[] — no 500 (AC6, AC10)."""
        from unittest.mock import patch

        from app.services.research_orchestrator import OrchestratorError

        plan = _create_plan(db_session)

        with patch(
            "app.routers.gather.run_research_for_plan",
            side_effect=OrchestratorError("LLM endpoint unreachable"),
        ):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        assert resp.json() == {"candidates": []}

    def test_generic_exception_in_engine_returns_200_with_empty_candidates(
        self, api_client, db_session
    ):
        """Any unhandled exception wrapped by orchestrator → 200 with candidates=[] (AC6)."""
        from unittest.mock import patch

        from app.services.research_orchestrator import OrchestratorError

        plan = _create_plan(db_session)

        # run_research_for_plan wraps all exceptions as OrchestratorError
        with patch(
            "app.routers.gather.run_research_for_plan",
            side_effect=OrchestratorError("embedding service timed out"),
        ):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []


# ---------------------------------------------------------------------------
# AC7: Existing gather endpoint unchanged
# ---------------------------------------------------------------------------

class TestExistingGatherUnchanged:
    def test_existing_gather_still_persists_sources(self, api_client, db_session):
        """POST /api/plans/{plan_id}/gather still auto-attaches sources (AC7)."""
        from unittest.mock import patch

        from app import models

        plan = _create_plan(db_session)
        engine_sources = [_make_source()]

        with patch("app.routers.gather.run_research_for_plan", return_value=engine_sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather")

        assert resp.status_code == 200
        body = resp.json()
        assert "sources" in body
        assert len(body["sources"]) >= 1

        persisted = (
            db_session.query(models.Source)
            .filter(models.Source.plan_id == plan.id)
            .count()
        )
        assert persisted >= 1, "Gather endpoint did not persist sources"

    def test_gather_response_has_plan_id_and_status(self, api_client, db_session):
        """Existing gather response shape is unchanged (AC7)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)

        with patch("app.routers.gather.run_research_for_plan", return_value=[]):
            resp = api_client.post(f"/api/plans/{plan.id}/gather")

        assert resp.status_code == 200
        body = resp.json()
        assert "plan_id" in body
        assert "gather_status" in body
        assert "sources" in body


# ---------------------------------------------------------------------------
# AC9: Malformed candidate fields → warning logged, candidate dropped
# ---------------------------------------------------------------------------

class TestMalformedCandidateDropped:
    def test_invalid_kind_dropped_with_warning(self, api_client, db_session, caplog):
        """Candidate with invalid kind → dropped + WARNING logged, no 500 (AC9)."""
        from unittest.mock import MagicMock, patch

        plan = _create_plan(db_session)

        bad_source = MagicMock()
        bad_source.kind = "invalid_kind"
        bad_source.title = "Good Title"
        bad_source.url = "https://example.com/a"
        bad_source.claim = "A claim."
        bad_source.citation = "A citation."

        with caplog.at_level(logging.WARNING, logger="app.routers.gather"):
            with patch("app.routers.gather.run_research_for_plan", return_value=[bad_source]):
                resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []
        assert any("invalid_kind" in r.message or "invalid kind" in r.message for r in caplog.records), (
            f"Expected warning about invalid kind; got: {[r.message for r in caplog.records]}"
        )

    def test_empty_title_dropped_with_warning(self, api_client, db_session, caplog):
        """Candidate with empty title → dropped + WARNING logged (AC9)."""
        from unittest.mock import MagicMock, patch

        plan = _create_plan(db_session)

        bad_source = MagicMock()
        bad_source.kind = "article"
        bad_source.title = ""
        bad_source.url = "https://example.com/a"
        bad_source.claim = "A claim."
        bad_source.citation = "A citation."

        with caplog.at_level(logging.WARNING, logger="app.routers.gather"):
            with patch("app.routers.gather.run_research_for_plan", return_value=[bad_source]):
                resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []
        assert any("title" in r.message for r in caplog.records)

    def test_valid_and_invalid_mixed_only_valid_returned(self, api_client, db_session):
        """Mix of valid and malformed → only valid candidates returned (AC9)."""
        from unittest.mock import MagicMock, patch

        plan = _create_plan(db_session)

        good = _make_source(url="https://example.com/good")
        bad = MagicMock()
        bad.kind = "article"
        bad.title = ""
        bad.url = "https://example.com/bad"
        bad.claim = "claim"
        bad.citation = "citation"

        with patch("app.routers.gather.run_research_for_plan", return_value=[good, bad]):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        candidates = resp.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["url"] == "https://example.com/good"

    def test_all_malformed_returns_empty_no_500(self, api_client, db_session):
        """All malformed candidates → 200 with empty array, not 500 (AC9)."""
        from unittest.mock import MagicMock, patch

        plan = _create_plan(db_session)

        bad = MagicMock()
        bad.kind = "NOT_VALID"
        bad.title = ""
        bad.url = ""
        bad.claim = ""
        bad.citation = ""

        with patch("app.routers.gather.run_research_for_plan", return_value=[bad]):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        assert resp.json()["candidates"] == []


# ---------------------------------------------------------------------------
# 404 for non-existent plan (UAT step 6)
# ---------------------------------------------------------------------------

class TestPlanNotFound:
    def test_suggest_returns_404_for_unknown_plan(self, api_client, db_session):
        """Non-existent plan_id → 404 Not Found (UAT step 6)."""
        resp = api_client.post(f"/api/plans/{uuid.uuid4()}/gather/suggest")
        assert resp.status_code == 404

    def test_suggest_404_response_has_detail(self, api_client):
        """404 response contains a detail message."""
        resp = api_client.post(f"/api/plans/{uuid.uuid4()}/gather/suggest")
        body = resp.json()
        assert "detail" in body


# ---------------------------------------------------------------------------
# AC10: Integration — normal response with ranked candidates
# ---------------------------------------------------------------------------

class TestIntegrationNormalResponse:
    def test_normal_response_returns_ranked_candidates(self, api_client, db_session):
        """Normal flow: engine returns 3 sources → 200 with 3 ranked candidates (AC10)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        sources = [
            _make_source(url=f"https://example.com/{i}", title=f"Source {i}", kind="article")
            for i in range(3)
        ]

        with patch("app.routers.gather.run_research_for_plan", return_value=sources):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        assert resp.status_code == 200
        body = resp.json()
        assert "candidates" in body
        candidates = body["candidates"]
        assert len(candidates) == 3

        for c in candidates:
            assert _is_uuid4(c["candidate_id"])
            assert c["kind"] in {"book", "article", "youtube"}
            assert c["title"]
            assert c["url"]
            assert c["claim"]
            assert c["citation"]
            assert isinstance(c["relevance_score"], (int, float))

        scores = [c["relevance_score"] for c in candidates]
        assert scores == sorted(scores, reverse=True)

    def test_suggest_uses_plan_mechanism_and_prior(self, api_client, db_session):
        """Research loop is called with the plan's mechanism and prior (AC10)."""
        from unittest.mock import patch

        plan = _create_plan(db_session, mechanism="statin reduces LDL", prior="0.7")

        with patch("app.routers.gather.run_research_for_plan", return_value=[]) as mock_run:
            api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else {}
        args = mock_run.call_args.args if mock_run.call_args.args else ()
        call_args = {**dict(zip(["plan_mechanism", "plan_prior", "engine"], args)), **kwargs}
        assert call_args.get("plan_mechanism") == "statin reduces LDL"
        assert call_args.get("plan_prior") == "0.7"
