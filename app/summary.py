"""Case summary generation using Claude.

Generates a structured synthesis of a case at the probe stage, covering:
  1. Sharpened problem statement
  2. A/B/C option ranking with per-option reasoning citing source documents
  3. Recommended plan
  4. Suggested probe plan

All summary logic lives here; the router calls generate_summary() and handles
persistence and caching.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

_MODEL = "claude-haiku-4-5-20251001"

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
