"""Service that verifies whether a source URL's content supports a stated claim.

Routing:
  - YouTube URLs  → YouTubeTranscriptFetcher
  - All other URLs → ArticleReaderFetcher

On fetch failure (blocked, timeout, empty, unavailable transcript) the service
returns support_status="unverified" with a rationale that cites the failure
reason verbatim — it never infers or hallucinates content.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from app.research.fetchers import ArticleReaderFetcher, YouTubeTranscriptFetcher
from app.research.types import (
    FetchBlockedError,
    FetchEmptyContentError,
    FetchTimeoutError,
)

logger = logging.getLogger(__name__)

_YT_PATTERN = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)

SUPPORT_STATUSES = frozenset({"supports", "partially_supports", "contradicts", "unverified"})

_SYSTEM_PROMPT = (
    "You are a fact-checking assistant. Analyze whether the provided source content "
    "supports, partially supports, contradicts, or is unrelated to the stated claim.\n\n"
    "Respond with ONLY a JSON object in this exact format:\n"
    '{"support_status": "<supports|partially_supports|contradicts|unverified>", '
    '"support_rationale": "<brief explanation citing specific content from the source>"}\n\n'
    "Definitions:\n"
    "  supports          — content clearly and directly validates the claim\n"
    "  partially_supports — content addresses some but not all aspects, or gives weak/indirect support\n"
    "  contradicts       — content clearly refutes or is inconsistent with the claim\n"
    "  unverified        — content is unrelated, insufficient, or the relationship cannot be determined"
)


def _default_classify(content: str, claim: str) -> dict[str, str]:
    from app.claude_cli import complete_sync

    user_prompt = f"Claim: {claim}\n\nSource content:\n{content}"
    raw = complete_sync(_SYSTEM_PROMPT, user_prompt)
    try:
        result = json.loads(raw)
        status = result.get("support_status", "unverified")
        if status not in SUPPORT_STATUSES:
            status = "unverified"
        rationale = str(result.get("support_rationale") or "No rationale provided.")
        return {"support_status": status, "support_rationale": rationale}
    except (json.JSONDecodeError, AttributeError):
        return {
            "support_status": "unverified",
            "support_rationale": raw or "Claude classification returned no output.",
        }


def _get_url(source: Any) -> str:
    if isinstance(source, dict):
        return source["url"]
    return source.url


def _get_claim(source: Any) -> str:
    if isinstance(source, dict):
        return source["claim"]
    return source.claim


def verify_source(
    source: Any,
    *,
    article_fetcher: ArticleReaderFetcher | None = None,
    yt_fetcher: YouTubeTranscriptFetcher | None = None,
    classify_fn: Callable[[str, str], dict[str, str]] | None = None,
) -> dict[str, str]:
    """Verify whether a source's content supports the stated claim.

    Args:
        source: Object or mapping with at least ``url`` and ``claim`` fields.
        article_fetcher: ``ArticleReaderFetcher`` instance; defaults to one with budget=1.
        yt_fetcher: ``YouTubeTranscriptFetcher`` instance; defaults to one with budget=1.
        classify_fn: ``(content, claim) -> {support_status, support_rationale}``.
            Defaults to a Claude-backed classifier via :func:`app.claude_cli.complete_sync`.

    Returns:
        ``{"support_status": str, "support_rationale": str}`` where ``support_status``
        is one of ``supports``, ``partially_supports``, ``contradicts``, ``unverified``.
    """
    if classify_fn is None:
        classify_fn = _default_classify

    url = _get_url(source)
    claim = _get_claim(source)

    if _YT_PATTERN.search(url):
        fetcher = yt_fetcher or YouTubeTranscriptFetcher(budget=1)
        try:
            doc = fetcher.fetch(url)
        except Exception as exc:
            return {
                "support_status": "unverified",
                "support_rationale": f"Fetch failed: {exc}",
            }
        if doc is None:
            return {
                "support_status": "unverified",
                "support_rationale": (
                    "YouTube transcript unavailable — captions disabled, "
                    "video private/deleted, or age-gated."
                ),
            }
        content = doc.text
    else:
        fetcher = article_fetcher or ArticleReaderFetcher(budget=1)
        try:
            doc = fetcher.fetch(url)
        except (FetchBlockedError, FetchTimeoutError, FetchEmptyContentError) as exc:
            return {
                "support_status": "unverified",
                "support_rationale": str(exc),
            }
        except Exception as exc:
            return {
                "support_status": "unverified",
                "support_rationale": f"Fetch failed: {exc}",
            }
        content = doc.text

    if not content or len(content.strip()) < 10:
        return {
            "support_status": "unverified",
            "support_rationale": "Source returned no extractable content.",
        }

    return classify_fn(content, claim)
