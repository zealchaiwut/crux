"""Tests for issue #138: Clarify rationale content requirements in weigh.py prompt.

AC coverage:
  AC1 – _SYSTEM prompt and rationale validation are consistent (both non-empty only, or both 1–2 sentences).
  AC2 – If prompt-relaxation path: "1–2 sentences" wording removed; non-empty language used instead.
  AC3 – (N/A for this path — validation-addition path not chosen.)
  AC4 – A comment/docstring at the validation site documents the chosen policy.
  AC5 – No existing passing tests are broken.
"""
import re


# ---------------------------------------------------------------------------
# AC1 + AC2: prompt-relaxation path chosen — "1–2 sentence" wording removed
# ---------------------------------------------------------------------------

def test_system_prompt_does_not_enforce_sentence_count():
    """AC2: _SYSTEM prompt must NOT contain '1–2 sentence' or '1-2 sentence' length constraint."""
    from app.weigh import _SYSTEM
    lower = _SYSTEM.lower()
    # Neither dash form nor en-dash form should appear
    assert "1–2 sentence" not in lower, (
        "_SYSTEM prompt must not contain '1–2 sentence' — chosen policy is non-empty only"
    )
    assert "1-2 sentence" not in lower, (
        "_SYSTEM prompt must not contain '1-2 sentence' — chosen policy is non-empty only"
    )


def test_system_prompt_requires_non_empty_rationale():
    """AC1: _SYSTEM prompt must still require non-empty rationale text."""
    from app.weigh import _SYSTEM
    lower = _SYSTEM.lower()
    # Should still describe rationale as required/non-empty
    assert "rationale" in lower, "_SYSTEM prompt must still mention 'rationale'"
    assert (
        "non-empty" in lower
        or "not be empty" in lower
        or "required" in lower
        or "must not" in lower
    ), "_SYSTEM prompt must indicate that rationale is required / non-empty"


def test_system_prompt_still_describes_rationale_purpose():
    """AC1: _SYSTEM prompt must still explain what rationale should say."""
    from app.weigh import _SYSTEM
    lower = _SYSTEM.lower()
    assert (
        "explain" in lower
        or "reason" in lower
        or "justif" in lower
        or "why" in lower
    ), "_SYSTEM prompt must still describe what rationale should explain"


# ---------------------------------------------------------------------------
# AC1: validation still rejects empty / whitespace rationale
# ---------------------------------------------------------------------------

def test_validation_rejects_empty_rationale():
    """AC1: rerank_plans validation must still reject an empty rationale string."""
    import json
    from unittest.mock import AsyncMock, patch
    import pytest
    import asyncio
    from app.weigh import rerank_plans, WeighError

    bad_result = [
        {"label": "A", "rank": 1, "standing": None, "rationale": ""},
        {"label": "B", "rank": 2, "standing": None, "rationale": "Valid reason."},
    ]
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
    ]

    async def run():
        with patch("app.weigh.complete", new_callable=AsyncMock,
                   return_value=json.dumps(bad_result)):
            with pytest.raises((WeighError, ValueError)):
                await rerank_plans("problem", plans, "context")

    asyncio.run(run())


def test_validation_rejects_whitespace_rationale():
    """AC1: rerank_plans validation must still reject a whitespace-only rationale string."""
    import json
    from unittest.mock import AsyncMock, patch
    import pytest
    import asyncio
    from app.weigh import rerank_plans, WeighError

    bad_result = [
        {"label": "A", "rank": 1, "standing": None, "rationale": "   "},
        {"label": "B", "rank": 2, "standing": None, "rationale": "Valid reason."},
    ]
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
    ]

    async def run():
        with patch("app.weigh.complete", new_callable=AsyncMock,
                   return_value=json.dumps(bad_result)):
            with pytest.raises((WeighError, ValueError)):
                await rerank_plans("problem", plans, "context")

    asyncio.run(run())


def test_validation_accepts_single_word_rationale():
    """AC2 (non-empty policy): a single-word rationale must be accepted under the relaxed policy."""
    import json
    from unittest.mock import AsyncMock, patch
    import asyncio
    from app.weigh import rerank_plans

    single_word_result = [
        {"label": "A", "rank": 1, "standing": None, "rationale": "ok"},
        {"label": "B", "rank": 2, "standing": None, "rationale": "unlikely"},
    ]
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
    ]

    async def run():
        with patch("app.weigh.complete", new_callable=AsyncMock,
                   return_value=json.dumps(single_word_result)):
            result = await rerank_plans("problem", plans, "context")
        assert len(result) == 2
        assert result[0]["rationale"] == "ok"

    asyncio.run(run())


def test_validation_accepts_multi_sentence_rationale():
    """AC1: a 1–2 sentence rationale must still be accepted under both policies."""
    import json
    from unittest.mock import AsyncMock, patch
    import asyncio
    from app.weigh import rerank_plans

    good_result = [
        {
            "label": "A",
            "rank": 1,
            "standing": "ruled-in",
            "rationale": "This option scores highest on cost. It also meets the deadline.",
        },
        {
            "label": "B",
            "rank": 2,
            "standing": None,
            "rationale": "Plan B is less likely given source Y.",
        },
    ]
    plans = [
        {"label": "A", "name": "Plan A", "mechanism": "Mech A"},
        {"label": "B", "name": "Plan B", "mechanism": "Mech B"},
    ]

    async def run():
        with patch("app.weigh.complete", new_callable=AsyncMock,
                   return_value=json.dumps(good_result)):
            result = await rerank_plans("problem", plans, "context")
        assert len(result) == 2

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC4: validation site has a comment documenting the policy
# ---------------------------------------------------------------------------

def test_validation_site_has_policy_comment():
    """AC4: The validation code in weigh.py must have a comment documenting the rationale policy."""
    import pathlib
    source = pathlib.Path(__file__).parent.parent / "app" / "weigh.py"
    text = source.read_text()

    # Find the rationale validation block
    val_idx = text.find("rationale")
    assert val_idx != -1, "weigh.py must contain rationale validation"

    # There must be a comment near the validation that mentions the policy
    # Look in a window of ~20 lines around the validation
    lines = text.splitlines()
    val_line = next(
        (i for i, l in enumerate(lines) if "rationale" in l and "strip" in l),
        None,
    )
    assert val_line is not None, "weigh.py must have rationale non-empty check (line with rationale + .strip())"

    # Check for a comment (# ...) within 10 lines above or on same line
    window = lines[max(0, val_line - 10): val_line + 3]
    comment_lines = [l for l in window if "#" in l]
    assert comment_lines, (
        "A comment must appear near the rationale validation in weigh.py "
        "documenting which policy is in effect (non-empty only vs sentence-count)"
    )

    # The comment must mention the policy decision
    combined = " ".join(comment_lines).lower()
    assert (
        "non-empty" in combined
        or "not empty" in combined
        or "policy" in combined
        or "sentence" in combined
        or "any text" in combined
        or "no length" in combined
        or "no sentence" in combined
    ), (
        "The comment near rationale validation must state the policy "
        "(e.g. 'non-empty only', 'no sentence-count constraint', etc.)"
    )
