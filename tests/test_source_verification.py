"""Unit tests for source verification pipeline and plan re-ranking.

AC coverage (issue #158):
  AC1 – mocked fetch (readable) + Claude 'supports' → SourceVerification.verdict=='supports',
         summary (confidence) attached
  AC2 – mocked fetch (readable) + Claude 'contradicts' → SourceVerification.verdict=='contradicts'
  AC3 – mocked fetch raises FetchBlockedError → verdict=='unverified', human-readable reason field
  AC4 – plan with a 'contradicts' source ranks lower than equivalent plan with only 'supports' sources
  AC5 – all tests pass with no live network or Claude API calls; all I/O mocked
  AC6 – shared mock state reset between cases (per-test fixtures)
"""
import os
import uuid

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


# ---------------------------------------------------------------------------
# DB fixture — isolated SQLite in-memory session per test
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
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
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _seed_source(session, url="https://example.com/article", claim="Exercise improves cognition"):
    """Create a minimal Case → Plan → Source chain and return the Source."""
    from app import models

    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="test problem",
        stage="gather",
    )
    session.add(case)
    session.flush()

    plan = models.Plan(
        id=str(uuid.uuid4()),
        case_id=case.id,
        label="A",
        name="Plan A",
        mechanism="some mechanism",
    )
    session.add(plan)
    session.flush()

    source = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="article",
        url=url,
        claim=claim,
    )
    session.add(source)
    session.commit()
    return source


# ---------------------------------------------------------------------------
# AC1: supports verdict → summary (confidence) attached
# ---------------------------------------------------------------------------

def test_supports_verdict_sets_summary(db_session):
    """AC1: mock fetch + Claude 'supports' → verdict='supports', summary non-empty."""
    from app.services.source_verification import run_verification_pipeline

    source = _seed_source(db_session)

    def mock_fetch(url):
        return "Aerobic exercise significantly improves memory and executive function."

    def mock_analyze(content, claim):
        return {"verdict": "supports", "summary": "Content directly validates the claim (confidence: high)."}

    record = run_verification_pipeline(db_session, source.id, mock_fetch, mock_analyze)

    assert record.verdict == "supports", f"Expected 'supports', got {record.verdict!r}"
    assert record.summary, "Summary (confidence indicator) must be attached for 'supports' verdict"
    assert record.source_id == source.id


# ---------------------------------------------------------------------------
# AC2: contradicts verdict
# ---------------------------------------------------------------------------

def test_contradicts_verdict(db_session):
    """AC2: mock fetch + Claude 'contradicts' → verdict='contradicts'."""
    from app.services.source_verification import run_verification_pipeline

    source = _seed_source(db_session)

    def mock_fetch(url):
        return "Study finds no cognitive benefit from aerobic exercise in healthy adults."

    def mock_analyze(content, claim):
        return {"verdict": "contradicts", "summary": "Content refutes the claim."}

    record = run_verification_pipeline(db_session, source.id, mock_fetch, mock_analyze)

    assert record.verdict == "contradicts", f"Expected 'contradicts', got {record.verdict!r}"
    assert record.source_id == source.id


# ---------------------------------------------------------------------------
# AC3: blocked fetch → unverified with human-readable reason
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc_label,exc_factory", [
    ("paywalled", lambda: __import__("app.research.types", fromlist=["FetchBlockedError"]).FetchBlockedError("paywalled")),
    ("fetch_blocked", lambda: __import__("app.research.types", fromlist=["FetchBlockedError"]).FetchBlockedError("fetch_blocked")),
    ("timeout", lambda: __import__("app.research.types", fromlist=["FetchTimeoutError"]).FetchTimeoutError("timeout")),
])
def test_blocked_fetch_gives_unverified_with_reason(db_session, exc_label, exc_factory):
    """AC3: fetch raises a block/timeout error → verdict='unverified', reason field set."""
    from app.services.source_verification import run_verification_pipeline

    source = _seed_source(db_session)
    exc = exc_factory()

    def mock_fetch(url):
        raise exc

    def mock_analyze(content, claim):  # pragma: no cover
        raise AssertionError("analyze must not be called when fetch fails")

    record = run_verification_pipeline(db_session, source.id, mock_fetch, mock_analyze)

    assert record.verdict == "unverified", f"Expected 'unverified', got {record.verdict!r}"
    assert record.reason, "reason field must be populated when fetch is blocked"
    assert exc_label in record.reason, (
        f"reason should mention the failure kind '{exc_label}'; got: {record.reason!r}"
    )


# ---------------------------------------------------------------------------
# AC4: plan with contradicts source ranks lower after apply_source_penalties
# ---------------------------------------------------------------------------

def test_contradicted_plan_ranks_lower(db_session):
    """AC4: apply_source_penalties demotes a plan with a 'contradicts' source below
    an otherwise equivalent plan that has only 'supports' sources.

    With n=3 plans and CONTRADICTED_MULTIPLIER=0.5:
      A (rank 1): raw=3, penalty×0.5 → adj=1.5
      B (rank 2): raw=2, no penalty     → adj=2.0   ← B wins
      C (rank 3): raw=1, no penalty     → adj=1.0
    So B rises to rank 1 and A drops to rank 2.
    """
    from app.weigh import apply_source_penalties

    ranked = [
        {"label": "A", "rank": 1, "standing": None, "rationale": "Best fit initially."},
        {"label": "B", "rank": 2, "standing": None, "rationale": "Second best."},
        {"label": "C", "rank": 3, "standing": None, "rationale": "Third."},
    ]
    plans_with_sources = [
        {"label": "A", "sources": [{"support_status": "contradicts", "title": "Refuting study"}]},
        {"label": "B", "sources": [{"support_status": "supports", "title": "Supporting study"}]},
        {"label": "C", "sources": []},
    ]

    result = apply_source_penalties(ranked, plans_with_sources)

    rank_by_label = {item["label"]: item["rank"] for item in result}
    assert rank_by_label["B"] < rank_by_label["A"], (
        f"Plan B (supports only) must outrank Plan A (contradicts source); "
        f"got B={rank_by_label['B']}, A={rank_by_label['A']}"
    )
    # Confirm A carries the contradicted_sources field
    a_item = next(x for x in result if x["label"] == "A")
    assert a_item["contradicted_sources"], "Plan A must list its contradicted sources"
    assert a_item["adjusted_score"] < a_item["raw_score"], (
        "adjusted_score must be lower than raw_score for a plan with contradicted sources"
    )
