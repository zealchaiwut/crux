"""Stage 3 weigh service — calls Claude API to re-rank Plans against user context.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 3 (weigh): plans + user context → re-ranked plans with ruled-in/ruled-out flags.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a plan-ranking assistant. "
    "Given a sharpened problem statement, a set of competing Plans (each with a label, name, and mechanism), "
    "and optionally a user's personal context (numbers, constraints, situation), re-rank the Plans from most "
    "to least likely. If no user context is provided, rank based on the problem statement and plans alone. "
    "Also flag any Plans that can be confidently ruled in or ruled out.\n\n"
    "Output ONLY a JSON array with one object per Plan. Each object must have these fields:\n"
    '  "label": the plan label ("A", "B", or "C")\n'
    '  "rank": integer 1–3 (1 = best fit for this user)\n'
    '  "standing": one of "ruled-in", "ruled-out", or null (null = neutral/uncertain)\n\n'
    "Rules:\n"
    "- Every plan must appear exactly once.\n"
    "- Ranks must be unique integers from 1 to the number of plans.\n"
    "- Use 'ruled-in' only when the evidence strongly supports this plan as the cause.\n"
    "- Use 'ruled-out' only when the evidence clearly contradicts this plan.\n"
    "- Return only the JSON array — no markdown fences, no commentary."
)


class WeighError(Exception):
    """Raised when the Claude call fails or returns unparseable output."""


async def rerank_plans(sharpened: str, plans: list[dict], context: str | None) -> list[dict]:
    """Call Claude to re-rank plans against user context.

    context may be None or empty — in that case ranking is done on gathered sources alone.
    Returns list of dicts with keys: label, rank, standing (null|"ruled-in"|"ruled-out").
    """
    plans_text = "\n".join(
        f"Plan {p['label']}: {p['name']} — {p['mechanism']}" for p in plans
    )
    context_section = (
        f"User context: {context}" if context and context.strip()
        else "User context: (none — rank based on the problem and gathered sources only)"
    )
    user_message = (
        f"Problem: {sharpened}\n\n"
        f"Plans:\n{plans_text}\n\n"
        f"{context_section}"
    )

    try:
        text = await complete(_SYSTEM, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise WeighError(f"Claude call failed: {exc}") from exc

    try:
        result = json.loads(text)
        if not isinstance(result, list) or len(result) != len(plans):
            raise ValueError(
                f"expected list of {len(plans)} items, got {type(result).__name__} "
                f"len={len(result) if isinstance(result, list) else '?'}"
            )
        valid_labels = {p["label"] for p in plans}
        valid_standings = {"ruled-in", "ruled-out", None}
        for item in result:
            if not all(k in item for k in ("label", "rank", "standing")):
                raise ValueError(f"item missing required fields: {item}")
            if item["label"] not in valid_labels:
                raise ValueError(f"unexpected label: {item['label']}")
            if not isinstance(item["rank"], int) or item["rank"] < 1:
                raise ValueError(f"invalid rank: {item['rank']}")
            if item["standing"] not in valid_standings:
                raise ValueError(f"invalid standing: {item['standing']}")
        return result
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise WeighError(f"Failed to parse Claude response: {exc}") from exc
