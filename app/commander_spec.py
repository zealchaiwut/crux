"""Commander spec generation service.

Calls the Claude API to generate a structured markdown spec from a
prototype Probe. The spec is consumed by a commander agent to implement
the prototype.

Only called for Probe records with type='prototype'.
"""
from app.claude_cli import ClaudeCLIError, complete

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
        CommanderSpecError: If the call fails or returns unusable output.
    """
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

    try:
        text = await complete(_SYSTEM, user_message, _MODEL)
    except ClaudeCLIError as exc:
        raise CommanderSpecError(f"Claude call failed: {exc}") from exc

    if not text.strip():
        raise CommanderSpecError("Claude returned empty spec text")
    return text.strip()
