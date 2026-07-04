"""Tests for issue #161: Align source_verifier.py status vocabulary with Source model enum (runs against UAT)"""
import os
import sys
import re
import json
import pytest
import httpx


BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


# Add repo root to path for importing app modules
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from app.services.source_verifier import SUPPORT_STATUSES, _SYSTEM_PROMPT
from app.models import _SUPPORT_STATUS


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_support_statuses_no_partially_supports():
    # AC1: `SUPPORT_STATUSES` in `app/services/source_verifier.py` no longer contains
    # `"partially_supports"`; it contains `"partial"` instead.
    assert "partially_supports" not in SUPPORT_STATUSES, \
        f"SUPPORT_STATUSES should not contain 'partially_supports'. Got: {SUPPORT_STATUSES}"
    assert "partial" in SUPPORT_STATUSES, \
        f"SUPPORT_STATUSES should contain 'partial'. Got: {SUPPORT_STATUSES}"


def test_system_prompt_uses_partial():
    # AC2: The Claude prompt template inside `source_verifier.py` uses `"partial"`
    # (not `"partially_supports"`) as the label/example for partial support verdicts.
    assert "partially_supports" not in _SYSTEM_PROMPT, \
        "Claude prompt template should not reference 'partially_supports'"
    assert "partial" in _SYSTEM_PROMPT, \
        "Claude prompt template should reference 'partial' for partial support"


def test_docstrings_comments_use_partial():
    # AC3: All docstrings and inline comments in `source_verifier.py` that reference
    # the partial-support status use `"partial"`.
    # Read the source file and check for vocabulary
    source_file = os.path.join(REPO_ROOT, "app", "services", "source_verifier.py")
    with open(source_file, "r") as f:
        content = f.read()

    # Should not contain partially_supports in any context (docstrings, comments, code)
    assert "partially_supports" not in content, \
        "source_verifier.py should not contain 'partially_supports' anywhere"


def test_source_model_enum_uses_partial():
    # AC5 part: The vocabulary in `source_verifier.py` matches the `Source` model enum
    # in `app/models.py` — all use `"partial"`.
    assert "partial" in _SUPPORT_STATUS, \
        f"Source model enum should include 'partial'. Got: {_SUPPORT_STATUS}"
    assert "partially_supports" not in _SUPPORT_STATUS, \
        f"Source model enum should not include 'partially_supports'. Got: {_SUPPORT_STATUS}"


def test_js_chip_map_consistency():
    # AC5 part: Verify JS chip map in `app/static/js/cases.js` also uses `"partial"`.
    cases_js_file = os.path.join(REPO_ROOT, "app", "static", "js", "cases.js")
    with open(cases_js_file, "r") as f:
        content = f.read()

    # Look for the chip map definition and verify it uses "partial" not "partially_supports"
    assert "partial:" in content, \
        "cases.js should have a 'partial:' key in the chip map"
    # Ensure the chip map doesn't use partially_supports
    chip_section = re.search(r'(partial:\s*\{[^}]+\}|partial:\s*"[^"]*")', content)
    assert chip_section, "Could not find partial chip definition in cases.js"
    chip_text = chip_section.group(0)
    assert "partially_supports" not in chip_text, \
        "cases.js chip map should not reference 'partially_supports'"


def test_support_status_values_align():
    # AC5 part: All three artifacts use identical vocabulary for support status values.
    # source_verifier.py SUPPORT_STATUSES
    verifier_statuses = set(SUPPORT_STATUSES)
    # models.py _SUPPORT_STATUS
    model_statuses = set(_SUPPORT_STATUS)

    assert verifier_statuses == model_statuses, \
        f"SUPPORT_STATUSES mismatch:\n" \
        f"  source_verifier.py: {sorted(verifier_statuses)}\n" \
        f"  models.py: {sorted(model_statuses)}"


def test_verify_source_partial_direct_persistence(client):
    # AC4: Calling `verify_source()` directly and persisting the returned
    # `support_status` on a `Source` model instance does not raise a DB constraint
    # error for the partial-support case.
    #
    # This is a code-level test: simulate calling verify_source() with a mock
    # classify_fn that returns "partial", then verify the result can be persisted.
    from app.services.source_verifier import verify_source
    from app.models import Source, Session
    from sqlalchemy import create_engine

    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    from app.models import Base
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Mock classify function that returns "partial"
    def mock_classify(content, claim):
        return {
            "support_status": "partial",
            "support_rationale": "Mock partial support verdict"
        }

    # Call verify_source with the mock
    mock_source = {
        "url": "http://example.com",
        "claim": "Test claim",
        "kind": "article"
    }

    # Mock fetcher to return content
    from app.research.fetchers import ArticleReaderFetcher
    from app.research.types import Document

    class MockFetcher:
        def fetch(self, url):
            return Document(text="Sample content that supports the claim")

    result = verify_source(
        mock_source,
        article_fetcher=MockFetcher(),
        classify_fn=mock_classify
    )

    # Verify the result contains "partial"
    assert result["support_status"] == "partial", \
        f"verify_source should return 'partial'. Got: {result['support_status']}"

    # Now try to persist it on a Source model instance (this would fail if vocab mismatch)
    try:
        # Create a minimal source in the test DB
        from app.models import Plan, Case
        case = Case(id="case-1", raw_problem="Test", stage="sharpened")
        session.add(case)
        session.flush()

        plan = Plan(id="plan-1", case_id="case-1", label="A")
        session.add(plan)
        session.flush()

        source = Source(
            id="source-1",
            plan_id="plan-1",
            kind="article",
            support_status=result["support_status"],  # Should be "partial"
            support_rationale=result["support_rationale"]
        )
        session.add(source)
        session.commit()

        # Verify it persisted correctly
        fetched = session.query(Source).filter_by(id="source-1").first()
        assert fetched is not None, "Source should persist to database"
        assert fetched.support_status == "partial", \
            f"Persisted support_status should be 'partial'. Got: {fetched.support_status}"
    except Exception as e:
        pytest.fail(f"Failed to persist Source with 'partial' status: {e}")
    finally:
        session.close()
