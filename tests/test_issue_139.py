"""Tests for issue #139: Add explicit comment for rationale None handling in cases.py.

AC coverage:
  AC1 – Line with plan.rationale assignment has an inline comment.
  AC2 – Comment is on or immediately above the assignment line.
  AC3 – Existing logic (item.get("rationale") or None) is unchanged.
  AC4 – Comment attributes source (Weigh) and intent (treat empty string as NULL).
"""
import pathlib


CASES_PY = pathlib.Path(__file__).parent.parent / "app" / "routers" / "cases.py"
ASSIGNMENT = 'plan.rationale = item.get("rationale") or None'


def _find_assignment_line(lines):
    for i, line in enumerate(lines):
        if ASSIGNMENT in line:
            return i
    return None


def test_assignment_logic_unchanged():
    """AC3: The exact assignment expression must still be present."""
    text = CASES_PY.read_text()
    assert ASSIGNMENT in text, (
        f"cases.py must still contain: {ASSIGNMENT!r}"
    )


def test_comment_present_on_assignment_line():
    """AC1 + AC2: A comment (#) must appear on the same line as the assignment."""
    lines = CASES_PY.read_text().splitlines()
    idx = _find_assignment_line(lines)
    assert idx is not None, f"Could not find assignment line in cases.py"
    line = lines[idx]
    assert "#" in line, (
        "The rationale assignment line must have an inline comment explaining "
        "the empty-string-to-None conversion"
    )


def test_comment_mentions_weigh():
    """AC4: Comment must attribute the source (Weigh)."""
    lines = CASES_PY.read_text().splitlines()
    idx = _find_assignment_line(lines)
    assert idx is not None
    # Check the assignment line and the line immediately above
    window = lines[max(0, idx - 1): idx + 1]
    combined = " ".join(window).lower()
    assert "weigh" in combined, (
        "Comment near rationale assignment must mention 'Weigh' as the source"
    )


def test_comment_mentions_null_intent():
    """AC4: Comment must state intent (treat empty as NULL/None)."""
    lines = CASES_PY.read_text().splitlines()
    idx = _find_assignment_line(lines)
    assert idx is not None
    window = lines[max(0, idx - 1): idx + 1]
    combined = " ".join(window).lower()
    assert "null" in combined or "none" in combined or "empty" in combined, (
        "Comment near rationale assignment must state the intent "
        "(treat empty string as NULL/None)"
    )
