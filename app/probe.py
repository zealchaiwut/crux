"""Stage 4 probe service — calls the judgment model to design probes across time horizons.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 4 (probe): leading Plan(s) → three probe designs, one per horizon (short/mid/long).
"""
import json

from app.claude_cli import ClaudeCLIError, complete
from app.llm_providers import call_stage

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

_SCHEMA_NAME = "probe_output"
_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "target_metric": {"type": "string"},
        "cost": {"type": "string"},
        "time": {"type": "string"},
        "note": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "duration": {"type": "string"},
        "decision_rule": {"type": "string"},
    },
    "required": ["type", "target_metric", "cost", "time", "note", "steps", "duration", "decision_rule"],
    "additionalProperties": False,
}


class ProbeError(Exception):
    """Raised when the LLM call fails or returns unparseable output."""


def _validate_probe_response(data: dict) -> dict:
    """Validate the response dict; raise ProbeError if invalid."""
    required = ("type", "target_metric", "cost", "time", "note")
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ProbeError(f"Response missing required fields: {missing}")
    if data["type"] not in _VALID_TYPES:
        raise ProbeError(
            f"Invalid probe type {data['type']!r}; must be one of {sorted(_VALID_TYPES)}"
        )
    # Normalise optional fields to safe defaults if absent
    if "steps" not in data or data["steps"] is None:
        data["steps"] = []
    if "duration" not in data or data["duration"] is None:
        data["duration"] = ""
    if "decision_rule" not in data or data["decision_rule"] is None:
        data["decision_rule"] = ""
    return data


_SYSTEM_THREE = (
    "You are a probe designer. Given a falsifiable problem statement and one or more competing "
    "Plans (each with a root-cause mechanism), design THREE probes for the leading plan — one "
    "per time horizon — so teams can act on early signals without waiting for the full experiment.\n\n"
    "Classify each probe as exactly one of:\n"
    '  "measurement"            — measure something already observable (e.g. resting HRV, bodyweight)\n'
    '  "lab-test"               — requires a professional or lab test; direct the user to a professional\n'
    '  "behaviour-experiment"   — change a behaviour and observe the outcome\n'
    '  "prototype"              — build a minimal product to test a hypothesis\n\n'
    "Horizon definitions:\n"
    '  "short" — fast early signal, duration expressed in DAYS (e.g. "5 days", "1 week").\n'
    "             Decision rule reflects an early go/no-go threshold — cheap and quick.\n"
    '  "mid"   — confirming signal, duration expressed in WEEKS (e.g. "2 weeks", "4 weeks").\n'
    "             Decision rule reflects a more confident threshold.\n"
    '  "long"  — definitive confirmation, duration expressed in weeks, months, or conclusive timeframe.\n'
    "             Decision rule reflects a conclusive/definitive threshold.\n\n"
    "Rules:\n"
    "- Each probe must have a DISTINCT target_metric, duration, and decision_rule.\n"
    "- Be honest: if the right answer is a lab test, say 'lab-test' and direct the user to see a professional.\n"
    "- Provide 3–6 concrete, ordered steps per probe.\n"
    "- State clear decision rules with confirmatory AND kill conditions.\n\n"
    "Return ONLY a JSON array of exactly three objects — no markdown fences, no commentary.\n"
    "Each object must have these fields:\n"
    '  "horizon": "short" | "mid" | "long"\n'
    '  "type": "<measurement|lab-test|behaviour-experiment|prototype>"\n'
    '  "target_metric": "<the one metric to measure>"\n'
    '  "cost": "<cost estimate>"\n'
    '  "time": "<time estimate>"\n'
    '  "note": "<brief honest instruction>"\n'
    '  "steps": ["<step 1>", "<step 2>", ...]  (3–6 ordered action steps)\n'
    '  "duration": "<how long to run this probe>"\n'
    '  "decision_rule": "<if X ≥ Y → proceed; if X < Y → discard>"\n'
    "Order the array: short first, mid second, long third.\n"
)

_VALID_HORIZONS = {"short", "mid", "long"}


def _validate_horizon_probe(data: dict, horizon: str) -> dict:
    """Validate a single probe dict from the three-probe response."""
    required = ("type", "target_metric", "cost", "time", "note")
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ProbeError(
            f"Probe {horizon!r} missing required fields: {missing}"
        )
    if data["type"] not in _VALID_TYPES:
        raise ProbeError(
            f"Probe {horizon!r} has invalid type {data['type']!r}; "
            f"must be one of {sorted(_VALID_TYPES)}"
        )
    data["horizon"] = horizon
    if "steps" not in data or data["steps"] is None:
        data["steps"] = []
    if "duration" not in data or data["duration"] is None:
        data["duration"] = ""
    if "decision_rule" not in data or data["decision_rule"] is None:
        data["decision_rule"] = ""
    return data


async def design_probes(sharpened: str, plans: list[dict]) -> list[dict]:
    """Call Claude API to design three probes (short/mid/long) for the leading Plan(s).

    Returns a list of exactly three dicts, each with keys: horizon, type, target_metric,
    cost, time, note, steps, duration, decision_rule.

    NOTE: not yet routed through app.llm_providers.call_stage (issue #190 landed on a
    branch cut before this function existed) — still calls app.claude_cli.complete
    directly. See follow-up ticket to bring this in line with design_probe() below.
    """
    plans_text = "\n".join(
        f"Plan {p['label']} (rank {p.get('current_rank', '?')}): "
        f"{p.get('name') or p['label']} — {p.get('mechanism', '')}"
        for p in plans
    )
    user_message = (
        f"Problem: {sharpened}\n\n"
        f"Competing plans:\n{plans_text}\n\n"
        "Design three probes (short, mid, long horizon) for the leading plan."
    )

    try:
        text = await complete(_SYSTEM_THREE, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise ProbeError(f"Claude call failed: {exc}") from exc

    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"expected a JSON array, got {type(data).__name__}")
        if len(data) != 3:
            raise ValueError(f"expected exactly 3 probe objects, got {len(data)}")
        horizons_in_response = [item.get("horizon") for item in data]
        if set(horizons_in_response) != _VALID_HORIZONS:
            raise ValueError(
                f"expected horizons {_VALID_HORIZONS}, got {set(horizons_in_response)}"
            )
        return [_validate_horizon_probe(item, item["horizon"]) for item in data]
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ProbeError(f"Failed to parse Claude response: {exc}") from exc


async def design_probe(sharpened: str, plans: list[dict]) -> dict:
    """Legacy single-probe design. Kept for backward compatibility with older callers.

    Returns dict with keys: type, target_metric, cost, time, note.
    """
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
        data = await call_stage(_SYSTEM, user_message, _MODEL, _SCHEMA_NAME, _JSON_SCHEMA)
    except Exception as exc:
        raise ProbeError(f"LLM call failed: {exc}") from exc

    try:
        if not isinstance(data, dict):
            raise ValueError(f"expected a JSON object, got {type(data).__name__}")
        return _validate_probe_response(data)
    except (KeyError, IndexError, ValueError) as exc:
        raise ProbeError(f"Failed to validate response: {exc}") from exc
