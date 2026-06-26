"""Tests for issue #131: Add rationale field to Weigh plan output.

AC coverage:
  AC1 – _SYSTEM prompt instructs model to include a "rationale" field on every plan object
  AC2 – rationale value is 1–2 sentences explaining rank position
  AC3 – rationale explicitly references gathered sources where relevant
  AC4 – rerank_plans raises a clear error if any plan object is missing the "rationale" field
  AC5 – rerank_plans raises a clear error if rationale is present but empty or blank
  AC6 – Existing plan fields (rank, score, etc.) are unaffected
  AC7 – Unit tests cover happy path and two failure paths (missing field, blank value)
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# AC1: _SYSTEM prompt contains "rationale" instruction
# ---------------------------------------------------------------------------

def test_system_prompt_mentions_rationale():
    """AC1: _SYSTEM prompt must instruct the model to include a 'rationale' field."""
    from app.weigh import _SYSTEM
    assert "rationale" in _SYSTEM, "_SYSTEM prompt must mention the 'rationale' field"


def test_system_prompt_describes_rationale_content():
    """AC2/AC3: _SYSTEM prompt must describe what rationale contains (sentences + sources)."""
    from app.weigh import _SYSTEM
    # Should mention sentence count or explanation, and source references
    lower = _SYSTEM.lower()
    assert "sentence" in lower or "explain" in lower or "reason" in lower, \
        "_SYSTEM prompt must describe rationale content (sentences/explanation)"
    assert "source" in lower or "reference" in lower or "cite" in lower or "document" in lower, \
        "_SYSTEM prompt must instruct rationale to reference gathered sources"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLANS = [
    {"label": "A", "name": "Plan Alpha", "mechanism": "Mechanism A"},
    {"label": "B", "name": "Plan Beta", "mechanism": "Mechanism B"},
]

_VALID_RESULT = [
    {
        "label": "A",
        "rank": 1,
        "standing": "ruled-in",
        "rationale": "Plan A ranks first because source X shows strong evidence for mechanism A.",
    },
    {
        "label": "B",
        "rank": 2,
        "standing": None,
        "rationale": "Plan B ranks second; document Y suggests mechanism B is less likely here.",
    },
]

_RESULT_MISSING_RATIONALE = [
    {"label": "A", "rank": 1, "standing": None},
    {"label": "B", "rank": 2, "standing": None},
]

_RESULT_BLANK_RATIONALE = [
    {"label": "A", "rank": 1, "standing": None, "rationale": ""},
    {"label": "B", "rank": 2, "standing": None, "rationale": "Valid rationale citing source Z."},
]

_RESULT_WHITESPACE_RATIONALE = [
    {"label": "A", "rank": 1, "standing": None, "rationale": "   "},
    {"label": "B", "rank": 2, "standing": None, "rationale": "Valid rationale citing source Z."},
]


# ---------------------------------------------------------------------------
# AC7 happy path: valid rationale passes validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_plans_accepts_valid_rationale():
    """AC7 happy path: rerank_plans returns plans when rationale is present and non-empty."""
    from app.weigh import rerank_plans

    with patch("app.weigh.complete", new_callable=AsyncMock,
               return_value=json.dumps(_VALID_RESULT)):
        result = await rerank_plans("sharpened problem", _PLANS, "some context")

    assert len(result) == 2
    for item in result:
        assert "rationale" in item, f"rationale missing from item: {item}"
        assert item["rationale"].strip(), f"rationale must not be blank: {item}"


# ---------------------------------------------------------------------------
# AC4: missing rationale field raises error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_plans_raises_on_missing_rationale():
    """AC4: rerank_plans raises WeighError (or ValueError) when rationale field is absent."""
    from app.weigh import rerank_plans, WeighError

    with patch("app.weigh.complete", new_callable=AsyncMock,
               return_value=json.dumps(_RESULT_MISSING_RATIONALE)):
        with pytest.raises((WeighError, ValueError)):
            await rerank_plans("sharpened problem", _PLANS, "some context")


# ---------------------------------------------------------------------------
# AC5: blank rationale raises error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_plans_raises_on_blank_rationale():
    """AC5: rerank_plans raises WeighError (or ValueError) when rationale is empty string."""
    from app.weigh import rerank_plans, WeighError

    with patch("app.weigh.complete", new_callable=AsyncMock,
               return_value=json.dumps(_RESULT_BLANK_RATIONALE)):
        with pytest.raises((WeighError, ValueError)):
            await rerank_plans("sharpened problem", _PLANS, "some context")


@pytest.mark.asyncio
async def test_rerank_plans_raises_on_whitespace_rationale():
    """AC5: rerank_plans raises WeighError (or ValueError) when rationale is whitespace-only."""
    from app.weigh import rerank_plans, WeighError

    with patch("app.weigh.complete", new_callable=AsyncMock,
               return_value=json.dumps(_RESULT_WHITESPACE_RATIONALE)):
        with pytest.raises((WeighError, ValueError)):
            await rerank_plans("sharpened problem", _PLANS, "some context")


# ---------------------------------------------------------------------------
# AC6: existing fields are unaffected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_plans_existing_fields_intact():
    """AC6: label, rank, and standing fields are still present and valid in output."""
    from app.weigh import rerank_plans

    with patch("app.weigh.complete", new_callable=AsyncMock,
               return_value=json.dumps(_VALID_RESULT)):
        result = await rerank_plans("sharpened problem", _PLANS, "some context")

    for item in result:
        assert "label" in item, f"label missing: {item}"
        assert "rank" in item, f"rank missing: {item}"
        assert "standing" in item, f"standing missing: {item}"
        assert isinstance(item["rank"], int) and item["rank"] >= 1, f"invalid rank: {item}"
