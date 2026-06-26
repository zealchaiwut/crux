"""Case summary generation using Claude.

Provides two interfaces:

  run(problem, ranking, recommended_plan, probe_plan) -> str
    Pipeline-orchestrator interface. Accepts explicit stage outputs and returns
    a GitHub-flavoured markdown conclusion document.

  generate_summary(case_data: dict) -> str
    Web-API interface. Accepts the raw case dict (as assembled by the router)
    and returns a JSON-encoded summary string.

All summary logic lives here; the router calls generate_summary() and handles
persistence and caching.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

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

_SYSTEM = """\
You are a decision-support analyst. Given a structured case investigation, produce a concise \
executive summary in JSON format.

Return ONLY a JSON object with exactly these four keys:
  "problem_statement" - one sentence restating the sharpened problem being investigated
  "option_ranking"    - for each option (A, B, C), one paragraph covering its rank, core \
mechanism, and evidence from any cited source documents (cite by title or ID)
  "recommended_plan"  - one paragraph naming the top-ranked option and why it should be pursued
  "probe_plan"        - one paragraph describing the current or suggested probe design

Rules:
- Do not wrap the JSON in a code fence
- Do not add any prose outside the JSON object
- Every field must be a non-empty string
- If source documents are attached, cite at least one by name or ID in option_ranking
"""


class SummaryError(Exception):
    """Raised when Claude fails to return a usable summary."""


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
            line += f" [Source: {title}" + (f" ({src_id})" if src_id else "") + "]"
        lines.append(line)
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

    return stripped


async def generate_summary(case_data: dict) -> str:
    """Generate a JSON-encoded summary string for the given case data.

    Args:
        case_data: dict with keys:
            sharpened (str), plans (list of plan dicts), probe (dict | None)
            Each plan dict has: label, name, mechanism, current_rank, sources (list)
            Each source dict has: id, title, claim, citation

    Returns:
        A JSON string with keys: problem_statement, option_ranking,
        recommended_plan, probe_plan.

    Raises:
        SummaryError: if the Claude call fails or the response is unparseable.
    """
    sharpened = case_data.get("sharpened") or case_data.get("raw_problem", "")
    plans = case_data.get("plans") or []
    probe = case_data.get("probe")

    plans_text = _format_plans(plans)
    probe_text = _format_probe(probe)

    user_message = (
        f"Problem being investigated: {sharpened}\n\n"
        f"{plans_text}\n"
        f"{probe_text}\n"
        "Generate the case summary JSON."
    )

    try:
        raw = await complete(_SYSTEM, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise SummaryError(f"Claude call failed: {exc}") from exc

    return _parse_and_validate(raw)


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
        for src in plan.get("sources") or []:
            title = src.get("title") or src.get("id") or "untitled"
            claim = src.get("claim") or ""
            src_id = src.get("id") or ""
            lines.append(f"    Source: {title} (id: {src_id}) — {claim}")
    return "\n".join(lines)


def _format_probe(probe: dict | None) -> str:
    if not probe:
        return "Probe: not yet designed."
    ptype = probe.get("type") or "unknown"
    metric = probe.get("target_metric") or ""
    note = probe.get("note") or ""
    return f"Probe type: {ptype}. Target metric: {metric}. Note: {note}."


def _parse_and_validate(raw: str) -> str:
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SummaryError(
            f"Claude returned non-JSON response: {raw[:200]!r}"
        ) from exc

    required = ("problem_statement", "option_ranking", "recommended_plan", "probe_plan")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise SummaryError(
            f"Summary JSON missing or empty fields: {missing}. Got: {list(data)}"
        )

    return json.dumps({k: data[k] for k in required})
