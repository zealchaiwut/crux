"""Stage 0 sharpen service — calls the judgment model to produce a falsifiable problem statement.

PRODUCT.md §9: "LLM: Claude API for the stage prompts (sharpen, plans, weigh, probe design)."
Stage 0 (sharpen): raw problem → sharpened statement + not_investigating list.
"""

from app.llm_providers import call_stage

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

_SCHEMA_NAME = "sharpen_output"
_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "sharpened": {"type": "string"},
        "not_investigating": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sharpened", "not_investigating"],
    "additionalProperties": False,
}


class SharpenError(Exception):
    """Raised when the LLM call fails or returns unparseable output."""


async def sharpen_problem(raw_problem: str) -> dict:
    """Call the judgment model, parse response, return {sharpened, not_investigating}."""
    try:
        data = await call_stage(_SYSTEM, raw_problem, _MODEL, _SCHEMA_NAME, _JSON_SCHEMA)
    except Exception as exc:
        raise SharpenError(f"LLM call failed: {exc}") from exc

    try:
        sharpened = data["sharpened"]
        not_investigating = data["not_investigating"]
        if not isinstance(sharpened, str) or not isinstance(not_investigating, list):
            raise ValueError("unexpected shape")
        return {"sharpened": sharpened, "not_investigating": not_investigating}
    except (KeyError, IndexError, ValueError) as exc:
        raise SharpenError(f"Failed to validate response: {exc}") from exc
