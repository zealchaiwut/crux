"""Tests for issue #101: Integration tests for source verification pipeline.

AC coverage:
  AC1  – Test file exists at tests/test_issue_101.py
  AC2  – supporting source → DB record has verdict='supports' and non-null summary
  AC3  – contradicting source → DB record has verdict='contradicts' and non-null summary
  AC4  – paywalled/blocked fetch → DB record has verdict='unverified' and reason explains failure
  AC5  – All tests use SQLite in-memory DB (no disk artifact, no teardown required)
  AC6  – Fetch is mocked (no real HTTP calls); Claude is mocked (no real API calls)
  AC7  – All three tests pass in CI
  AC8  – No test shares state (each test sets up its own DB schema and data)
"""
import uuid

import pytest

from app.research.types import FetchBlockedError


# ---------------------------------------------------------------------------
# Per-test DB helpers — no shared state (AC8)
# ---------------------------------------------------------------------------

def _make_session():
    """Return a fresh in-memory SQLite session with all tables created."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def _seed_source(session, url="https://example.com/article", claim="The treatment reduces inflammation."):
    """Create a minimal case → plan → source chain and return source_id."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened problem",
        stage="gather",
    )
    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="mechanism",
        prior="0.50",
    )
    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="article",
        title="Test Source",
        url=url,
        claim=claim,
        citation="Example et al. 2024",
    )
    session.add_all([case, plan, source])
    session.commit()
    return source.id


# ---------------------------------------------------------------------------
# AC2 — supporting source → verdict='supports', non-null summary
# ---------------------------------------------------------------------------

class TestSupportingSource:
    def test_supporting_source_verdict_and_summary(self):
        """Pipeline writes verdict='supports' and a non-null summary to the DB."""
        session, engine = _make_session()
        try:
            source_id = _seed_source(session)

            def mock_fetch(url):
                assert url.startswith("http"), "fetch_fn received a non-URL"
                return "This article provides clear empirical evidence that the treatment reduces inflammation in controlled trials."

            def mock_analyze(content, claim):
                assert content  # confirm content was passed
                return {
                    "verdict": "supports",
                    "summary": "The source confirms the claim with double-blind trial data.",
                }

            from app.services.source_verification import run_verification_pipeline

            record = run_verification_pipeline(session, source_id, mock_fetch, mock_analyze)

            assert record.verdict == "supports"
            assert record.summary is not None
            assert len(record.summary) > 0
            assert record.reason is None
            assert record.source_id == source_id
        finally:
            session.close()
            engine.dispose()


# ---------------------------------------------------------------------------
# AC3 — contradicting source → verdict='contradicts', non-null summary
# ---------------------------------------------------------------------------

class TestContradictingSource:
    def test_contradicting_source_verdict_and_summary(self):
        """Pipeline writes verdict='contradicts' and a non-null summary to the DB."""
        session, engine = _make_session()
        try:
            source_id = _seed_source(session)

            def mock_fetch(url):
                return "This meta-analysis found no reduction in inflammation with this treatment."

            def mock_analyze(content, claim):
                return {
                    "verdict": "contradicts",
                    "summary": "The source refutes the claim: no effect observed in the meta-analysis.",
                }

            from app.services.source_verification import run_verification_pipeline

            record = run_verification_pipeline(session, source_id, mock_fetch, mock_analyze)

            assert record.verdict == "contradicts"
            assert record.summary is not None
            assert len(record.summary) > 0
            assert record.reason is None
            assert record.source_id == source_id
        finally:
            session.close()
            engine.dispose()


# ---------------------------------------------------------------------------
# AC4 — paywalled/blocked fetch → verdict='unverified', reason explains failure
# ---------------------------------------------------------------------------

class TestPaywalledSource:
    def test_paywall_blocked_fetch_verdict_unverified_with_reason(self):
        """When fetch raises FetchBlockedError, pipeline writes verdict='unverified' and a reason."""
        session, engine = _make_session()
        try:
            source_id = _seed_source(session, url="https://paywalled-journal.com/article/42")

            def mock_fetch(url):
                raise FetchBlockedError(f"HTTP 403 fetching {url}: access denied (paywall)")

            def mock_analyze(content, claim):
                raise AssertionError("analyze must not be called when fetch fails")

            from app.services.source_verification import run_verification_pipeline

            record = run_verification_pipeline(session, source_id, mock_fetch, mock_analyze)

            assert record.verdict == "unverified"
            assert record.reason is not None
            assert len(record.reason) > 0
            assert "403" in record.reason or "paywall" in record.reason.lower() or "denied" in record.reason.lower()
            assert record.summary is None
            assert record.source_id == source_id
        finally:
            session.close()
            engine.dispose()
