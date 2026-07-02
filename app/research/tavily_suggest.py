"""Tavily-backed source suggestion.

Flow: search Tavily for the plan's hypothesis → get real URLs with extracted
page text → ask Claude, per result, whether that text supports the hypothesis
and to summarise the source's claim. Only genuinely-assessed results
(supports/partial/contradicts) are kept; irrelevant/unreadable ones are dropped.

This replaces LLM-guessed URLs (often wrong/paywalled) with real, content-backed
sources, so verification succeeds instead of returning "unverified".
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.claude_cli import ClaudeCLIError, complete, extract_json
from app.research import tavily_search
from app.research.types import Source

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_YT_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)
_PODCAST_RE = re.compile(
    r"(open\.spotify\.com/episode|podcasts\.apple\.com|podbean\.com|spreaker\.com|"
    r"buzzsprout\.com|soundcloud\.com|/podcast|/episode)",
    re.IGNORECASE,
)
_VERIFIED = frozenset({"supports", "partially_supports", "contradicts"})
# Cap the page text handed to the model so one huge page can't blow the prompt.
_MAX_CONTENT_CHARS = 6000
# How many candidates to return for hand-picking, and the kind minimums we aim
# to include among them (best-effort — only if enough verify).
_RETURN_MAX = 15
_MIN_PODCAST = 1
_MIN_YOUTUBE = 3
# Cap how many raw results we assess (each is one Claude call) to bound latency.
_ASSESS_CAP = 20


def _kind_for(url: str) -> str:
    if _YT_RE.search(url):
        return "youtube"
    if _PODCAST_RE.search(url):
        return "podcast"
    return "article"

_ASSESS_SYSTEM = (
    "You are a fact-checking research assistant. You are given a research "
    "hypothesis and the text of one source. Decide how the source bears on the "
    "hypothesis and summarise it.\n"
    "Respond with ONLY a JSON object with these fields:\n"
    '  "support_status": one of "supports", "partially_supports", '
    '"contradicts", or "unverified" (use "unverified" if the source is '
    "unrelated or the text is insufficient to judge).\n"
    '  "claim": one sentence stating what THIS source concretely says about '
    "the hypothesis.\n"
    '  "support_rationale": one or two sentences citing specific content from '
    "the source that justifies the status.\n"
    '  "citation": author or site/organization + year if determinable, else '
    "the publication or site name.\n"
    "No prose, no markdown fences — the entire response is the JSON object."
)


def _query(mechanism: str, prior: str, name: str) -> str:
    parts = [p for p in (name, mechanism) if p]
    return " ".join(parts) if parts else "research evidence"


async def _thai_query(en_query: str) -> str:
    """Translate the search query to Thai for Thai-language results; "" on failure."""
    try:
        raw = await complete(
            "Translate the given search query into natural Thai. "
            "Output ONLY the Thai query text — no quotes, no explanation.",
            en_query,
            _MODEL,
        )
    except ClaudeCLIError as exc:
        logger.warning("tavily_suggest: Thai translation failed: %s", exc)
        return ""
    return (raw or "").strip()


async def _assess(hypothesis: str, title: str, url: str, content: str) -> dict | None:
    user = (
        f"Hypothesis:\n{hypothesis}\n\n"
        f"Source title: {title}\nSource URL: {url}\n\n"
        f"Source text:\n{content[:_MAX_CONTENT_CHARS]}"
    )
    try:
        raw = await complete(_ASSESS_SYSTEM, user, _MODEL)
    except ClaudeCLIError as exc:
        logger.warning("tavily_suggest: assess call failed for %s: %s", url, exc)
        return None
    try:
        return json.loads(extract_json(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("tavily_suggest: could not parse assessment for %s: %s", url, exc)
        return None


async def suggest_sources(mechanism: str, prior: str, name: str = "") -> list[tuple[Source, dict]]:
    """Return up to 15 (Source, {support_status, support_rationale}) pairs.

    Runs several targeted Tavily searches — English + Thai, plus YouTube- and
    podcast-focused queries — so results span kinds and languages. Every result
    is assessed against the hypothesis; only genuinely-verified sources
    (supports/partial/contradicts) are kept, and the returned set aims to
    include at least 1 podcast and 3 YouTube sources when enough verify.

    The returned support_status uses the verifier vocabulary; the caller maps it
    to the DB enum. Returns [] when Tavily is unavailable or nothing verifies.
    """
    hypothesis = "\n".join(
        p for p in [
            f"Plan: {name}" if name else "",
            f"Mechanism: {mechanism}" if mechanism else "",
            f"Prior probability: {prior}" if prior else "",
        ] if p
    ) or "(no hypothesis details provided)"

    en = _query(mechanism, prior, name)
    th = await _thai_query(en)

    # Fan out targeted searches: general (EN/TH), YouTube-only (EN/TH), podcast.
    searches = [
        tavily_search.search(en, max_results=6),
        tavily_search.search(en, max_results=5, include_domains=["youtube.com"]),
        tavily_search.search(f"{en} podcast episode", max_results=4),
    ]
    if th:
        searches.append(tavily_search.search(th, max_results=5))
        searches.append(tavily_search.search(th, max_results=4, include_domains=["youtube.com"]))

    result_lists = await asyncio.gather(*searches)

    # Merge + dedupe by URL, preserving first-seen order.
    seen: set[str] = set()
    merged: list[dict] = []
    for results in result_lists:
        for r in results or []:
            url = (r.get("url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                merged.append(r)
    merged = merged[:_ASSESS_CAP]

    async def _one(result: dict) -> tuple[Source, dict] | None:
        url = (result.get("url") or "").strip()
        title = (result.get("title") or "").strip()
        content = result.get("raw_content") or result.get("content") or ""
        if not url or not content.strip():
            return None
        assessment = await _assess(hypothesis, title, url, content)
        if not assessment:
            return None
        status = assessment.get("support_status")
        if status not in _VERIFIED:
            return None
        claim = (assessment.get("claim") or "").strip()
        citation = (assessment.get("citation") or "").strip()
        if not (title and claim and citation):
            return None
        source = Source(
            kind=_kind_for(url), title=title, url=url, claim=claim, citation=citation
        )
        return source, {
            "support_status": status,
            "support_rationale": assessment.get("support_rationale") or "",
        }

    assessed = [p for p in await asyncio.gather(*[_one(r) for r in merged]) if p is not None]

    # Order so the kind minimums land inside the returned window, then fill with
    # the rest. Best-effort: if too few of a kind verified, we return what exists.
    pods = [p for p in assessed if p[0].kind == "podcast"]
    yts = [p for p in assessed if p[0].kind == "youtube"]
    arts = [p for p in assessed if p[0].kind == "article"]

    ordered: list[tuple[Source, dict]] = []
    ordered += pods[:_MIN_PODCAST]
    ordered += yts[:_MIN_YOUTUBE]
    rest = pods[_MIN_PODCAST:] + yts[_MIN_YOUTUBE:] + arts
    ordered += rest
    return ordered[:_RETURN_MAX]
