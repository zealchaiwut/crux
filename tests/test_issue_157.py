"""Tests for issue #157: Factor source verification status into ranking and summary.

AC coverage:
  AC1 – weigh.py reads each source's support_status and applies a configurable penalty
         (multiplier < 1) to sources marked 'contradicts'
  AC2 – weigh.py applies no penalty (multiplier = 1) to sources marked 'supports' or 'unverified'
  AC3 – The adjusted score, not the raw score, is used for plan ranking
  AC4 – summary.py includes a rationale note for any contradicted source that influenced a plan
  AC5 – Contradicted sources are surfaced under a distinct '⚠ Contradicted Evidence' label
  AC6 – If all sources for the top-ranked plan are contradicted, summary flags this explicitly
  AC7 – Existing behaviour for plans with no contradicted sources is unchanged
  AC8 – Unit tests cover: all-supported, mixed, all-contradicted, and unverified-only source sets
"""

# ---------------------------------------------------------------------------
# weigh.py: apply_source_penalties
# ---------------------------------------------------------------------------

def _ranked(pairs):
    """Build a ranked list from [(label, rank)] pairs."""
    return [
        {"label": label, "rank": rank, "standing": None, "rationale": f"Plan {label}."}
        for label, rank in pairs
    ]


def _plans(sources_by_label):
    """Build plans_with_sources from {label: [support_status, ...]} mapping."""
    result = []
    for label, statuses in sources_by_label.items():
        sources = [
            {"support_status": status, "title": f"Source-{label}-{i}", "id": f"src-{label}-{i}"}
            for i, status in enumerate(statuses)
        ]
        result.append({"label": label, "sources": sources})
    return result


def test_weigh_exports_apply_source_penalties():
    """AC1: apply_source_penalties must be exported from app.weigh."""
    from app.weigh import apply_source_penalties
    assert callable(apply_source_penalties)


def test_weigh_exports_contradicted_multiplier():
    """AC1: A CONTRADICTED_MULTIPLIER constant must be exported from app.weigh."""
    import app.weigh as w
    assert hasattr(w, "CONTRADICTED_MULTIPLIER")
    assert 0 < w.CONTRADICTED_MULTIPLIER < 1, "Multiplier must be in (0, 1)"


# --- AC1: 'contradicts' sources reduce adjusted_score ---

def test_contradicted_source_reduces_adjusted_score():
    """AC1: A plan with a 'contradicts' source must have adjusted_score < raw_score."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2)])
    plans = _plans({"A": ["contradicts"], "B": []})
    result = apply_source_penalties(ranked, plans)
    a = next(r for r in result if r["label"] == "A")
    assert a["adjusted_score"] < a["raw_score"]


def test_multiple_contradicted_sources_compound_penalty():
    """AC1: Multiple 'contradicts' sources should compound the penalty further."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    single = apply_source_penalties(ranked, _plans({"A": ["contradicts"]}))
    double = apply_source_penalties(ranked, _plans({"A": ["contradicts", "contradicts"]}))
    assert double[0]["adjusted_score"] < single[0]["adjusted_score"]


def test_contradicted_sources_list_populated():
    """AC1: Result item must include a 'contradicted_sources' list naming the penalised sources."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    plans = _plans({"A": ["contradicts"]})
    result = apply_source_penalties(ranked, plans)
    a = result[0]
    assert "contradicted_sources" in a
    assert len(a["contradicted_sources"]) == 1


# --- AC2: 'supports' and 'unverified' sources get no penalty ---

def test_supports_source_no_penalty():
    """AC2: A plan with only 'supports' sources must have adjusted_score == raw_score."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    result = apply_source_penalties(ranked, _plans({"A": ["supports"]}))
    a = result[0]
    assert a["adjusted_score"] == a["raw_score"]


def test_unverified_source_no_penalty():
    """AC2: A plan with only 'unverified' sources must have adjusted_score == raw_score."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    result = apply_source_penalties(ranked, _plans({"A": ["unverified"]}))
    a = result[0]
    assert a["adjusted_score"] == a["raw_score"]


def test_partial_source_no_penalty():
    """AC2: A plan with only 'partial' sources must have adjusted_score == raw_score."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    result = apply_source_penalties(ranked, _plans({"A": ["partial"]}))
    a = result[0]
    assert a["adjusted_score"] == a["raw_score"]


def test_no_sources_no_penalty():
    """AC2: A plan with no sources at all must have adjusted_score == raw_score."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    result = apply_source_penalties(ranked, [{"label": "A", "sources": []}])
    a = result[0]
    assert a["adjusted_score"] == a["raw_score"]


# --- AC3: adjusted score determines final rank ---

def test_contradicted_top_plan_demoted():
    """AC3: A plan whose contradicted penalty drops its adjusted_score below a rival is demoted.

    With 3 plans: A(rank1).raw=3 → adjusted=1.5 (one contradicted source, multiplier=0.5),
    B(rank2).raw=2 → adjusted=2.0. B.adjusted > A.adjusted so B becomes rank 1.
    """
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2), ("C", 3)])
    plans = _plans({"A": ["contradicts"], "B": ["supports"], "C": ["supports"]})
    result = apply_source_penalties(ranked, plans)
    by_label = {r["label"]: r for r in result}
    assert by_label["B"]["rank"] == 1, "B should be promoted to rank 1 after A is penalised"
    assert by_label["A"]["rank"] > 1, "A should drop from rank 1 after penalty"


def test_supported_plan_outranks_contradicted_equivalent():
    """AC3/UAT5: A plan with only 'supports' sources outranks an otherwise equal plan with a
    'contradicts' source.

    With 3 plans: A(rank1).adjusted = 3*0.5 = 1.5, B(rank2).adjusted = 2.0 → B > A.
    """
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2), ("C", 3)])
    plans = _plans({"A": ["contradicts"], "B": ["supports"], "C": []})
    result = apply_source_penalties(ranked, plans)
    by_label = {r["label"]: r for r in result}
    assert by_label["B"]["adjusted_score"] > by_label["A"]["adjusted_score"]


def test_output_contains_raw_and_adjusted_score():
    """UAT6: Output must include both raw_score and adjusted_score per plan."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1)])
    result = apply_source_penalties(ranked, _plans({"A": ["contradicts"]}))
    assert "raw_score" in result[0]
    assert "adjusted_score" in result[0]


# --- AC8 scenario: all-supported ---

def test_all_supported_scenario():
    """AC8: all-supported — all plans keep their original ranking."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2), ("C", 3)])
    plans = _plans({"A": ["supports", "supports"], "B": ["supports"], "C": ["supports"]})
    result = apply_source_penalties(ranked, plans)
    by_label = {r["label"]: r for r in result}
    assert by_label["A"]["rank"] == 1
    assert by_label["B"]["rank"] == 2
    assert by_label["C"]["rank"] == 3
    for r in result:
        assert r["adjusted_score"] == r["raw_score"]


# --- AC8 scenario: mixed ---

def test_mixed_scenario():
    """AC8: mixed — plan with contradicted source gets penalty; clean plan may be promoted."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2)])
    plans = _plans({"A": ["contradicts", "supports"], "B": ["supports"]})
    result = apply_source_penalties(ranked, plans)
    a = next(r for r in result if r["label"] == "A")
    assert a["adjusted_score"] < a["raw_score"]


# --- AC8 scenario: all-contradicted ---

def test_all_contradicted_scenario():
    """AC8: all-contradicted — all plans penalised; rank ordering adjusted by penalty magnitude."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2)])
    plans = _plans({"A": ["contradicts", "contradicts"], "B": ["contradicts"]})
    result = apply_source_penalties(ranked, plans)
    for r in result:
        assert r["adjusted_score"] < r["raw_score"]


# --- AC8 scenario: unverified-only ---

def test_unverified_only_scenario():
    """AC8: unverified-only — no penalties, original rankings preserved."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2), ("C", 3)])
    plans = _plans({"A": ["unverified"], "B": ["unverified"], "C": ["unverified"]})
    result = apply_source_penalties(ranked, plans)
    by_label = {r["label"]: r for r in result}
    assert by_label["A"]["rank"] == 1
    assert by_label["B"]["rank"] == 2
    assert by_label["C"]["rank"] == 3


# --- AC7: no contradicted sources → unchanged behaviour ---

def test_no_contradicted_sources_ranks_unchanged():
    """AC7: Plans with no contradicted sources must retain their original rank order."""
    from app.weigh import apply_source_penalties
    ranked = _ranked([("A", 1), ("B", 2), ("C", 3)])
    plans = _plans({"A": ["supports"], "B": ["unverified"], "C": []})
    result = apply_source_penalties(ranked, plans)
    by_label = {r["label"]: r for r in result}
    assert by_label["A"]["rank"] == 1
    assert by_label["B"]["rank"] == 2
    assert by_label["C"]["rank"] == 3


def test_original_fields_preserved_after_penalties():
    """AC7: standing, rationale, and label must be preserved in the penalty output."""
    from app.weigh import apply_source_penalties
    ranked = [{"label": "A", "rank": 1, "standing": "ruled-in", "rationale": "Strong evidence."}]
    result = apply_source_penalties(ranked, [{"label": "A", "sources": []}])
    assert result[0]["standing"] == "ruled-in"
    assert result[0]["rationale"] == "Strong evidence."
    assert result[0]["label"] == "A"


# ---------------------------------------------------------------------------
# summary.py: build_contradiction_section
# ---------------------------------------------------------------------------

def _make_plan(label, rank, statuses):
    return {
        "label": label,
        "rank": rank,
        "sources": [
            {"support_status": s, "title": f"Source-{label}-{i}"}
            for i, s in enumerate(statuses)
        ],
    }


def test_summary_exports_build_contradiction_section():
    """AC4/AC5: build_contradiction_section must be exported from app.summary."""
    from app.summary import build_contradiction_section
    assert callable(build_contradiction_section)


def test_contradiction_section_empty_when_no_contradictions():
    """AC5: build_contradiction_section returns empty string when no 'contradicts' sources."""
    from app.summary import build_contradiction_section
    plans = [_make_plan("A", 1, ["supports", "unverified"])]
    section = build_contradiction_section(plans)
    assert not section.strip()


def test_contradiction_section_present_when_contradicted():
    """AC5: build_contradiction_section includes '⚠ Contradicted Evidence' header."""
    from app.summary import build_contradiction_section
    plans = [_make_plan("A", 1, ["contradicts"])]
    section = build_contradiction_section(plans)
    assert "⚠" in section or "Contradicted" in section
    assert section.strip()


def test_contradiction_section_names_source():
    """AC4: The contradiction section must identify the contradicted source by name."""
    from app.summary import build_contradiction_section
    plans = [{"label": "A", "rank": 1, "sources": [
        {"support_status": "contradicts", "title": "BadStudy2024"},
    ]}]
    section = build_contradiction_section(plans)
    assert "BadStudy2024" in section


def test_contradiction_section_names_plan():
    """AC4: The contradiction section must identify which plan the contradicted source belongs to."""
    from app.summary import build_contradiction_section
    plans = [{"label": "B", "rank": 1, "sources": [
        {"support_status": "contradicts", "title": "Refutation Paper"},
    ]}]
    section = build_contradiction_section(plans)
    assert "B" in section


# --- AC6: all sources contradicted for top plan ---

def test_contradiction_section_flags_all_contradicted_top_plan():
    """AC6: When all sources for rank-1 plan are contradicted, section must flag this explicitly."""
    from app.summary import build_contradiction_section
    plans = [
        _make_plan("A", 1, ["contradicts", "contradicts"]),
        _make_plan("B", 2, ["supports"]),
    ]
    section = build_contradiction_section(plans)
    assert "all" in section.lower() or "entirely" in section.lower() or "well-supported" in section.lower()


def test_contradiction_section_no_all_flag_when_partial():
    """AC6: When only some (not all) sources for top plan are contradicted, the all-flag is absent."""
    from app.summary import build_contradiction_section
    plans = [
        _make_plan("A", 1, ["contradicts", "supports"]),
    ]
    section = build_contradiction_section(plans)
    # Should still mention the contradicted source but NOT say all evidence is contradicted
    assert "Source-A-0" in section or "contradicted" in section.lower()
    # Must NOT falsely claim ALL evidence is contradicted
    lower = section.lower()
    assert not ("all supporting evidence" in lower and "well-supported" in lower), \
        "Should not claim all evidence contradicted when only some sources are contradicted"


# ---------------------------------------------------------------------------
# summary.py: _build_ranking_text flags contradicted sources
# ---------------------------------------------------------------------------

def test_build_ranking_text_flags_contradicted_source():
    """AC4: _build_ranking_text must visually flag 'contradicts' sources differently."""
    from app.summary import _build_ranking_text
    ranking = {
        "A": {
            "rank": 1,
            "rationale": "Top plan.",
            "sources": [{"title": "BadPaper", "id": "s1", "support_status": "contradicts"}],
        }
    }
    text = _build_ranking_text(ranking)
    assert "BadPaper" in text
    # Should flag the source as contradicted (⚠ or the word 'contradict')
    assert "⚠" in text or "contradict" in text.lower()


def test_build_ranking_text_no_flag_for_supported():
    """AC7: _build_ranking_text must NOT flag 'supports' sources as contradicted."""
    from app.summary import _build_ranking_text
    ranking = {
        "A": {
            "rank": 1,
            "rationale": "Top plan.",
            "sources": [{"title": "GoodPaper", "id": "s1", "support_status": "supports"}],
        }
    }
    text = _build_ranking_text(ranking)
    # Should not add a contradiction warning for a supporting source
    assert "⚠" not in text
    assert "contradict" not in text.lower()
