"""Related-case matching service using Claude embedding vectors (issue #68).

Finds prior Cases with logged Verdicts whose semantic embedding is similar
to a given Case's embedding. Embeddings are pre-computed and stored in the
case_embedding table; no external vector database is used.

Configuration:
  RELATED_CASE_SIMILARITY_THRESHOLD (float, default 0.1):
    Minimum cosine similarity score for a case to be included in results.
    Set via environment variable. Filter with a higher value to reduce
    false positives without a code change.
"""

import json
import math
import os

from sqlalchemy.orm import Session, joinedload

from app import models
from app.services.embeddings import get_embedding

SIMILARITY_THRESHOLD: float = float(
    os.environ.get("RELATED_CASE_SIMILARITY_THRESHOLD", "0.1")
)

_SNIPPET_MAX_LEN = 120


def _snippet(sharpened: str) -> str:
    if len(sharpened) <= _SNIPPET_MAX_LEN:
        return sharpened
    return sharpened[:_SNIPPET_MAX_LEN].rsplit(" ", 1)[0] + "…"


def _cosine_vec(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors in-process."""
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(x * x for x in v1))
    mag2 = math.sqrt(sum(x * x for x in v2))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot / (mag1 * mag2)


def _load_embedding(case_id: str, db: Session) -> list[float] | None:
    """Load a stored embedding vector from case_embedding. Returns None if absent."""
    row = (
        db.query(models.CaseEmbedding)
        .filter(models.CaseEmbedding.case_id == case_id)
        .first()
    )
    if row is None:
        return None
    try:
        return json.loads(row.embedding)
    except (json.JSONDecodeError, TypeError):
        return None


def _candidates_with_verdicts(db: Session) -> list[models.Case]:
    """Load all cases that have at least one verdict, with plans and probes eager-loaded."""
    return (
        db.query(models.Case)
        .join(models.Probe, models.Probe.case_id == models.Case.id)
        .join(models.Verdict, models.Verdict.probe_id == models.Probe.id)
        .options(
            joinedload(models.Case.plans),
            joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
        )
        .all()
    )


def _score_candidates(
    query_vec: list[float],
    candidates: list[models.Case],
    exclude_id: str | None,
    db: Session,
    threshold: float,
) -> list[dict]:
    """Score candidate cases by cosine similarity to query_vec. Returns sorted results."""
    seen: set[str] = set()
    results: list[dict] = []

    for case in candidates:
        if case.id in seen:
            continue
        if exclude_id and case.id == exclude_id:
            seen.add(case.id)
            continue
        if not case.sharpened or not case.sharpened.strip():
            seen.add(case.id)
            continue

        probe = case.probes[0] if case.probes else None
        if probe is None:
            seen.add(case.id)
            continue
        verdict = probe.verdicts[0] if probe.verdicts else None
        if verdict is None:
            seen.add(case.id)
            continue

        cand_vec = _load_embedding(case.id, db)
        if cand_vec is None:
            seen.add(case.id)
            continue

        score = _cosine_vec(query_vec, cand_vec)
        if score >= threshold:
            results.append({
                "case_id": case.id,
                "sharpened_snippet": _snippet(case.sharpened),
                "verdict_outcome": verdict.outcome,
                "deciding_metric": probe.target_metric or "",
                "similarity_score": round(score, 6),
            })
        seen.add(case.id)

    results.sort(key=lambda r: r["similarity_score"], reverse=True)
    return results


def find_related_by_text(
    sharpened: str,
    mechanisms: list[str],
    db: Session,
    threshold: float | None = None,
) -> list[dict]:
    """Return ranked related cases given sharpened text and mechanisms.

    Used by the New Case flow before a case is persisted. Calls the embedding
    API once for the query text; reads stored embeddings for candidates.
    Returns [] if sharpened is empty or no candidates score above threshold.
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    if not sharpened or not sharpened.strip():
        return []

    parts = [sharpened] + (mechanisms or [])
    query_text = " ".join(p for p in parts if p)
    query_vec = get_embedding(query_text)

    candidates = _candidates_with_verdicts(db)
    return _score_candidates(query_vec, candidates, exclude_id=None, db=db, threshold=threshold)


def find_related_cases(
    case_id: str,
    db: Session,
    threshold: float | None = None,
) -> list[dict] | None:
    """Return ranked related cases for the given case_id.

    Returns None if the case does not exist (signals 404 to the router).
    Returns [] if:
    - The case has no stored embedding (fallback — backfill not yet run).
    - No prior cases with verdicts exist.
    - No candidates score above the threshold.

    Does NOT call the embedding API; reads from case_embedding only.
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    query_case = (
        db.query(models.Case)
        .filter(models.Case.id == case_id)
        .first()
    )
    if query_case is None:
        return None  # signals 404

    query_vec = _load_embedding(case_id, db)
    if query_vec is None:
        return []  # graceful fallback — no embedding stored yet

    candidates = _candidates_with_verdicts(db)
    return _score_candidates(query_vec, candidates, exclude_id=case_id, db=db, threshold=threshold)
