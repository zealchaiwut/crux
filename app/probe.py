"""Stage 4 probe service — calls Claude API to design the cheapest decisive test.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 4 (probe): leading Plan(s) → single probe design with type, target_metric, cost, time, note.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

_MODEL = "claude-haiku-4-5-20251001"

_VALID_TYPES = {"measurement", "lab-test", "behaviour-experiment", "prototype"}

_SYSTEM = (
    "You are a probe designer. Given a falsifiable problem statement and one or more competing "
    "Plans (each with a root-cause mechanism), design the single cheapest, most decisive test "
    "to validate or refute the leading plan(s).\n\n"
    "Classify the probe as exactly one of:\n"
    '  "measurement"            — measure something already observable (e.g. resting HRV, bodyweight)\n'
    '  "lab-test"               — requires a professional or lab test (e.g. blood test); '
    "direct the user to see an appropriate professional\n"
    '  "behaviour-experiment"   — change a behaviour and observe the outcome (e.g. deload week, '
    "dietary change, sleep intervention)\n"
    '  "prototype"              — build a minimal product to test a hypothesis\n\n'
    "Rules:\n"
    "- Be honest: if the right answer is a blood test, say 'lab-test' and direct the user "
    "to see a doctor. Do NOT suggest a fictional app or invented solution.\n"
    "- Name exactly ONE target metric — the single number or observation that will settle the question.\n"
    "- Keep cost and time estimates realistic and brief (e.g. 'free', '~£30', '7 days', '2 weeks').\n"
    "- Provide 3–6 concrete, ordered steps someone can follow to run this probe outside the app.\n"
    "- State a clear decision rule with BOTH a confirmatory outcome AND a kill condition.\n\n"
    "Return ONLY a JSON object — no markdown fences, no commentary — with these fields:\n"
    '  "type": "<measurement|lab-test|behaviour-experiment|prototype>"\n'
    '  "target_metric": "<the one metric to measure>"\n'
    '  "cost": "<cost estimate>"\n'
    '  "time": "<time estimate>"\n'
    '  "note": "<brief honest instruction>"\n'
    '  "steps": ["<step 1>", "<step 2>", ...]  (3–6 ordered action steps)\n'
    '  "duration": "<how long to run the probe, e.g. \'7 days\', \'2 weeks\'>"\n'
    '  "decision_rule": "<if X ≥ Y → proceed with Plan A; if X < Y → discard Plan A>"\n'
)


class ProbeError(Exception):
    """Raised when the Claude API call fails or returns unparseable output."""


def _validate_probe_response(data: dict) -> dict:
    """Validate the Claude response dict; raise ProbeError if invalid."""
    required = ("type", "target_metric", "cost", "time", "note")
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ProbeError(f"Claude response missing required fields: {missing}")
    if data["type"] not in _VALID_TYPES:
        raise ProbeError(
            f"Invalid probe type {data['type']!r}; must be one of {sorted(_VALID_TYPES)}"
        )
    # Normalise optional new fields to safe defaults if absent
    if "steps" not in data or data["steps"] is None:
        data["steps"] = []
    if "duration" not in data or data["duration"] is None:
        data["duration"] = ""
    if "decision_rule" not in data or data["decision_rule"] is None:
        data["decision_rule"] = ""
    return data


async def design_probe(sharpened: str, plans: list[dict]) -> dict:
    """Call Claude API to design the cheapest decisive probe for the leading Plan(s).

    Returns dict with keys: type, target_metric, cost, time, note.
    """
    # Build context from plans ordered by current rank
    plans_text = "\n".join(
        f"Plan {p['label']} (rank {p.get('current_rank', '?')}): "
        f"{p.get('name') or p['label']} — {p.get('mechanism', '')}"
        for p in plans
    )
    user_message = (
        f"Problem: {sharpened}\n\n"
        f"Competing plans:\n{plans_text}\n\n"
        "Design the single cheapest, most decisive probe for the leading plan(s)."
    )

    try:
        text = await complete(_SYSTEM, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise ProbeError(f"Claude call failed: {exc}") from exc

    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"expected a JSON object, got {type(data).__name__}")
        return _validate_probe_response(data)
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ProbeError(f"Failed to parse Claude response: {exc}") from exc
