"""Tests for issue #87: Improve relevance_score formula in gather suggest endpoint.

AC coverage:
  AC1 – Formula updated to distribute scores evenly based on actual candidate count;
         old formula `1.0 - i * 0.1` is removed.
  AC2 – Highest-ranked candidate (i=0) always receives relevance_score = 1.0.
  AC3 – Lowest-ranked candidate always receives score > 0.0 (no zero or negative scores).
  AC4 – With exactly 5 candidates: scores are 1.0, 0.8, 0.6, 0.4, 0.2.
  AC5 – With fewer than 5 candidates, scores span from 1.0 down with no gaps at the high end.
  AC6 – Scores are rounded to 2 decimal places.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# DB + client fixtures (reuse pattern from test_issue_82.py)
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


def _make_sources(n: int):
    return [
        _make_source(url=f"https://example.com/{i}", title=f"Source {i}")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# AC2: Highest-ranked candidate always gets 1.0
# ---------------------------------------------------------------------------

class TestHighestRankedAlwaysOnePointZero:
    def test_single_candidate_gets_score_1_0(self, api_client, db_session):
        """1 candidate → relevance_score = 1.0 (AC2)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(1)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["relevance_score"] == 1.0

    def test_two_candidates_first_gets_score_1_0(self, api_client, db_session):
        """2 candidates → first has relevance_score = 1.0 (AC2)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(2)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 2
        assert candidates[0]["relevance_score"] == 1.0

    def test_three_candidates_first_gets_score_1_0(self, api_client, db_session):
        """3 candidates → first has relevance_score = 1.0 (AC2)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(3)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 3
        assert candidates[0]["relevance_score"] == 1.0

    def test_five_candidates_first_gets_score_1_0(self, api_client, db_session):
        """5 candidates → first has relevance_score = 1.0 (AC2)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(5)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 5
        assert candidates[0]["relevance_score"] == 1.0


# ---------------------------------------------------------------------------
# AC3: Lowest-ranked always > 0.0
# ---------------------------------------------------------------------------

class TestLowestRankedAboveZero:
    def test_single_candidate_score_above_zero(self, api_client, db_session):
        """1 candidate → score > 0.0 (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(1)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert all(c["relevance_score"] > 0.0 for c in candidates)

    def test_two_candidates_all_scores_above_zero(self, api_client, db_session):
        """2 candidates → both scores > 0.0 (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(2)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 2
        assert all(c["relevance_score"] > 0.0 for c in candidates)

    def test_five_candidates_all_scores_above_zero(self, api_client, db_session):
        """5 candidates → all scores > 0.0, lowest is 0.2 not 0.0 (AC3)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(5)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 5
        assert all(c["relevance_score"] > 0.0 for c in candidates)
        assert min(c["relevance_score"] for c in candidates) == 0.2


# ---------------------------------------------------------------------------
# AC4: Exactly 5 candidates → scores 1.0, 0.8, 0.6, 0.4, 0.2
# ---------------------------------------------------------------------------

class TestFiveCandidateScores:
    def test_five_candidates_exact_scores(self, api_client, db_session):
        """5 candidates → scores are exactly 1.0, 0.8, 0.6, 0.4, 0.2 (AC4)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(5)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 5
        scores = [c["relevance_score"] for c in candidates]
        assert scores == [1.0, 0.8, 0.6, 0.4, 0.2], f"Expected [1.0, 0.8, 0.6, 0.4, 0.2], got {scores}"


# ---------------------------------------------------------------------------
# AC5: Fewer than 5 candidates → scores span from 1.0 with no gaps at high end
# ---------------------------------------------------------------------------

class TestFewerThanFiveCandidates:
    def test_two_candidates_scores_span_correctly(self, api_client, db_session):
        """2 candidates → scores are 1.0, 0.5 (no gap at high end) (AC5)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(2)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 2
        scores = [c["relevance_score"] for c in candidates]
        assert scores == [1.0, 0.5], f"Expected [1.0, 0.5], got {scores}"

    def test_three_candidates_scores_span_correctly(self, api_client, db_session):
        """3 candidates → scores are 1.0, 0.67, 0.33 (AC5)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(3)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 3
        scores = [c["relevance_score"] for c in candidates]
        assert scores == [1.0, 0.67, 0.33], f"Expected [1.0, 0.67, 0.33], got {scores}"

    def test_four_candidates_scores_span_correctly(self, api_client, db_session):
        """4 candidates → scores are 1.0, 0.75, 0.5, 0.25 (AC5)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(4)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert len(candidates) == 4
        scores = [c["relevance_score"] for c in candidates]
        assert scores == [1.0, 0.75, 0.5, 0.25], f"Expected [1.0, 0.75, 0.5, 0.25], got {scores}"

    def test_three_candidates_first_score_is_not_less_than_one(self, api_client, db_session):
        """With 3 candidates, highest score is 1.0 (not 0.9 as with old formula) (AC5)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(3)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        assert candidates[0]["relevance_score"] == 1.0, (
            f"Expected 1.0 for top candidate with 3 results, got {candidates[0]['relevance_score']}"
        )


# ---------------------------------------------------------------------------
# AC6: Scores rounded to 2 decimal places
# ---------------------------------------------------------------------------

class TestScoresRoundedToTwoDecimalPlaces:
    def test_three_candidates_scores_have_at_most_two_decimal_places(self, api_client, db_session):
        """3 candidates → scores have at most 2 decimal places (AC6)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(3)):
            resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

        candidates = resp.json()["candidates"]
        for c in candidates:
            score = c["relevance_score"]
            rounded = round(score, 2)
            assert score == rounded, f"Score {score} is not rounded to 2 decimal places"

    def test_all_candidate_counts_produce_two_decimal_scores(self, api_client, db_session):
        """All candidate counts 1-5 → all scores rounded to 2 decimal places (AC6)."""
        from unittest.mock import patch

        plan = _create_plan(db_session)
        for n in range(1, 6):
            with patch("app.routers.gather.run_research_for_plan", return_value=_make_sources(n)):
                resp = api_client.post(f"/api/plans/{plan.id}/gather/suggest")

            candidates = resp.json()["candidates"]
            for c in candidates:
                score = c["relevance_score"]
                assert score == round(score, 2), (
                    f"With {n} candidates, score {score} is not rounded to 2 decimal places"
                )


# ---------------------------------------------------------------------------
# AC1: Old formula no longer present (checked via source inspection)
# ---------------------------------------------------------------------------

class TestOldFormulaRemoved:
    def test_old_hardcoded_formula_not_in_source(self):
        """The old formula `1.0 - i * 0.1` is not present in gather.py (AC1)."""
        import ast
        import pathlib

        gather_path = pathlib.Path(__file__).parent.parent / "app" / "routers" / "gather.py"
        source = gather_path.read_text()
        assert "1.0 - i * 0.1" not in source, (
            "Old hardcoded formula `1.0 - i * 0.1` still present in gather.py"
        )

    def test_new_formula_uses_len_top_sources(self):
        """The new formula references len(top_sources) as divisor (AC1)."""
        import pathlib

        gather_path = pathlib.Path(__file__).parent.parent / "app" / "routers" / "gather.py"
        source = gather_path.read_text()
        assert "len(top_sources)" in source, (
            "New formula does not reference len(top_sources) in gather.py"
        )
