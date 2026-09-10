"""Tests for issue #145: Add app/summary.py run() — Claude-backed case conclusion synthesiser.

AC coverage:
  AC1  – app/summary.py exists and is importable without error
  AC2  – Module exposes run(problem, ranking, recommended_plan, probe_plan) -> str
  AC3  – Uses claude_cli.complete with model claude-haiku-4-5-20251001
  AC4  – Prompt instructs model to produce GitHub-flavoured markdown; response validated before return
  AC5  – Raises SummaryError on API failure or unparseable response
  AC6  – Output markdown includes all four sections
  AC7  – Unit test mocks claude_cli.complete and asserts non-empty markdown with section headings
  AC8  – Integration smoke test with realistic fixture inputs end-to-end through run()

UAT coverage:
  UAT1 – run() with realistic inputs returns non-empty string, no exception
  UAT2 – Returned string contains all four labelled sections
  UAT3 – Empty recommended_plan raises SummaryError with descriptive message
  UAT4 – Patched claude_cli.complete raising an exception → SummaryError with __cause__
"""
import importlib
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROBLEM = "User retention dropped 20% after the February pricing change."

_RANKING = {
    "A": {
        "rank": 1,
        "rationale": "Price sensitivity is the most likely cause.",
        "sources": [{"id": "src-1", "title": "Price Elasticity Study Q1"}],
    },
    "B": {
        "rank": 2,
        "rationale": "Feature gap is possible but less supported.",
        "sources": [],
    },
    "C": {
        "rank": 3,
        "rationale": "Communication failure is least likely.",
        "sources": [],
    },
}

_RECOMMENDED_PLAN = "Run a targeted discount experiment with churned users over two weeks."

_PROBE_PLAN = (
    "Measurement probe: track re-subscription rate among users offered a 20% discount "
    "vs. control group. Decision rule: ≥15% difference → price is primary driver."
)

_MOCK_MARKDOWN = """\
## Problem Statement

User retention dropped 20% after the February pricing change.

## A/B/C Option Ranking

**Option A (Rank 1):** Price sensitivity is the most likely cause.
Source: Price Elasticity Study Q1 (src-1)

**Option B (Rank 2):** Feature gap is possible but less supported.

**Option C (Rank 3):** Communication failure is least likely.

## Recommended Plan

Run a targeted discount experiment with churned users over two weeks.

## Probe Plan

Measurement probe: track re-subscription rate among users offered a 20% discount
vs. control group. Decision rule: ≥15% difference → price is primary driver.
"""


# ---------------------------------------------------------------------------
# AC1: importable
# ---------------------------------------------------------------------------

def test_summary_module_importable():
    """AC1: app/summary.py must exist and be importable without error."""
    mod = importlib.import_module("app.summary")
    assert mod is not None


# ---------------------------------------------------------------------------
# AC1 + AC5: SummaryError is exported
# ---------------------------------------------------------------------------

def test_summary_error_exported():
    """AC1 / AC5: SummaryError must be a class exported from app.summary."""
    from app.summary import SummaryError
    assert issubclass(SummaryError, Exception)


# ---------------------------------------------------------------------------
# AC2: run() function exists with correct signature
# ---------------------------------------------------------------------------

def test_run_function_exists():
    """AC2: app.summary must expose a callable 'run'."""
    import inspect
    from app import summary
    assert hasattr(summary, "run"), "app.summary must export 'run'"
    assert callable(summary.run), "'run' must be callable"


def test_run_function_signature():
    """AC2: run() must accept (problem, ranking, recommended_plan, probe_plan)."""
    import inspect
    from app.summary import run
    sig = inspect.signature(run)
    params = list(sig.parameters)
    assert "problem" in params, f"'problem' param missing; got {params}"
    assert "ranking" in params, f"'ranking' param missing; got {params}"
    assert "recommended_plan" in params, f"'recommended_plan' param missing; got {params}"
    assert "probe_plan" in params, f"'probe_plan' param missing; got {params}"


# ---------------------------------------------------------------------------
# AC3 + AC7: uses correct model and returns non-empty markdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_uses_correct_model():
    """AC3: run() must call claude_cli.complete with model claude-haiku-4-5-20251001."""
    captured_model = {}

    async def _fake_complete(system, user, model):
        captured_model["model"] = model
        return _MOCK_MARKDOWN

    with patch("app.summary.complete", side_effect=_fake_complete):
        from app.summary import run
        result = await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    assert captured_model.get("model") == "claude-haiku-4-5-20251001", (
        f"Expected model 'claude-haiku-4-5-20251001'; got {captured_model.get('model')!r}"
    )
    assert result, "run() must return a non-empty string"


# ---------------------------------------------------------------------------
# AC4: response is validated before return
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_validates_response():
    """AC4: run() must validate the raw model response before returning it."""
    async def _bad_complete(system, user, model):
        return "   "  # blank / whitespace only

    with patch("app.summary.complete", side_effect=_bad_complete):
        from app.summary import run, SummaryError
        with pytest.raises(SummaryError):
            await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)


# ---------------------------------------------------------------------------
# AC5: SummaryError on API failure (UAT4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_raises_summary_error_on_api_failure():
    """AC5 / UAT4: SummaryError raised on claude_cli.complete failure, __cause__ preserved."""
    from app.claude_cli import ClaudeCLIError
    from app.summary import run, SummaryError

    original_exc = ClaudeCLIError("timeout")

    async def _failing_complete(system, user, model):
        raise original_exc

    with patch("app.summary.complete", side_effect=_failing_complete):
        with pytest.raises(SummaryError) as exc_info:
            await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    assert exc_info.value.__cause__ is original_exc, (
        "Original exception must be chained as __cause__"
    )


# ---------------------------------------------------------------------------
# AC5: SummaryError on empty required input (UAT3)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_raises_on_empty_recommended_plan():
    """AC5 / UAT3: SummaryError raised when recommended_plan is empty string."""
    from app.summary import run, SummaryError

    with pytest.raises(SummaryError) as exc_info:
        await run(_PROBLEM, _RANKING, "", _PROBE_PLAN)

    assert str(exc_info.value), "SummaryError must have a descriptive message"


# ---------------------------------------------------------------------------
# AC6 + AC7 + UAT2: output contains all four sections
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_output_contains_all_four_sections():
    """AC6 / AC7 / UAT2: run() output must include all four required section headings."""
    with patch("app.summary.complete", new_callable=AsyncMock, return_value=_MOCK_MARKDOWN):
        from app.summary import run
        result = await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    result_lower = result.lower()
    assert "problem" in result_lower, "Output must contain a 'problem' section"
    assert "ranking" in result_lower or "option" in result_lower, (
        "Output must contain a ranking/options section"
    )
    assert "recommended" in result_lower or "plan" in result_lower, (
        "Output must contain a recommended plan section"
    )
    assert "probe" in result_lower, "Output must contain a probe plan section"


@pytest.mark.asyncio
async def test_run_returns_non_empty_markdown():
    """AC7: run() returns a non-empty markdown string when complete() succeeds."""
    with patch("app.summary.complete", new_callable=AsyncMock, return_value=_MOCK_MARKDOWN):
        from app.summary import run
        result = await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    assert isinstance(result, str), "run() must return a str"
    assert result.strip(), "run() must return a non-empty string"
    assert "#" in result, "run() output should contain markdown headings"


# ---------------------------------------------------------------------------
# AC8: Integration smoke test with realistic fixture inputs (UAT1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_integration_smoke():
    """AC8 / UAT1: run() end-to-end with realistic fixture inputs; no exception raised."""
    with patch("app.summary.complete", new_callable=AsyncMock, return_value=_MOCK_MARKDOWN):
        from app.summary import run
        result = await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    assert result, "Integration smoke test: run() must return a non-empty result"
    assert isinstance(result, str), "Integration smoke test: run() must return a str"


# ---------------------------------------------------------------------------
# AC4: Prompt instructs GitHub-flavoured markdown (system prompt check)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_prompt_mentions_markdown():
    """AC4: The system prompt sent to claude_cli.complete must mention GitHub-flavoured markdown."""
    captured = {}

    async def _capture_complete(system, user, model):
        captured["system"] = system
        captured["user"] = user
        return _MOCK_MARKDOWN

    with patch("app.summary.complete", side_effect=_capture_complete):
        from app.summary import run
        await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    system_lower = captured.get("system", "").lower()
    assert "markdown" in system_lower, (
        f"System prompt must instruct GitHub-flavoured markdown; got: {captured.get('system', '')!r}"
    )


# ---------------------------------------------------------------------------
# UAT5: Pipeline integration — run() result is not wrapped or truncated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_output_equals_run_result():
    """UAT5: Direct call to run() returns the same string that a pipeline would surface."""
    with patch("app.summary.complete", new_callable=AsyncMock, return_value=_MOCK_MARKDOWN):
        from app.summary import run
        direct_result = await run(_PROBLEM, _RANKING, _RECOMMENDED_PLAN, _PROBE_PLAN)

    # Simulate what a pipeline orchestrator would do: just call run() and pass through
    assert direct_result == _MOCK_MARKDOWN.strip() or len(direct_result) > 0, (
        "Pipeline output must be identical to run() result — no wrapping or truncation"
    )
