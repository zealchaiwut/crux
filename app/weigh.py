"""Stage 3 weigh service — calls Claude API to re-rank Plans against user context."""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a plan-ranking assistant. "
    "Given a sharpened problem statement, a set of competing Plans (each with a label, name, and mechanism), "
    "and a user's personal context (numbers, constraints, situation), re-rank the Plans from most to least "
    "likely given the user's specific context. Also flag any Plans that can be confidently ruled in or ruled out.\n\n"
    "Output ONLY a JSON array with one object per Plan. Each object must have these fields:\n"
    '  "label": the plan label ("A", "B", or "C")\n'
    '  "rank": integer 1–3 (1 = best fit for this user)\n'
    '  "standing": one of "ruled-in", "ruled-out", or null (null = neutral/uncertain)\n\n'
    "Rules:\n"
    "- Every plan must appear exactly once.\n"
    "- Ranks must be unique integers from 1 to the number of plans.\n"
    "- Use 'ruled-in' only when the user's data strongly supports this plan as the cause.\n"
    "- Use 'ruled-out' only when the user's data clearly contradicts this plan.\n"
    "- Return only the JSON array — no markdown fences, no commentary."
)


class WeighError(Exception):
    """Raised when the Claude API call fails or returns unparseable output."""


async def rerank_plans(sharpened: str, plans: list[dict], context: str) -> list[dict]:
    """Call Claude API to re-rank plans against user context."""
    if not ANTHROPIC_API_KEY:
        raise WeighError("ANTHROPIC_API_KEY is not configured")

    plans_text = "\n".join(
        f"Plan {p['label']}: {p['name']} — {p['mechanism']}" for p in plans
    )
    user_message = (
        f"Problem: {sharpened}\n\n"
        f"Plans:\n{plans_text}\n\n"
        f"User context: {context}"
    )

    payload = {
        "model": _MODEL,
        "max_tokens": 512,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": user_message}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise WeighError(f"Claude API HTTP error {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise WeighError(f"Claude API request failed: {exc}") from exc

    try:
        text = resp.json()["content"][0]["text"]
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
