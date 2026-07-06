"""Bulk pipeline stage functions — always routed to CRUX_BULK_MODEL (issue #191).

Three high-volume, low-stakes stages that bypass the judgment model and route
explicitly to the configured bulk model via call_bulk_stage() / call_bulk_stage_sync():

  content_summary(source_text, source_title) -> str
    Produce a concise summary of one fetched source document.

  dedup_candidates(candidates) -> list[dict]
    Remove near-duplicate candidates from the pipeline by URL and claim similarity.

  summarize_candidates(plan_mechanism, plan_prior, candidates) -> list[dict]
    Produce citation-grounded source rows from a list of {kind, title, url, claim} candidates.

All functions route through call_bulk_stage() / call_bulk_stage_sync(), which always
dispatch to CRUX_BULK_MODEL — never the judgment model.
"""
from __future__ import annotations

import json
import logging

from app.llm_providers import call_bulk_stage, call_bulk_stage_sync

_log = logging.getLogger(__name__)

_VALID_KINDS = frozenset({"book", "article", "youtube"})


# ---------------------------------------------------------------------------
# Per-source content summary
# ---------------------------------------------------------------------------

_CONTENT_SUMMARY_SYSTEM = """\
You are a research assistant. Produce a brief factual summary of the provided source document.

Return a JSON object with exactly this field:
  "summary": a 1-3 sentence factual summary of the source's main claims and evidence

Return only the JSON object — no markdown fences, no commentary.
"""

_CONTENT_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
    "additionalProperties": False,
}


async def content_summary(source_text: str, source_title: str) -> str:
    """Summarize a source document using CRUX_BULK_MODEL via the provider interface.

    Returns a 1-3 sentence factual summary string.
    """
    user = f"Source title: {source_title}\n\nSource text:\n{source_text[:4000]}"
    result = await call_bulk_stage(
        _CONTENT_SUMMARY_SYSTEM, user, "content_summary", _CONTENT_SUMMARY_SCHEMA
    )
    if isinstance(result, dict):
        return result.get("summary", "")
    return str(result)


def content_summary_sync(source_text: str, source_title: str) -> str:
    """Synchronous version of content_summary."""
    user = f"Source title: {source_title}\n\nSource text:\n{source_text[:4000]}"
    result = call_bulk_stage_sync(
        _CONTENT_SUMMARY_SYSTEM, user, "content_summary", _CONTENT_SUMMARY_SCHEMA
    )
    if isinstance(result, dict):
        return result.get("summary", "")
    return str(result)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

_DEDUP_SYSTEM = """\
You are a research assistant. Given a numbered list of source candidates (each with a URL and \
claim excerpt), identify which entries are near-duplicates of an earlier entry — same URL or \
the same factual claim expressed differently.

Return a JSON object with exactly this field:
  "keep_indices": a list of integer indices (0-based) identifying unique candidates to retain.
    Include the first occurrence of each unique URL/claim and exclude later duplicates.
    Preserve the original order.

Return only the JSON object — no markdown fences, no commentary.
"""

_DEDUP_SCHEMA = {
    "type": "object",
    "properties": {
        "keep_indices": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["keep_indices"],
    "additionalProperties": False,
}


async def dedup_candidates(candidates: list[dict]) -> list[dict]:
    """Remove near-duplicate candidates using CRUX_BULK_MODEL via the provider interface.

    Returns deduplicated list preserving original order.
    Falls back to the original list on error.
    """
    if len(candidates) <= 1:
        return candidates

    lines = "\n".join(
        f"{i}: url={c.get('url', '')}, claim={str(c.get('claim', ''))[:120]}"
        for i, c in enumerate(candidates)
    )
    user = f"Candidates:\n{lines}"

    try:
        result = await call_bulk_stage(_DEDUP_SYSTEM, user, "dedup_output", _DEDUP_SCHEMA)
        if isinstance(result, dict) and "keep_indices" in result:
            indices = sorted(set(i for i in result["keep_indices"] if 0 <= i < len(candidates)))
            return [candidates[i] for i in indices]
    except Exception as exc:
        _log.warning("dedup_candidates: LLM call failed, using all %d candidates: %s", len(candidates), exc)

    return candidates


def dedup_candidates_sync(candidates: list[dict]) -> list[dict]:
    """Synchronous version of dedup_candidates."""
    if len(candidates) <= 1:
        return candidates

    lines = "\n".join(
        f"{i}: url={c.get('url', '')}, claim={str(c.get('claim', ''))[:120]}"
        for i, c in enumerate(candidates)
    )
    user = f"Candidates:\n{lines}"

    try:
        result = call_bulk_stage_sync(_DEDUP_SYSTEM, user, "dedup_output", _DEDUP_SCHEMA)
        if isinstance(result, dict) and "keep_indices" in result:
            indices = sorted(set(i for i in result["keep_indices"] if 0 <= i < len(candidates)))
            return [candidates[i] for i in indices]
    except Exception as exc:
        _log.warning("dedup_candidates_sync: LLM call failed, using all %d candidates: %s", len(candidates), exc)

    return candidates


# ---------------------------------------------------------------------------
# Candidate summarization
# ---------------------------------------------------------------------------

_CANDIDATE_SUMMARIZATION_SYSTEM = """\
You are a research assistant that produces structured, citation-grounded evidence rows.

You will receive:
1. A research plan with a mechanism and prior knowledge.
2. A list of source candidates, each with: kind (book/article/youtube), title, url, and claim.

For each candidate, produce a concise factual claim statement and a verbatim or \
minimally-paraphrased citation drawn directly from the provided claim text.
Omit any item for which you cannot provide a citation directly grounded in the provided source.
If no item can be verified, return an empty sources array.

Return a JSON object with exactly this field:
  "sources": an array of objects, each with:
    kind     — one of: book | article | youtube
    title    — the source title (non-empty)
    url      — the source URL (non-empty)
    claim    — a concise factual claim statement (non-empty)
    citation — a verbatim or minimally-paraphrased quote from the source (non-empty)

Return only the JSON object — no markdown fences, no commentary.
"""

_CANDIDATE_SUMMARIZATION_SCHEMA = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "claim": {"type": "string"},
                    "citation": {"type": "string"},
                },
                "required": ["kind", "title", "url", "claim", "citation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sources"],
    "additionalProperties": False,
}


def _validate_source_rows(rows: list[dict]) -> list[dict]:
    valid = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("kind", "") not in _VALID_KINDS:
            continue
        if not (row.get("title") or "").strip():
            continue
        if not (row.get("url") or "").strip():
            continue
        if not (row.get("claim") or "").strip():
            continue
        if not (row.get("citation") or "").strip():
            continue
        valid.append(row)
    return valid


async def summarize_candidates(
    plan_mechanism: str,
    plan_prior: str,
    candidates: list[dict],
) -> list[dict]:
    """Produce citation-grounded source rows from candidates using CRUX_BULK_MODEL.

    Returns a list of validated {kind, title, url, claim, citation} dicts.
    """
    if not candidates:
        return []

    candidates_json = json.dumps(candidates, indent=2, ensure_ascii=False)
    user = (
        f"Research Plan:\n"
        f"  Mechanism: {plan_mechanism}\n"
        f"  Prior: {plan_prior}\n\n"
        f"Source candidates:\n{candidates_json}"
    )

    result = await call_bulk_stage(
        _CANDIDATE_SUMMARIZATION_SYSTEM, user,
        "candidate_summarization", _CANDIDATE_SUMMARIZATION_SCHEMA,
    )

    if isinstance(result, dict) and "sources" in result:
        return _validate_source_rows(result["sources"])
    return []


def summarize_candidates_sync(
    plan_mechanism: str,
    plan_prior: str,
    candidates: list[dict],
) -> list[dict]:
    """Synchronous version of summarize_candidates."""
    if not candidates:
        return []

    candidates_json = json.dumps(candidates, indent=2, ensure_ascii=False)
    user = (
        f"Research Plan:\n"
        f"  Mechanism: {plan_mechanism}\n"
        f"  Prior: {plan_prior}\n\n"
        f"Source candidates:\n{candidates_json}"
    )

    result = call_bulk_stage_sync(
        _CANDIDATE_SUMMARIZATION_SYSTEM, user,
        "candidate_summarization", _CANDIDATE_SUMMARIZATION_SCHEMA,
    )

    if isinstance(result, dict) and "sources" in result:
        return _validate_source_rows(result["sources"])
    return []
