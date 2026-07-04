"""Tests for issue #125: Add clarifying comment to _STAGE_ORDER definition.

The suggestion: add an inline comment near `_STAGE_ORDER` in
app/routers/cases.py explaining that it is retained as a legacy
fallback/UI mapping but is no longer used in API response serialization
(since #75 changed the stage field to return a string enum value).

AC: A human-readable comment must appear adjacent to the _STAGE_ORDER
    definition that explains its retained purpose.
"""
import ast
import inspect
import pathlib


CASES_PY = pathlib.Path(__file__).parent.parent / "app" / "routers" / "cases.py"


def _lines_around_stage_order(source: str, window: int = 6) -> list[str]:
    """Return lines surrounding the _STAGE_ORDER assignment."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if "_STAGE_ORDER" in line and "=" in line:
            start = max(0, i - 2)
            end = min(len(lines), i + window)
            return lines[start:end]
    return []


def test_stage_order_comment_present():
    """AC: A comment must appear near the _STAGE_ORDER definition explaining
    why it is retained (legacy fallback, not used in API serialization)."""
    source = CASES_PY.read_text()
    surrounding = "\n".join(_lines_around_stage_order(source))
    assert surrounding, "_STAGE_ORDER definition not found in cases.py"

    # A comment must exist within a few lines of the definition.
    assert "#" in surrounding, (
        "No inline comment found near _STAGE_ORDER definition. "
        "Add a comment explaining it is kept for legacy fallback/UI mapping "
        "but is no longer used in API response serialization."
    )


def test_stage_order_comment_mentions_legacy_or_fallback():
    """AC: The comment should mention the retention reason (legacy/fallback/UI mapping)."""
    source = CASES_PY.read_text()
    surrounding = "\n".join(_lines_around_stage_order(source))
    lower = surrounding.lower()
    has_reason = any(word in lower for word in ["legacy", "fallback", "ui", "mapping", "serializ"])
    assert has_reason, (
        "Comment near _STAGE_ORDER does not mention the reason for retaining it. "
        "Include at least one of: legacy, fallback, UI, mapping, or serialization."
    )


def test_stage_order_dict_unchanged():
    """Sanity: _STAGE_ORDER dict values must remain correct after the comment addition."""
    from app.routers.cases import _STAGE_ORDER  # noqa: PLC0415

    expected = {
        "sharpened": 0,
        "bake_off": 1,
        "gather": 2,
        "weigh": 3,
        "probe": 4,
        "verdict": 5,
    }
    assert _STAGE_ORDER == expected, (
        f"_STAGE_ORDER values changed unexpectedly: {_STAGE_ORDER!r}"
    )
