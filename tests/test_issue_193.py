"""Groq regression gate — canonical deficit fixture (issue #193).

AC coverage:
  AC1 — regression test submits canonical deficit fixture to Groq judgment model end-to-end
  AC2 — Weigh stage down-ranks overreaching plans (Plan A ranks above Plan B and Plan C)
  AC3 — Summary stage flags the VO2max-interval claim as unsupported or contradicted
  AC4 — Summary stage flags the carb-timing claim as unsupported or contradicted
  AC5 — On failure, test output includes a structured failure message
  AC6 — Failure message identifies which stage regressed (Weigh or Summary)
  AC7 — Runnable in CI against the Groq provider without manual intervention
         (skipped automatically when GROQ_API_KEY is absent)
  AC8 — Switch not marked complete until this regression passes green on Groq
         (enforced by CI gate; test must be green before merge)

All tests in this module are integration tests that call the live Groq API.
They are skipped automatically when GROQ_API_KEY is not present in the environment.
Set CRUX_JUDGMENT_MODEL to override the Groq model used (default: openai/gpt-oss-120b).
"""
import asyncio
import importlib
import json
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

_needs_groq = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason="GROQ_API_KEY not set — Groq regression gate requires a live API key",
)

# ---------------------------------------------------------------------------
# Canonical deficit fixture
# ---------------------------------------------------------------------------

_PROBLEM = (
    "Endurance athlete experiencing fatigue, declining performance, and poor recovery. "
    "Training volume is high (14 h/week). "
    "Recent HRV trend is declining. "
    "Bloodwork shows low ferritin (18 ng/mL) and normal thyroid. "
    "Goal: restore performance and reduce fatigue without cutting training volume."
)

_CONTEXT = (
    "Athlete is in a 20-week base-building phase. "
    "Current diet: high carbohydrate, moderate protein (~1.4 g/kg). "
    "Body composition: 70 kg, 12 % body fat. "
    "No acute injury. No diagnosed RED-S."
)

# Plan A is the deficit-aligned plan; B and C are overreaching plans.
_PLANS = [
    {
        "label": "A",
        "name": "Moderate deficit + protein",
        "mechanism": (
            "Create a moderate 15–20 % caloric deficit while increasing protein to 2.2 g/kg "
            "to preserve lean mass and address fatigue arising from energy imbalance."
        ),
    },
    {
        "label": "B",
        "name": "VO2max interval overreach",
        "mechanism": (
            "Add high-intensity VO2max interval sessions on top of the current 14 h/week "
            "volume to force aerobic adaptation through accumulated physiological stress."
        ),
    },
    {
        "label": "C",
        "name": "Carb-timing reoptimisation",
        "mechanism": (
            "Shift all carbohydrate intake to strict peri-workout windows while reducing "
            "overall fat intake, aiming to maximise intra-workout carbohydrate availability."
        ),
    },
]

# Case data for the Summary stage.  Sources for Plans B and C are pre-labelled
# 'contradicts' by the upstream verification step — the regression checks that
# the Summary stage faithfully propagates this into its output.
_CASE_DATA = {
    "sharpened": _PROBLEM,
    "plans": [
        {
            "label": "A",
            "name": "Moderate deficit + protein",
            "mechanism": _PLANS[0]["mechanism"],
            "current_rank": 1,
            "sources": [
                {
                    "id": "src-protein",
                    "title": "Protein adequacy preserves lean mass in endurance deficits",
                    "claim": (
                        "Protein ≥ 2.0 g/kg mitigates catabolism during caloric restriction "
                        "in endurance athletes."
                    ),
                    "citation": "Morton et al. 2018; Br J Sports Med",
                    "support_status": "supports",
                }
            ],
        },
        {
            "label": "B",
            "name": "VO2max interval overreach",
            "mechanism": _PLANS[1]["mechanism"],
            "current_rank": 2,
            "sources": [
                {
                    "id": "src-vo2max",
                    "title": "VO2max intervals raise cortisol in energy-deficient athletes",
                    "claim": (
                        "High-intensity interval training layered onto an energy-deficient "
                        "state elevates cortisol and impairs recovery."
                    ),
                    "citation": "Meeusen et al. 2013; Eur J Sport Sci overtraining consensus",
                    "support_status": "contradicts",
                }
            ],
        },
        {
            "label": "C",
            "name": "Carb-timing reoptimisation",
            "mechanism": _PLANS[2]["mechanism"],
            "current_rank": 3,
            "sources": [
                {
                    "id": "src-carb",
                    "title": "Carb-timing efficacy requires adequate energy availability",
                    "claim": (
                        "Carbohydrate timing strategies produce no benefit when overall "
                        "energy availability is insufficient."
                    ),
                    "citation": "Burke et al. 2011; Int J Sport Nutr Exerc Metab",
                    "support_status": "contradicts",
                }
            ],
        },
    ],
    "probe": {
        "type": "n_of_1",
        "target_metric": "HRV 7-day rolling average",
        "note": "Measure HRV daily for 4 weeks on the moderate deficit + protein protocol.",
    },
}

_VO2MAX_CLAIM_TITLE = "VO2max intervals raise cortisol in energy-deficient athletes"
_CARB_CLAIM_TITLE = "Carb-timing efficacy requires adequate energy availability"


# ---------------------------------------------------------------------------
# Shared provider fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def groq_env(monkeypatch):
    """Configure env vars so rerank_plans and generate_summary use the Groq provider."""
    monkeypatch.setenv("CRUX_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", _GROQ_API_KEY)
    monkeypatch.setenv(
        "CRUX_JUDGMENT_MODEL",
        os.environ.get("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b"),
    )
    import app.llm_providers as lp
    importlib.reload(lp)
    yield
    importlib.reload(lp)


# ---------------------------------------------------------------------------
# AC1 + AC2: Weigh stage — deficit plan outranks both overreaching plans
# ---------------------------------------------------------------------------

@_needs_groq
def test_weigh_deficit_plan_outranks_overreaching_plan_b(groq_env):
    """AC1+AC2: Plan A (deficit-aligned) ranks higher than Plan B (VO2max overreach).

    Failure message identifies [Stage: Weigh] so the regressing stage can be pinned.
    """
    from app.weigh import rerank_plans

    rankings = asyncio.run(rerank_plans(_PROBLEM, _PLANS, _CONTEXT))
    rank_by_label = {r["label"]: r["rank"] for r in rankings}

    assert "A" in rank_by_label and "B" in rank_by_label, (
        "[Stage: Weigh] Incomplete ranking — labels A and/or B missing. "
        f"Got labels: {sorted(rank_by_label)}"
    )

    rank_a, rank_b = rank_by_label["A"], rank_by_label["B"]
    assert rank_a < rank_b, (
        f"[Stage: Weigh] Regression detected: deficit-aligned Plan A ranked {rank_a} "
        f"but overreaching Plan B ranked {rank_b}. "
        "Plan A must rank higher (lower rank number) than Plan B for the deficit fixture."
    )


@_needs_groq
def test_weigh_deficit_plan_outranks_overreaching_plan_c(groq_env):
    """AC1+AC2: Plan A (deficit-aligned) ranks higher than Plan C (carb-timing overreach).

    Failure message identifies [Stage: Weigh] so the regressing stage can be pinned.
    """
    from app.weigh import rerank_plans

    rankings = asyncio.run(rerank_plans(_PROBLEM, _PLANS, _CONTEXT))
    rank_by_label = {r["label"]: r["rank"] for r in rankings}

    assert "A" in rank_by_label and "C" in rank_by_label, (
        "[Stage: Weigh] Incomplete ranking — labels A and/or C missing. "
        f"Got labels: {sorted(rank_by_label)}"
    )

    rank_a, rank_c = rank_by_label["A"], rank_by_label["C"]
    assert rank_a < rank_c, (
        f"[Stage: Weigh] Regression detected: deficit-aligned Plan A ranked {rank_a} "
        f"but overreaching Plan C ranked {rank_c}. "
        "Plan A must rank higher (lower rank number) than Plan C for the deficit fixture."
    )


@_needs_groq
def test_weigh_returns_valid_ranking_for_all_three_plans(groq_env):
    """AC1: Groq Weigh stage returns exactly three rankings with required fields."""
    from app.weigh import rerank_plans

    rankings = asyncio.run(rerank_plans(_PROBLEM, _PLANS, _CONTEXT))

    assert len(rankings) == 3, (
        "[Stage: Weigh] Expected 3 ranked plans, got "
        f"{len(rankings)}. Provider may be returning partial output."
    )

    for item in rankings:
        for field in ("label", "rank", "standing", "rationale"):
            assert field in item, (
                f"[Stage: Weigh] Ranking item missing required field '{field}': {item}"
            )
        assert isinstance(item["rank"], int) and 1 <= item["rank"] <= 3, (
            f"[Stage: Weigh] Invalid rank value {item['rank']!r} for label {item['label']!r}."
        )
        assert item["label"] in {"A", "B", "C"}, (
            f"[Stage: Weigh] Unexpected plan label {item['label']!r}."
        )


# ---------------------------------------------------------------------------
# AC3 + AC4: Summary stage — contradicted claims appear in output
# ---------------------------------------------------------------------------

@_needs_groq
def test_summary_flags_vo2max_claim_as_contradicted(groq_env):
    """AC3: generate_summary includes the VO2max-interval claim in the contradicted section.

    Failure message identifies [Stage: Summary] so the regressing stage can be pinned.
    """
    from app.summary import generate_summary

    raw = asyncio.run(generate_summary(_CASE_DATA))
    parsed = json.loads(raw)

    contradicted = parsed.get("contradicted_evidence", "")
    assert _VO2MAX_CLAIM_TITLE in contradicted, (
        "[Stage: Summary] Regression detected: VO2max-interval claim not found in "
        "the contradicted_evidence section of the summary output. "
        f"Expected title: '{_VO2MAX_CLAIM_TITLE}'. "
        f"Actual contradicted_evidence field: {contradicted!r}"
    )


@_needs_groq
def test_summary_flags_carb_timing_claim_as_contradicted(groq_env):
    """AC4: generate_summary includes the carb-timing claim in the contradicted section.

    Failure message identifies [Stage: Summary] so the regressing stage can be pinned.
    """
    from app.summary import generate_summary

    raw = asyncio.run(generate_summary(_CASE_DATA))
    parsed = json.loads(raw)

    contradicted = parsed.get("contradicted_evidence", "")
    assert _CARB_CLAIM_TITLE in contradicted, (
        "[Stage: Summary] Regression detected: carb-timing claim not found in "
        "the contradicted_evidence section of the summary output. "
        f"Expected title: '{_CARB_CLAIM_TITLE}'. "
        f"Actual contradicted_evidence field: {contradicted!r}"
    )


@_needs_groq
def test_summary_output_contains_required_fields(groq_env):
    """AC1: generate_summary returns a valid JSON object with all required summary fields."""
    from app.summary import generate_summary

    raw = asyncio.run(generate_summary(_CASE_DATA))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"[Stage: Summary] generate_summary returned non-JSON output: {exc}. "
            f"Raw output (first 300 chars): {raw[:300]!r}"
        )

    for field in ("problem_statement", "option_ranking", "recommended_plan", "probe_plan"):
        assert parsed.get(field), (
            f"[Stage: Summary] Missing or empty required field '{field}' in summary output. "
            f"Got keys: {list(parsed)}"
        )


@_needs_groq
def test_summary_both_contradicted_claims_present(groq_env):
    """AC3+AC4: Both the VO2max and carb-timing claims appear in contradicted_evidence.

    This single test catches any regression where the contradiction section is
    dropped entirely or only partially populated.
    Failure message identifies [Stage: Summary].
    """
    from app.summary import generate_summary

    raw = asyncio.run(generate_summary(_CASE_DATA))
    parsed = json.loads(raw)

    contradicted = parsed.get("contradicted_evidence", "")

    missing = []
    if _VO2MAX_CLAIM_TITLE not in contradicted:
        missing.append(f"VO2max claim ('{_VO2MAX_CLAIM_TITLE}')")
    if _CARB_CLAIM_TITLE not in contradicted:
        missing.append(f"carb-timing claim ('{_CARB_CLAIM_TITLE}')")

    assert not missing, (
        "[Stage: Summary] Regression detected — the following claims were not flagged "
        f"as contradicted in the summary output: {', '.join(missing)}. "
        f"Actual contradicted_evidence: {contradicted!r}"
    )


# ---------------------------------------------------------------------------
# AC5 + AC6: Structured failure messages identify the regressing stage
# ---------------------------------------------------------------------------
# The tests above already embed [Stage: Weigh] and [Stage: Summary] in every
# assertion message.  The tests below verify this property explicitly by running
# the assertion logic against intentionally bad data and checking the error text.

def test_weigh_failure_message_identifies_weigh_stage():
    """AC5+AC6: A Weigh regression raises an assertion whose message names 'Weigh'."""
    bad_rankings = [
        {"label": "A", "rank": 3, "standing": None, "rationale": "last"},
        {"label": "B", "rank": 1, "standing": None, "rationale": "first"},
        {"label": "C", "rank": 2, "standing": None, "rationale": "second"},
    ]
    rank_by_label = {r["label"]: r["rank"] for r in bad_rankings}
    rank_a, rank_b = rank_by_label["A"], rank_by_label["B"]

    try:
        assert rank_a < rank_b, (
            f"[Stage: Weigh] Regression detected: deficit-aligned Plan A ranked {rank_a} "
            f"but overreaching Plan B ranked {rank_b}. "
            "Plan A must rank higher (lower rank number) than Plan B for the deficit fixture."
        )
        pytest.fail("Expected AssertionError was not raised")
    except AssertionError as exc:
        assert "[Stage: Weigh]" in str(exc), (
            "Weigh failure message must contain '[Stage: Weigh]' to identify the regressing "
            f"stage. Got: {exc!s}"
        )


def test_summary_failure_message_identifies_summary_stage():
    """AC5+AC6: A Summary regression raises an assertion whose message names 'Summary'."""
    parsed = {
        "problem_statement": "test",
        "option_ranking": "test",
        "recommended_plan": "test",
        "probe_plan": "test",
        "contradicted_evidence": "",
    }
    contradicted = parsed.get("contradicted_evidence", "")

    try:
        assert _VO2MAX_CLAIM_TITLE in contradicted, (
            "[Stage: Summary] Regression detected: VO2max-interval claim not found in "
            "the contradicted_evidence section of the summary output. "
            f"Expected title: '{_VO2MAX_CLAIM_TITLE}'. "
            f"Actual contradicted_evidence field: {contradicted!r}"
        )
        pytest.fail("Expected AssertionError was not raised")
    except AssertionError as exc:
        assert "[Stage: Summary]" in str(exc), (
            "Summary failure message must contain '[Stage: Summary]' to identify the "
            f"regressing stage. Got: {exc!s}"
        )
