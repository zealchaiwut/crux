"""Stage 0 sharpen service — calls Claude API to produce a falsifiable problem statement.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 0 (sharpen): raw problem → sharpened statement + not_investigating list.
"""
import json

from app.claude_cli import ClaudeCLIError, complete, extract_json

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a problem-sharpening assistant. "
    "Given a vague, informal problem description, output ONLY a JSON object with two fields:\n"
    '  "sharpened": a single precise, falsifiable problem statement (1–2 sentences). '
    "Name the observable symptom, its magnitude or timeframe if known, and the causal question. "
    "No action plans — this is a research question.\n"
    '  "not_investigating": an array of 3–6 strings, each a plausible angle explicitly NOT in scope '
    "for this investigation. These keep the inquiry narrow.\n"
    "Return only the JSON object — no markdown fences, no commentary.\n"
    "CRITICAL: Do NOT ask clarifying questions and do NOT reply with any prose. "
    "The input may be vague or incomplete — that is expected. Make reasonable "
    "assumptions, note the unknowns inside the sharpened statement, and ALWAYS "
    "return the JSON object. Your entire response must be the JSON object and "
    "nothing else."
)


class SharpenError(Exception):
    """Raised when the Claude call fails or returns unparseable output."""


def _parse(text: str) -> dict:
    """Extract and validate the sharpen JSON, tolerating prose around it."""
    result = json.loads(extract_json(text))
    sharpened = result["sharpened"]
    not_investigating = result["not_investigating"]
    if not isinstance(sharpened, str) or not isinstance(not_investigating, list):
        raise ValueError("unexpected shape")
    return {"sharpened": sharpened, "not_investigating": not_investigating}


async def sharpen_problem(raw_problem: str) -> dict:
    """Call Claude, parse response, return {sharpened, not_investigating}.

    The CLI agent occasionally replies with prose/clarifying questions instead
    of JSON. We tolerate prose around the JSON (extract_json) and retry once
    with a hardened reminder before giving up.
    """
    _retry_note = (
        "\n\nReturn ONLY the JSON object described in your instructions. "
        "No questions, no prose."
    )
    last_exc: Exception | None = None
    for attempt in range(2):
        prompt = raw_problem if attempt == 0 else raw_problem + _retry_note
        try:
            text = await complete(_SYSTEM, prompt, _MODEL)
        except ClaudeCLIError as exc:
            raise SharpenError(f"Claude call failed: {exc}") from exc

        try:
            return _parse(text)
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc  # retry once, then surface

    raise SharpenError(f"Failed to parse Claude response: {last_exc}") from last_exc
