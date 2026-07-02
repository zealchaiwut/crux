"""LLM-backed source suggestion.

The DuckDuckGo-based research pipeline (research_orchestrator._CustomEngine)
depends on a live web-search endpoint that is currently HTTP 403-blocked, so
suggest returns nothing. This module sidesteps the dead search: it asks Claude
directly to propose candidate sources spanning the three supported kinds
(book / article / youtube / podcast), each with a title, url, claim, and citation.

These are *proposals* the user reviews before attaching — the existing verify
flow (SourceVerification) is what confirms a URL actually supports the claim.
"""
from __future__ import annotations

import json
import logging

from app.claude_cli import ClaudeCLIError, complete, extract_json
from app.research.types import Source

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_VALID_KINDS = frozenset({"book", "article", "youtube", "podcast"})

_SYSTEM = (
    "You are a research librarian. Given a hypothesis (a plan being investigated), "
    "propose real, well-known evidence sources that bear on it.\n"
    "Output ONLY a JSON array of 5 objects. Each object has exactly these fields:\n"
    '  "kind": one of "book", "article", "youtube", or "podcast".\n'
    '  "title": the real title of the book, article, video, or podcast episode.\n'
    '  "url": a plausible direct URL (publisher page, DOI, article link, '
    "youtube watch URL, or podcast episode/show page). Never invent fake domains.\n"
    '  "claim": one sentence — what this source concretely says about the hypothesis.\n'
    '  "citation": author(s) or host/show + year (+ publication/channel).\n'
    "Rules:\n"
    "- Include a MIX of kinds: at least one book, one article, one youtube, and "
    "one podcast.\n"
    "- Prefer widely-cited, verifiable sources over obscure ones.\n"
    "- Do NOT ask clarifying questions. Do NOT add prose or markdown fences. "
    "Your entire response must be the JSON array and nothing else."
)


async def suggest_sources(mechanism: str, prior: str, name: str = "") -> list[Source]:
    """Ask Claude to propose up to 5 candidate sources across the 3 kinds.

    Returns validated Source objects (invalid rows dropped). Raises nothing on
    an empty/garbled model reply — returns [] so the caller degrades gracefully.
    """
    hypothesis = "\n".join(
        p for p in [
            f"Plan: {name}" if name else "",
            f"Mechanism: {mechanism}" if mechanism else "",
            f"Prior probability: {prior}" if prior else "",
        ] if p
    ) or "(no hypothesis details provided)"

    try:
        text = await complete(_SYSTEM, hypothesis, _MODEL)
    except ClaudeCLIError as exc:
        logger.warning("llm_suggest: Claude call failed: %s", exc)
        return []

    try:
        rows = json.loads(extract_json(text))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("llm_suggest: could not parse response: %s", exc)
        return []

    if not isinstance(rows, list):
        logger.warning("llm_suggest: expected a JSON array, got %s", type(rows).__name__)
        return []

    sources: list[Source] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = (row.get("kind") or "").strip().lower()
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        claim = (row.get("claim") or "").strip()
        citation = (row.get("citation") or "").strip()
        if kind not in _VALID_KINDS or not (title and url and claim and citation):
            logger.warning(
                "llm_suggest: dropping row (kind=%r title=%r url=%r)", kind, title, url
            )
            continue
        sources.append(
            Source(kind=kind, title=title, url=url, claim=claim, citation=citation)
        )
    return sources
