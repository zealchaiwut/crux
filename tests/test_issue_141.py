"""Tests for issue #141: Improve PlanCard rationale comment in cases.js.

AC coverage:
  AC1 – The comment reads exactly: {/* Rationale: shown only when non-empty to avoid empty containers */}
  AC2 – No other code in the file is modified — only the comment text changes.
  AC3 – The updated comment is syntactically valid JSX (no broken braces or delimiters).
"""
import pathlib

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"

EXPECTED_COMMENT = "{/* Rationale: shown only when non-empty to avoid empty containers */}"
OLD_COMMENT = "{/* Rationale — shown only when non-empty */}"


def test_new_comment_present():
    """AC1: The exact updated comment text must be present in cases.js."""
    text = CASES_JS.read_text()
    assert EXPECTED_COMMENT in text, (
        f"cases.js must contain the updated comment: {EXPECTED_COMMENT!r}"
    )


def test_old_comment_absent():
    """AC1: The old comment text must no longer appear in cases.js."""
    text = CASES_JS.read_text()
    assert OLD_COMMENT not in text, (
        f"cases.js must not contain the old comment: {OLD_COMMENT!r}"
    )


def test_comment_is_valid_jsx_delimiters():
    """AC3: The comment must open with {{/* and close with */}} — no broken braces."""
    text = CASES_JS.read_text()
    assert EXPECTED_COMMENT in text
    # The comment must start with {/* and end with */}
    assert EXPECTED_COMMENT.startswith("{/*"), "Comment must open with {/*"
    assert EXPECTED_COMMENT.endswith("*/}"), "Comment must close with */}"
