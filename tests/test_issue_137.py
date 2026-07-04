"""Tests for issue #137: Consolidate rationale validation in weigh.py.

AC coverage:
  AC1 – single consolidated validation block (not two separate checks for presence + content)
  AC2 – plan with missing rationale field is rejected with a single, clear error message
  AC3 – plan with {"rationale": ""} rejected with the SAME error message as missing field
  AC4 – plan with {"rationale": "   "} (whitespace-only) is rejected
  AC5 – plan with non-empty rationale string passes validation
  AC6 – no functional behavior change: valid plans still pass; invalid plans still fail
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


_PLAN_A = {"label": "A", "name": "Plan Alpha", "mechanism": "Mechanism A"}
_PLANS = [_PLAN_A]


def _make_result(rationale_value):
    """Build a single-plan result with the given rationale value (use _MISSING to omit key)."""
    item = {"label": "A", "rank": 1, "standing": None}
    if rationale_value is not _MISSING:
        item["rationale"] = rationale_value
    return [item]


_MISSING = object()  # sentinel: omit the rationale key entirely


# ---------------------------------------------------------------------------
# AC2: missing rationale key → rejected with a clear error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_rationale_key_raises():
    """AC2: plan with no 'rationale' key is rejected."""
    from app.weigh import rerank_plans, WeighError

    result = _make_result(_MISSING)
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result)):
        with pytest.raises(WeighError):
            await rerank_plans("problem", _PLANS, None)


# ---------------------------------------------------------------------------
# AC3: {"rationale": ""} → same error message as missing field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_string_rationale_same_error_as_missing():
    """AC3: empty-string rationale produces the same error message as a missing rationale key."""
    from app.weigh import rerank_plans, WeighError

    result_missing = _make_result(_MISSING)
    result_empty = _make_result("")

    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result_missing)):
        with pytest.raises(WeighError) as exc_missing:
            await rerank_plans("problem", _PLANS, None)

    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result_empty)):
        with pytest.raises(WeighError) as exc_empty:
            await rerank_plans("problem", _PLANS, None)

    assert str(exc_missing.value) == str(exc_empty.value), (
        f"Expected same error for missing vs empty rationale.\n"
        f"  missing: {exc_missing.value!r}\n"
        f"  empty:   {exc_empty.value!r}"
    )


# ---------------------------------------------------------------------------
# AC4: {"rationale": "   "} whitespace-only → rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whitespace_rationale_raises():
    """AC4: whitespace-only rationale is rejected (strip applied before check)."""
    from app.weigh import rerank_plans, WeighError

    result = _make_result("   ")
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result)):
        with pytest.raises(WeighError):
            await rerank_plans("problem", _PLANS, None)


# ---------------------------------------------------------------------------
# AC5: non-empty rationale passes validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_rationale_passes():
    """AC5: plan with a non-empty rationale string passes validation without error."""
    from app.weigh import rerank_plans

    result = _make_result("Because mechanism A is strongly supported by source X.")
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result)):
        output = await rerank_plans("problem", _PLANS, None)

    assert len(output) == 1
    assert output[0]["rationale"] == "Because mechanism A is strongly supported by source X."


# ---------------------------------------------------------------------------
# AC6: valid multi-plan result still works; plan without rationale still rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_plan_valid_result_passes():
    """AC6: valid plans that previously passed still pass."""
    from app.weigh import rerank_plans

    plans = [
        {"label": "A", "name": "Plan Alpha", "mechanism": "Mechanism A"},
        {"label": "B", "name": "Plan Beta", "mechanism": "Mechanism B"},
    ]
    result = [
        {"label": "A", "rank": 1, "standing": "ruled-in",
         "rationale": "Strong evidence from source X."},
        {"label": "B", "rank": 2, "standing": None,
         "rationale": "Weak correlation per document Y."},
    ]

    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result)):
        output = await rerank_plans("problem", plans, "some context")

    assert len(output) == 2
    labels = {item["label"] for item in output}
    assert labels == {"A", "B"}


@pytest.mark.asyncio
async def test_plan_missing_other_required_field_still_rejected():
    """AC6: invalid plans that previously failed still fail (e.g. missing 'rank')."""
    from app.weigh import rerank_plans, WeighError

    result = [{"label": "A", "standing": None, "rationale": "Good rationale."}]  # missing rank
    with patch("app.weigh.complete", new_callable=AsyncMock, return_value=json.dumps(result)):
        with pytest.raises(WeighError):
            await rerank_plans("problem", _PLANS, None)
