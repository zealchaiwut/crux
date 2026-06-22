"""Stage 0 sharpen service — calls Claude API to produce a falsifiable problem statement.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 0 (sharpen): raw problem → sharpened statement + not_investigating list.
"""
import json

from app.claude_cli import ClaudeCLIError, complete

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
    """Raised when the Claude call fails or returns unparseable output."""


async def sharpen_problem(raw_problem: str) -> dict:
    """Call Claude, parse response, return {sharpened, not_investigating}."""
    try:
        text = await complete(_SYSTEM, raw_problem, _MODEL)
    except ClaudeCLIError as exc:
        raise SharpenError(f"Claude call failed: {exc}") from exc

    try:
        result = json.loads(text)
        sharpened = result["sharpened"]
        not_investigating = result["not_investigating"]
        if not isinstance(sharpened, str) or not isinstance(not_investigating, list):
            raise ValueError("unexpected shape")
        return {"sharpened": sharpened, "not_investigating": not_investigating}
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise SharpenError(f"Failed to parse Claude response: {exc}") from exc
