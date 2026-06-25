"""Source verification pipeline: fetch → Claude analysis → DB write.

The pipeline is dependency-injected so that tests can supply mock fetch and
analyze callables without any real HTTP or Claude API calls.

Usage (production)::

    from app.research.fetchers import ArticleReaderFetcher
    from app.services.source_verification import run_verification_pipeline

    def fetch(url: str) -> str:
        doc = ArticleReaderFetcher(budget=1).fetch(url)
        return doc.text

    def analyze(content: str, claim: str) -> dict:
        # call claude_cli.call_claude(...) and parse JSON response
        ...

    record = run_verification_pipeline(db, source_id, fetch, analyze)

Usage (tests)::

    def mock_fetch(url): return "article content..."
    def mock_analyze(content, claim): return {"verdict": "supports", "summary": "..."}
    record = run_verification_pipeline(session, source_id, mock_fetch, mock_analyze)
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app import models
from app.research.types import FetchBlockedError, FetchEmptyContentError, FetchTimeoutError


def run_verification_pipeline(
    db: Session,
    source_id: str,
    fetch_fn: Callable[[str], str],
    analyze_fn: Callable[[str, str], dict],
) -> models.SourceVerification:
    """Run the verification pipeline and persist the result.

    Args:
        db: SQLAlchemy session (caller manages commit boundary).
        source_id: PK of the ``source`` row to verify.
        fetch_fn: ``(url) -> content_str``; raise FetchBlockedError/
                  FetchTimeoutError/FetchEmptyContentError on failure.
        analyze_fn: ``(content, claim) -> {"verdict": ..., "summary": ...}``;
                    verdict must be one of 'supports' | 'contradicts' | 'unverified'.

    Returns:
        The newly created and committed ``SourceVerification`` record.

    Raises:
        ValueError: if the source_id is not found in the DB.
    """
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if source is None:
        raise ValueError(f"Source not found: {source_id}")

    try:
        content = fetch_fn(source.url or "")
    except (FetchBlockedError, FetchTimeoutError, FetchEmptyContentError) as exc:
        record = models.SourceVerification(
            source_id=source_id,
            verdict="unverified",
            reason=str(exc),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    result = analyze_fn(content, source.claim or "")
    record = models.SourceVerification(
        source_id=source_id,
        verdict=result.get("verdict", "unverified"),
        summary=result.get("summary"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
