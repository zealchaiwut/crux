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
    "Return only the JSON object — no markdown fences, no commentary.\n"
    "CRITICAL: Do NOT ask clarifying questions and do NOT reply with any prose. "
    "The input may be vague or incomplete — that is expected. Make reasonable "
    "assumptions, note the unknowns inside the sharpened statement, and ALWAYS "
    "return the JSON object. Your entire response must be the JSON object and "
    "nothing else."
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


def _validate(data: dict) -> dict:
    """Validate the sharpen response shape."""
    sharpened = data["sharpened"]
    not_investigating = data["not_investigating"]
    if not isinstance(sharpened, str) or not isinstance(not_investigating, list):
        raise ValueError("unexpected shape")
    return {"sharpened": sharpened, "not_investigating": not_investigating}


async def sharpen_problem(raw_problem: str) -> dict:
    """Call the judgment model, parse response, return {sharpened, not_investigating}.

    Structured-output providers should always return valid JSON, but the
    fallback text-completion path (no provider configured) can still return
    prose. We retry once with a hardened reminder before giving up.
    """
    _retry_note = (
        "\n\nReturn ONLY the JSON object described in your instructions. "
        "No questions, no prose."
    )
    last_exc: Exception | None = None
    for attempt in range(2):
        prompt = raw_problem if attempt == 0 else raw_problem + _retry_note
        try:
            data = await call_stage(_SYSTEM, prompt, _MODEL, _SCHEMA_NAME, _JSON_SCHEMA)
        except Exception as exc:
            last_exc = exc
            continue

        try:
            return _validate(data)
        except (KeyError, IndexError, ValueError) as exc:
            last_exc = exc  # retry once, then surface

    raise SharpenError(f"Failed to get a valid response: {last_exc}") from last_exc
