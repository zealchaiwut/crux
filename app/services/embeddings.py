"""Embedding computation and storage for cases.

Computes a TF-IDF vector over a case's sharpened statement and plan mechanisms,
serialises it to JSON, and persists it in the case_embedding table.

EMBEDDING_MODEL_VERSION: bump this string whenever the embedding algorithm
changes so that stale records can be detected and reindexed.
"""
import json
import math
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models

EMBEDDING_MODEL_VERSION = "tf-idf-v1"

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


def _dict_to_list(vec: dict[str, float]) -> list[float]:
    """Stable sorted list representation of a TF vector."""
    return [v for _, v in sorted(vec.items())]


def compute_case_embedding(case: models.Case) -> list[float]:
    """Compute a TF-IDF embedding vector for a case."""
    parts = [case.sharpened or case.raw_problem or ""]
    for plan in (case.plans or []):
        if plan.mechanism:
            parts.append(plan.mechanism)
    text = " ".join(p for p in parts if p)
    tokens = _tokenize(text)
    vec = _tf_vector(tokens)
    return _dict_to_list(vec)


def upsert_case_embedding(
    case_id: str,
    vector: list[float],
    model_version: str,
    db: Session,
) -> models.CaseEmbedding:
    """Insert or update the embedding record for a case."""
    emb = db.query(models.CaseEmbedding).filter_by(case_id=case_id).first()
    now = datetime.now(tz=timezone.utc)
    if emb is None:
        emb = models.CaseEmbedding(
            case_id=case_id,
            vector=json.dumps(vector),
            model_version=model_version,
            updated_at=now,
        )
        db.add(emb)
    else:
        emb.vector = json.dumps(vector)
        emb.model_version = model_version
        emb.updated_at = now
    db.commit()
    db.refresh(emb)
    return emb


def refresh_case_embedding(case: models.Case, db: Session) -> models.CaseEmbedding:
    """Recompute and persist the embedding for a case."""
    vector = compute_case_embedding(case)
    return upsert_case_embedding(case.id, vector, EMBEDDING_MODEL_VERSION, db)
