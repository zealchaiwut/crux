"""Case summary generation using the configured LLM provider.

Provides two interfaces:

  run(problem, ranking, recommended_plan, probe_plan) -> str
    Pipeline-orchestrator interface. Accepts explicit stage outputs and returns
    a GitHub-flavoured markdown conclusion document.

  generate_summary(case_data: dict) -> str
    Web-API interface. Accepts the raw case dict (as assembled by the router)
    and returns a JSON-encoded literature-review-style summary string with
    inline numbered citations.

All summary logic lives here; the router calls generate_summary() and handles
persistence and caching.
"""
import json
import re

from app.claude_cli import ClaudeCLIError, complete
from app.llm_providers import call_stage

_MODEL = "claude-haiku-4-5-20251001"

_MARKDOWN_SYSTEM = """\
You are a decision-support analyst. Given a structured case investigation, produce a \
concise conclusion document in GitHub-flavoured markdown.

Structure your response with exactly these four sections (use ## headings):
  ## Problem Statement
  ## A/B/C Option Ranking
  ## Recommended Plan
  ## Probe Plan

Rules:
- Use GitHub-flavoured markdown (##, **bold**, bullet lists)
- In the Option Ranking section, include each option's rank, core reasoning, and cite \
any source documents by title or ID
- Every section must be non-empty
- Return only the markdown document — no preamble or trailing commentary
"""

_LITERATURE_REVIEW_SYSTEM = """\
You are a research analyst synthesising a case investigation into a literature-review-style report.

Given a problem statement and a numbered list of evidence sources, write 3-4 cohesive paragraphs that:
- Summarise the core problem and the evidence landscape
- Use inline citations in the form [1], [2], etc., matching the provided numbered sources
- Synthesise competing explanations and the strongest evidence

Return your output as a JSON object with exactly two top-level keys:
  "paragraphs": ordered array of 3-4 paragraph strings, each containing inline [N] citation markers
  "references": array of objects, one per cited source, each with:
    - "id": integer matching the inline citation marker
    - "source_id": the exact source identifier from the provided source list
    - "title": the source title
    - "url": the source URL

Rules:
- Return ONLY the JSON object — no preamble, no code fence
- Only cite sources from the provided numbered list; do not invent citations
- Every [N] marker that appears in any paragraph must have a matching entry in references with "id": N
- Every entry in references must correspond to an [N] marker in at least one paragraph
- If no sources are provided, write paragraphs without citation markers and return "references": []
"""

_SUMMARY_SCHEMA_NAME = "literature_review_output"
_SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "source_id": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["id", "source_id", "title", "url"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["paragraphs", "references"],
    "additionalProperties": False,
}


class SummaryError(Exception):
    """Raised when the LLM call fails or returns an unusable summary."""


def _build_ranking_text(ranking: dict) -> str:
    """Format the ranking dict into readable text for the prompt."""
    if not ranking:
        return "No ranking data provided."
    lines = []
    for label in sorted(ranking, key=lambda k: ranking[k].get("rank", 99)):
        opt = ranking[label]
        rank = opt.get("rank", "?")
        rationale = opt.get("rationale", "")
        sources = opt.get("sources", [])
        line = f"Option {label} (Rank {rank}): {rationale}"
        for src in sources:
            title = src.get("title") or src.get("id") or "untitled"
            src_id = src.get("id") or ""
            status = src.get("support_status", "unverified")
            if status == "contradicts":
                prefix = "⚠ Contradicted source"
            else:
                prefix = "Source"
            line += f" [{prefix}: {title}" + (f" ({src_id})" if src_id else "") + "]"
        lines.append(line)
    return "\n".join(lines)


def build_contradiction_section(ranked_plans: list[dict]) -> str:
    """Build a '⚠ Contradicted Evidence' section from ranked plans.

    Args:
        ranked_plans: list of {label, rank, sources: [{support_status, title, ...}]}

    Returns:
        A formatted string section, or empty string when no contradicted sources exist.
    """
    top_plan = None
    all_contradicted: list[dict] = []

    for plan in ranked_plans:
        if plan.get("rank") == 1:
            top_plan = plan
        for src in plan.get("sources") or []:
            if src.get("support_status") == "contradicts":
                all_contradicted.append({
                    "plan_label": plan.get("label", "?"),
                    "title": src.get("title") or src.get("id") or "untitled",
                })

    if not all_contradicted:
        return ""

    lines = ["## ⚠ Contradicted Evidence\n"]
    for item in all_contradicted:
        lines.append(
            f"- **{item['title']}** (Plan {item['plan_label']}) "
            "— this source is contradicted by the verification step."
        )

    if top_plan:
        top_sources = top_plan.get("sources") or []
        if top_sources and all(
            s.get("support_status") == "contradicts" for s in top_sources
        ):
            label = top_plan.get("label", "?")
            lines.append(
                f"\n**Warning:** All supporting evidence for the top-ranked plan "
                f"(Plan {label}) is contradicted. "
                "This plan is not well-supported and should not be treated as the leading explanation."
            )

    return "\n".join(lines)


async def run(
    problem: str,
    ranking: dict,
    recommended_plan: str,
    probe_plan: str,
) -> str:
    """Synthesise a GitHub-flavoured markdown conclusion from pipeline stage outputs.

    Args:
        problem: Sharpened problem statement from the sharpen stage.
        ranking: Dict mapping option labels (A/B/C) to rank, rationale, and sources.
        recommended_plan: Text description of the top-ranked plan to pursue.
        probe_plan: Text description of the probe design.

    Returns:
        A GitHub-flavoured markdown string covering all four sections.

    Raises:
        SummaryError: if recommended_plan is empty, the Claude call fails, or the
            response is blank/unparseable.
    """
    if not recommended_plan or not recommended_plan.strip():
        raise SummaryError(
            "recommended_plan must be a non-empty string; "
            "cannot synthesise a conclusion without a recommended plan."
        )

    ranking_text = _build_ranking_text(ranking)
    user_message = (
        f"## Problem Being Investigated\n\n{problem}\n\n"
        f"## Option Ranking\n\n{ranking_text}\n\n"
        f"## Recommended Plan\n\n{recommended_plan}\n\n"
        f"## Probe Plan\n\n{probe_plan}\n\n"
        "Produce the case conclusion document."
    )

    try:
        raw = await complete(_MARKDOWN_SYSTEM, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise SummaryError(f"Claude call failed: {exc}") from exc

    stripped = raw.strip()
    if not stripped:
        raise SummaryError(
            "Claude returned a blank response; cannot produce a valid markdown summary."
        )

    ranked_plans = [
        {"label": label, "rank": opt.get("rank", 99), "sources": opt.get("sources") or []}
        for label, opt in ranking.items()
    ]
    contradiction_section = build_contradiction_section(ranked_plans)
    if contradiction_section:
        return f"{stripped}\n\n{contradiction_section}"
    return stripped


async def generate_summary(case_data: dict) -> str:
    """Generate a literature-review-style cited JSON summary for the given case data.

    Args:
        case_data: dict with keys:
            sharpened (str), plans (list of plan dicts), probe (dict | None)
            Each plan dict has: label, name, mechanism, current_rank, sources (list)
            Each source dict has: id, title, url, claim

    Returns:
        A JSON string with keys:
            paragraphs: list of 3-4 paragraph strings with inline [N] citation markers
            references: list of objects each with id, source_id, title, url

    Raises:
        SummaryError: if the LLM call fails, the response is unparseable, citation
            markers are inconsistent, or any reference source_id is not a real case source.
    """
    sharpened = case_data.get("sharpened") or case_data.get("raw_problem", "")
    plans = case_data.get("plans") or []

    # Collect all sources across all plans, preserving insertion order
    all_sources = []
    seen_ids = set()
    for plan in plans:
        for src in (plan.get("sources") or []):
            src_id = src.get("id")
            if src_id and src_id not in seen_ids:
                seen_ids.add(src_id)
                all_sources.append({
                    "source_id": src_id,
                    "title": src.get("title") or "",
                    "url": src.get("url") or "",
                    "claim": src.get("claim") or "",
                })

    valid_source_ids = {s["source_id"] for s in all_sources}

    if all_sources:
        sources_block = "Evidence sources available for citation:\n" + "\n".join(
            f"[{i + 1}] source_id={s['source_id']!r}, title={s['title']!r}, url={s['url']!r}"
            + (f", claim: {s['claim']}" if s["claim"] else "")
            for i, s in enumerate(all_sources)
        )
    else:
        sources_block = "No evidence sources are available for citation."

    user_message = (
        f"Problem being investigated: {sharpened}\n\n"
        f"{_format_plans(plans)}\n\n"
        f"{sources_block}\n\n"
        "Generate the literature-review JSON summary."
    )

    try:
        raw_data = await call_stage(
            _LITERATURE_REVIEW_SYSTEM, user_message, _MODEL,
            _SUMMARY_SCHEMA_NAME, _SUMMARY_JSON_SCHEMA,
        )
    except Exception as exc:
        raise SummaryError(f"LLM call failed: {exc}") from exc

    data = _validate_literature_review_dict(raw_data)
    _validate_citations(data["paragraphs"], data["references"])
    _validate_source_ids(data["references"], valid_source_ids, data["paragraphs"])

    return json.dumps(data)


def _format_plans(plans: list) -> str:
    if not plans:
        return "Options: none recorded."
    lines = ["Options under investigation:"]
    for plan in sorted(plans, key=lambda p: p.get("current_rank") or 99):
        label = plan.get("label", "?")
        name = plan.get("name") or f"Plan {label}"
        mechanism = plan.get("mechanism") or ""
        rank = plan.get("current_rank", "?")
        lines.append(f"  Plan {label} (rank {rank}): {name} — {mechanism}")
    return "\n".join(lines)


def _validate_literature_review_dict(data: dict) -> dict:
    """Structurally validate an already-parsed literature-review response dict."""
    if "paragraphs" not in data or not isinstance(data["paragraphs"], list):
        raise SummaryError(
            f"Summary JSON missing or invalid 'paragraphs' array. Got keys: {list(data)}"
        )
    if "references" not in data or not isinstance(data["references"], list):
        raise SummaryError(
            f"Summary JSON missing or invalid 'references' array. Got keys: {list(data)}"
        )
    if len(data["paragraphs"]) < 3 or len(data["paragraphs"]) > 4:
        raise SummaryError(
            f"'paragraphs' must contain 3-4 items; got {len(data['paragraphs'])}"
        )

    for ref in data["references"]:
        for field in ("id", "source_id", "title", "url"):
            if field not in ref:
                raise SummaryError(
                    f"Reference object missing required field '{field}': {ref}"
                )
        if not isinstance(ref["id"], int):
            raise SummaryError(
                f"Reference 'id' must be an integer; got {type(ref['id'])!r}: {ref['id']!r}"
            )

    return {"paragraphs": data["paragraphs"], "references": data["references"]}


def _validate_citations(paragraphs: list, references: list) -> None:
    """Assert every [N] marker in paragraphs has a matching reference id, and vice versa."""
    markers_in_text: set[int] = set()
    for para in paragraphs:
        for m in re.findall(r'\[(\d+)\]', para):
            markers_in_text.add(int(m))

    ref_ids = {r["id"] for r in references}

    missing_refs = markers_in_text - ref_ids
    if missing_refs:
        raise SummaryError(
            f"Citation markers {sorted(missing_refs)} appear in paragraphs "
            f"but have no matching entry in references"
        )

    orphan_refs = ref_ids - markers_in_text
    if orphan_refs:
        raise SummaryError(
            f"Reference ids {sorted(orphan_refs)} have no corresponding [N] "
            f"citation marker in any paragraph"
        )


def _validate_source_ids(references: list, valid_source_ids: set, paragraphs: list) -> None:
    """Assert every cited references[].source_id is valid and non-falsy."""
    cited_ref_ids: set[int] = set()
    for para in paragraphs:
        for m in re.findall(r'\[(\d+)\]', para):
            cited_ref_ids.add(int(m))

    for ref in references:
        source_id = ref.get("source_id")
        ref_id = ref.get("id")
        if ref_id not in cited_ref_ids:
            continue
        if not source_id:
            raise SummaryError(
                f"Reference [{ref_id}] has a falsy source_id ({source_id!r}) "
                f"but is cited in the summary text — phantom citation"
            )
        if source_id not in valid_source_ids:
            raise SummaryError(
                f"Reference source_id {source_id!r} does not match any source on the case "
                f"(valid ids: {sorted(valid_source_ids)!r})"
            )
