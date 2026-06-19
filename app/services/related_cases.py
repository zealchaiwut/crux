"""Related-case matching service.

Finds prior Cases with logged Verdicts whose sharpened statements and plan
mechanisms are semantically similar to a given Case.

Similarity method: TF cosine similarity over combined text
(sharpened statement + all plan mechanisms). This is a lightweight
bag-of-words approach that runs entirely in-process with no external API
calls, making it suitable for test environments and keeping latency well
under the 3s target for 1,000-row corpora.

To swap in an embedding model or LLM-based comparison, replace the
`_compute_similarity` function with your preferred implementation.

Configuration:
  RELATED_CASE_SIMILARITY_THRESHOLD (float, default 0.1):
    Minimum cosine similarity score for a case to be included in results.
    Set via environment variable. Filter with a higher value to reduce
    false positives without a code change.
"""

import math
import os
import re

from sqlalchemy.orm import Session, joinedload

from app import models

SIMILARITY_THRESHOLD: float = float(
    os.environ.get("RELATED_CASE_SIMILARITY_THRESHOLD", "0.1")
)

_SNIPPET_MAX_LEN = 120
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "this", "that", "these", "those",
    "it", "its", "i", "my", "me", "we", "our", "you", "your", "he", "she",
    "they", "their", "not", "no", "as", "if", "than", "so", "also", "due",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z]+", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _tf_vector(tokens: list[str]) -> dict[str, float]:
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: count / total for t, count in freq.items()}


def _cosine(v1: dict[str, float], v2: dict[str, float]) -> float:
    if not v1 or not v2:
        return 0.0
    common = set(v1) & set(v2)
    if not common:
        return 0.0
    dot = sum(v1[t] * v2[t] for t in common)
    mag1 = math.sqrt(sum(x * x for x in v1.values()))
    mag2 = math.sqrt(sum(x * x for x in v2.values()))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot / (mag1 * mag2)


def _build_text(sharpened: str, mechanisms: list[str]) -> str:
    parts = [sharpened] + mechanisms
    return " ".join(p for p in parts if p)


def _snippet(sharpened: str) -> str:
    if len(sharpened) <= _SNIPPET_MAX_LEN:
        return sharpened
    return sharpened[:_SNIPPET_MAX_LEN].rsplit(" ", 1)[0] + "…"


def find_related_cases(
    case_id: str,
    db: Session,
    threshold: float | None = None,
) -> list[dict]:
    """Return ranked related cases for the given case_id.

    Returns an empty list if:
    - The case does not exist.
    - The case has no sharpened statement.
    - No prior cases with verdicts exist.
    - No candidates score above the threshold.
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    query_case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans))
        .filter(models.Case.id == case_id)
        .first()
    )
    if query_case is None:
        return None  # signals 404

    if not query_case.sharpened or not query_case.sharpened.strip():
        return []

    query_mechs = [p.mechanism or "" for p in query_case.plans if p.mechanism]
    query_text = _build_text(query_case.sharpened, query_mechs)
    query_vec = _tf_vector(_tokenize(query_text))

    # Load all cases (excluding the query case) that have at least one verdict,
    # fetching plans and probe→verdicts in a single joined query.
    candidates = (
        db.query(models.Case)
        .join(models.Probe, models.Probe.case_id == models.Case.id)
        .join(models.Verdict, models.Verdict.probe_id == models.Probe.id)
        .filter(models.Case.id != case_id)
        .options(
            joinedload(models.Case.plans),
            joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
        )
        .all()
    )

    # Deduplicate: a case may have multiple probes/verdicts; keep one entry.
    seen: set[str] = set()
    results: list[dict] = []

    for case in candidates:
        if case.id in seen:
            continue
        if not case.sharpened or not case.sharpened.strip():
            continue

        probe = case.probes[0] if case.probes else None
        if probe is None:
            continue
        verdict = probe.verdicts[0] if probe.verdicts else None
        if verdict is None:
            continue

        mechs = [p.mechanism or "" for p in case.plans if p.mechanism]
        cand_text = _build_text(case.sharpened, mechs)
        cand_vec = _tf_vector(_tokenize(cand_text))
        score = _cosine(query_vec, cand_vec)

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
