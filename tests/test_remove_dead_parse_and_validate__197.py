"""Tests for issue #197: Remove dead _parse_and_validate string-parsing function.

Context: generate_summary() was refactored to use structured output via call_stage(),
so the old fenced-JSON string parsing path has no callers and is dead code.
"""
import importlib
import pytest
import app.summary as summary_module


class TestDeadCodeRemoved:
    """Verify the dead string-parsing function is gone from app.summary."""

    def test_parse_and_validate_not_in_module(self):
        # AC: _parse_and_validate (old name) must not exist — removed as dead code after
        # structured-output refactoring in issue #190
        assert not hasattr(summary_module, "_parse_and_validate"), (
            "_parse_and_validate is dead code and must be removed from app/summary.py"
        )

    def test_parse_literature_review_not_in_module(self):
        # AC: _parse_literature_review is the string-based parse path renamed in sprint-58;
        # it still has no callers after the structured-output refactoring and must be removed.
        assert not hasattr(summary_module, "_parse_literature_review"), (
            "_parse_literature_review is a dead string-parsing function with no callers "
            "in app/ and must be removed from app/summary.py"
        )

    def test_validate_literature_review_dict_still_present(self):
        # Regression guard: _validate_literature_review_dict IS used by generate_summary()
        # and must NOT be removed.
        assert hasattr(summary_module, "_validate_literature_review_dict"), (
            "_validate_literature_review_dict is still called by generate_summary() "
            "and must not be removed"
        )
