"""Stage 0 sharpen service — calls Claude API to produce a falsifiable problem statement."""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a problem-sharpening assistant. "
    "Given a vague, informal problem description, output ONLY a JSON object with two fields:\n"
    '  "sharpened": a single precise, falsifiable problem statement (1–2 sentences). '
    "Name the observable symptom, its magnitude or timeframe if known, and the causal question. "
    "No action plans — this is a research question.\n"
    '  "not_investigating": an array of 3–6 strings, each a plausible angle explicitly NOT in scope '
    "for this investigation. These keep the inquiry narrow.\n"
    "Return only the JSON object — no markdown fences, no commentary."
)


class SharpenError(Exception):
    """Raised when the Claude API call fails or returns unparseable output."""


async def sharpen_problem(raw_problem: str) -> dict:
    """Call Claude API, parse response, return {sharpened, not_investigating}."""
    if not ANTHROPIC_API_KEY:
        raise SharpenError("ANTHROPIC_API_KEY is not configured")

    payload = {
        "model": _MODEL,
        "max_tokens": 512,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": raw_problem}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SharpenError(f"Claude API HTTP error {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise SharpenError(f"Claude API request failed: {exc}") from exc

    try:
        text = resp.json()["content"][0]["text"]
        result = json.loads(text)
        sharpened = result["sharpened"]
        not_investigating = result["not_investigating"]
        if not isinstance(sharpened, str) or not isinstance(not_investigating, list):
            raise ValueError("unexpected shape")
        return {"sharpened": sharpened, "not_investigating": not_investigating}
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise SharpenError(f"Failed to parse Claude response: {exc}") from exc
