"""Stage 1 bake-off service — calls Claude API to generate Plan A/B/C.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 1 (bake-off): sharpened problem → Plan A/B/C each with label, name, mechanism, prior.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a root-cause hypothesis generator. "
    "Given a sharpened, falsifiable problem statement, output ONLY a JSON array of exactly three "
    "competing root-cause Plans labelled A, B, and C. Each plan object must have these fields:\n"
    '  "label": one of "A", "B", "C"\n'
    '  "name": a short name for the hypothesis (3–6 words)\n'
    '  "mechanism": a single sentence describing the mechanistic pathway (≤20 words)\n'
    '  "prior": a float between 0 and 1 representing the prior probability. '
    "The three priors must sum to exactly 1.0.\n"
    "Order the plans from highest to lowest prior. "
    "Return only the JSON array — no markdown fences, no commentary."
)


class BakeOffError(Exception):
    """Raised when the Claude call fails or returns unparseable output."""


async def generate_plans(sharpened: str) -> list[dict]:
    """Call Claude, parse response, return list of 3 plan dicts."""
    try:
        text = await complete(_SYSTEM, sharpened, _MODEL)
    except ClaudeCLIError as exc:
        raise BakeOffError(f"Claude call failed: {exc}") from exc

    try:
        plans = json.loads(text)
        if not isinstance(plans, list) or len(plans) != 3:
            raise ValueError(
                f"expected list of 3 plans, got {type(plans).__name__} "
                f"len={len(plans) if isinstance(plans, list) else '?'}"
            )
        for p in plans:
            if not all(k in p for k in ("label", "name", "mechanism", "prior")):
                raise ValueError(f"plan missing required fields: {p}")
            if p["label"] not in ("A", "B", "C"):
                raise ValueError(f"invalid label: {p['label']}")
            prior = float(p["prior"])
            if not (0.0 <= prior <= 1.0):
                raise ValueError(f"prior out of range: {prior}")
        return plans
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise BakeOffError(f"Failed to parse Claude response: {exc}") from exc
