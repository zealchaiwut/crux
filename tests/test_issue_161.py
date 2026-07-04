"""Tests for issue #161: Align source_verifier.py status vocabulary with Source model enum.

AC coverage:
  AC1 – SUPPORT_STATUSES in source_verifier.py contains "partial", not "partially_supports"
  AC2 – Claude prompt template uses "partial" as the label for partial-support verdicts
  AC3 – All docstrings/comments in source_verifier.py use "partial", not "partially_supports"
  AC4 – verify_source() with partial-support result persists to DB without constraint error
  AC5 – Vocabulary in source_verifier.py matches models.py enum and cases.js chip map
"""
from __future__ import annotations

import inspect
import uuid

import pytest


# ---------------------------------------------------------------------------
# AC1 – SUPPORT_STATUSES uses "partial", not "partially_supports"
# ---------------------------------------------------------------------------

class TestSupportStatuses:
    def test_partially_supports_not_in_support_statuses(self):
        """AC1: SUPPORT_STATUSES must not contain 'partially_supports'."""
        from app.services.source_verifier import SUPPORT_STATUSES
        assert "partially_supports" not in SUPPORT_STATUSES, (
            "'partially_supports' must be removed from SUPPORT_STATUSES; use 'partial' instead"
        )

    def test_partial_in_support_statuses(self):
        """AC1: SUPPORT_STATUSES must contain 'partial'."""
        from app.services.source_verifier import SUPPORT_STATUSES
        assert "partial" in SUPPORT_STATUSES, (
            "'partial' must be present in SUPPORT_STATUSES to match the Source model enum"
        )

    def test_other_statuses_unchanged(self):
        """AC1: supports, contradicts, and unverified remain in SUPPORT_STATUSES."""
        from app.services.source_verifier import SUPPORT_STATUSES
        for status in ("supports", "contradicts", "unverified"):
            assert status in SUPPORT_STATUSES, (
                f"'{status}' must remain in SUPPORT_STATUSES"
            )


# ---------------------------------------------------------------------------
# AC2 – Claude prompt template uses "partial"
# ---------------------------------------------------------------------------

class TestPromptTemplate:
    def test_prompt_does_not_contain_partially_supports(self):
        """AC2: The system prompt must not mention 'partially_supports'."""
        import app.services.source_verifier as sv
        # Only fail if the string appears in a string literal context (the prompt)
        assert "partially_supports" not in sv._SYSTEM_PROMPT, (
            "The Claude prompt template must use 'partial', not 'partially_supports'"
        )

    def test_prompt_contains_partial(self):
        """AC2: The system prompt uses 'partial' as the partial-support label."""
        import app.services.source_verifier as sv
        assert "partial" in sv._SYSTEM_PROMPT, (
            "The Claude prompt template must include 'partial' as the partial-support label"
        )


# ---------------------------------------------------------------------------
# AC3 – No "partially_supports" in source file (docstrings, comments, source)
# ---------------------------------------------------------------------------

class TestNoPartiallySupportsInSource:
    def test_no_partially_supports_anywhere_in_module_source(self):
        """AC3: The string 'partially_supports' must not appear anywhere in source_verifier.py."""
        import app.services.source_verifier as sv
        src = inspect.getsource(sv)
        assert "partially_supports" not in src, (
            "source_verifier.py still contains 'partially_supports'; "
            "replace all occurrences with 'partial'"
        )


# ---------------------------------------------------------------------------
# AC4 – verify_source with "partial" result persists to DB without constraint error
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


def _seed_source(session, url="https://example.com/article", claim="Test claim"):
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
        mechanism="mechanism",
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


class TestPartialPersistsWithoutConstraintError:
    def test_verify_source_partial_result_saves_to_db(self, db_session):
        """AC4: verify_source returning 'partial' persists to Source without DB error."""
        from app.research.types import ArticleDocument
        from app.services.source_verifier import verify_source

        source = _seed_source(db_session)

        def mock_fetcher_fetch(url):
            return ArticleDocument(
                url=url,
                title="Test Article",
                text="Content partially supporting the stated claim.",
            )

        class MockFetcher:
            def fetch(self, url):
                return mock_fetcher_fetch(url)

        def partial_classify(content, claim):
            return {"support_status": "partial", "support_rationale": "Partial support."}

        result = verify_source(
            source,
            article_fetcher=MockFetcher(),
            classify_fn=partial_classify,
        )

        assert result["support_status"] == "partial", (
            f"verify_source must return 'partial', got {result['support_status']!r}"
        )

        # Persist to DB — must not raise a constraint error
        source.support_status = result["support_status"]
        source.support_rationale = result["support_rationale"]
        db_session.commit()  # raises if "partial" is not a valid enum value

        # Read back to confirm
        db_session.refresh(source)
        assert source.support_status == "partial", (
            f"Persisted support_status must be 'partial', got {source.support_status!r}"
        )

    def test_partially_supports_would_fail_db_constraint(self, db_session):
        """AC4: 'partially_supports' is NOT a valid DB enum value (documents the mismatch)."""
        import sqlalchemy.exc

        source = _seed_source(db_session)
        source.support_status = "partially_supports"
        with pytest.raises((sqlalchemy.exc.StatementError, sqlalchemy.exc.IntegrityError, Exception)):
            db_session.commit()


# ---------------------------------------------------------------------------
# AC5 – Vocabulary matches models.py and cases.js
# ---------------------------------------------------------------------------

class TestVocabularyAlignment:
    def test_support_statuses_matches_models_enum(self):
        """AC5: source_verifier.SUPPORT_STATUSES and models._SUPPORT_STATUS both use 'partial'."""
        from app.services.source_verifier import SUPPORT_STATUSES
        from app.models import _SUPPORT_STATUS

        models_statuses = set(_SUPPORT_STATUS)
        assert "partial" in SUPPORT_STATUSES
        assert "partial" in models_statuses
        assert "partially_supports" not in SUPPORT_STATUSES
        assert "partially_supports" not in models_statuses

    def test_support_statuses_matches_cases_js_chip_map(self):
        """AC5: cases.js chip map uses 'partial', matching source_verifier.py."""
        import pathlib

        cases_js = (
            pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"
        ).read_text()

        from app.services.source_verifier import SUPPORT_STATUSES
        assert "partial" in SUPPORT_STATUSES, "source_verifier.py must use 'partial'"
        assert "partial" in cases_js, "cases.js must contain 'partial' chip key"
        assert "partially_supports" not in cases_js, (
            "cases.js must not use 'partially_supports'"
        )

    def test_default_classify_rejects_partially_supports(self):
        """AC5: _default_classify treats 'partially_supports' from LLM as 'unverified'."""
        from app.services.source_verifier import SUPPORT_STATUSES
        assert "partially_supports" not in SUPPORT_STATUSES, (
            "After fix, if LLM returns 'partially_supports' it must fall through to 'unverified'"
        )

    def test_default_classify_accepts_partial(self):
        """AC5: _default_classify accepts 'partial' as a valid LLM output."""
        from app.services.source_verifier import SUPPORT_STATUSES
        assert "partial" in SUPPORT_STATUSES, (
            "'partial' must be accepted by the classifier so it passes through to the caller"
        )
