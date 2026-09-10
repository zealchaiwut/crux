"""Service that fetches and stores raw content and a Claude-generated summary for a source.

Routing:
  - YouTube URLs / kind="youtube" → yt_fetch_fn
  - All other article/web sources   → article_fetch_fn

On fetch failure (blocked, paywalled, geo-restricted, timeout, missing transcript)
both extracted_content and content_summary remain NULL. The failure reason is
logged so it can be retrieved from server logs or surfaced to the caller.

The 50,000-character cap is enforced before storage; truncated content carries
a "[TRUNCATED]" sentinel appended at the cut point.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

from sqlalchemy.orm import Session

from app import models
from app.research.types import (
    ArticleDocument,
    FetchBlockedError,
    FetchEmptyContentError,
    FetchTimeoutError,
)

logger = logging.getLogger(__name__)

_CONTENT_CAP = 50_000
_TRUNCATED_SENTINEL = "[TRUNCATED]"

_YT_PATTERN = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)

_SUMMARY_SYSTEM_PROMPT = (
    "You are a research assistant. Your task is to write a concise, neutral summary "
    "of what a source document says — its substance, claims, and key points. "
    "Do NOT evaluate whether the content supports or contradicts any particular claim. "
    "Do NOT use words like 'supports', 'contradicts', 'partially_supports', or 'unverified'. "
    "Write 2-4 sentences describing the source's own content and what it covers."
)


def _cap_content(text: str) -> str:
    if len(text) <= _CONTENT_CAP:
        return text
    cut = _CONTENT_CAP - len(_TRUNCATED_SENTINEL)
    return text[:cut] + _TRUNCATED_SENTINEL


def _is_youtube(source: models.Source) -> bool:
    if source.kind == "youtube":
        return True
    if source.url and _YT_PATTERN.search(source.url):
        return True
    return False


def _default_article_fetcher(url: str) -> ArticleDocument | None:
    from app.research.fetchers import ArticleReaderFetcher
    return ArticleReaderFetcher(budget=1).fetch(url)


def _default_yt_fetcher(url: str) -> ArticleDocument | None:
    from app.research.fetchers import YouTubeTranscriptFetcher
    return YouTubeTranscriptFetcher(budget=1).fetch(url)


def _default_summarize(content: str) -> str:
    from app.claude_cli import complete_sync
    user_prompt = f"Source content:\n\n{content[:8000]}"
    return complete_sync(_SUMMARY_SYSTEM_PROMPT, user_prompt)


def fetch_and_store_content(
    db: Session,
    source: models.Source,
    *,
    article_fetch_fn: Callable[[str], ArticleDocument | None] | None = None,
    yt_fetch_fn: Callable[[str], ArticleDocument | None] | None = None,
    summarize_fn: Callable[[str], str] | None = None,
) -> None:
    """Fetch source content, cap it, summarize it, and persist on the source row.

    On any fetch failure both fields stay None and the reason is logged.
    On success ``extracted_content`` and ``content_summary`` are written and committed.
    """
    if article_fetch_fn is None:
        article_fetch_fn = _default_article_fetcher
    if yt_fetch_fn is None:
        yt_fetch_fn = _default_yt_fetcher
    if summarize_fn is None:
        summarize_fn = _default_summarize

    url = source.url or ""

    try:
        if _is_youtube(source):
            doc = yt_fetch_fn(url)
        else:
            doc = article_fetch_fn(url)
    except (FetchBlockedError, FetchTimeoutError, FetchEmptyContentError) as exc:
        logger.warning("fetch_content: fetch failed for source %s: %s", source.id, exc)
        db.commit()
        return
    except Exception as exc:
        logger.warning("fetch_content: unexpected fetch error for source %s: %s", source.id, exc)
        db.commit()
        return

    if doc is None:
        logger.info("fetch_content: no content returned for source %s (blocked or unavailable)", source.id)
        db.commit()
        return

    raw_text = doc.text or ""
    if not raw_text.strip():
        logger.info("fetch_content: empty content for source %s", source.id)
        db.commit()
        return

    capped = _cap_content(raw_text)

    try:
        summary = summarize_fn(capped)
    except Exception as exc:
        logger.warning("fetch_content: summarization failed for source %s: %s", source.id, exc)
        summary = None

    source.extracted_content = capped
    source.content_summary = summary
    db.commit()
