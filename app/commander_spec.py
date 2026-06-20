"""Commander spec generation service.

Calls the Claude API to generate a structured markdown spec from a
prototype Probe. The spec is consumed by a commander agent to implement
the prototype.

Only called for Probe records with type='prototype'.
"""
import os

import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a spec writer for commander, an AI agent that implements prototypes. "
    "Given a prototype probe description, produce a concise markdown spec that commander "
    "can use to build and test the prototype.\n\n"
    "The spec MUST contain exactly:\n"
    "1. A single `# Title` line — an imperative sentence describing what to build "
    "(e.g., '# Build a Minimal Daily Step Tracker')\n"
    "2. A `**Target metric:**` line — exactly one measurable outcome "
    "(e.g., '**Target metric:** task completion rate')\n"
    "3. An `## Acceptance Criteria` section — a markdown checklist of testable items "
    "(each line: `- [ ] ...`)\n"
    "4. A `## Build Context` section — two to four sentences of minimal background "
    "that explain the hypothesis being tested and why this prototype is the cheapest test\n\n"
    "Rules:\n"
    "- Do not include any scaffolding, code, or implementation instructions\n"
    "- Do not mention external systems (GitHub, Linear, Jira)\n"
    "- Do not include a verdict or action plan\n"
    "- Keep the whole spec under 300 words\n"
    "Return the markdown spec only — no preamble, no commentary."
)


class CommanderSpecError(Exception):
    """Raised when the Claude API call fails or returns unusable output."""


async def generate_commander_spec(probe_data: dict) -> str:
    """Generate a commander markdown spec for a prototype probe.

    Args:
        probe_data: dict with keys: target_metric, note, sharpened,
                    and optionally: plans (list of plan dicts).

    Returns:
        A markdown string containing the commander spec.

    Raises:
        CommanderSpecError: If the API call fails or returns unusable output.
    """
    if not ANTHROPIC_API_KEY:
        raise CommanderSpecError("ANTHROPIC_API_KEY is not configured")

    target_metric = probe_data.get("target_metric", "")
    note = probe_data.get("note", "")
    sharpened = probe_data.get("sharpened", "")
    plans = probe_data.get("plans", [])

    plans_text = ""
    if plans:
        plans_text = "\nHypotheses under test:\n" + "\n".join(
            f"  Plan {p.get('label', '?')}: {p.get('mechanism', '')}"
            for p in plans
        )

    user_message = (
        f"Problem being investigated: {sharpened}\n"
        f"Prototype probe instruction: {note}\n"
        f"Target metric: {target_metric}"
        f"{plans_text}\n\n"
        "Generate the commander spec markdown."
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
        raise CommanderSpecError(
            f"Claude API HTTP error {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise CommanderSpecError(f"Claude API request failed: {exc}") from exc

    try:
        text = resp.json()["content"][0]["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty or non-string response text")
        return text.strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise CommanderSpecError(f"Failed to parse Claude response: {exc}") from exc
