"""Embedding service for case semantic similarity (issue #68).

Calls the Anthropic messages API to produce a fixed-dimension float vector
for a given text. Vectors are stored in case_embedding and reused on every
related-case query without additional API calls.

Configuration:
  EMBEDDING_MODEL (str, default "claude-haiku-4-5-20251001"):
    Model identifier used for embedding generation. Stored in model_version
    column to enable future re-embedding when the model changes.

  ANTHROPIC_API_KEY: required for production use.
"""
import json
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app import models

EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "claude-haiku-4-5-20251001")
EMBEDDING_DIM: int = 256

_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_API_URL = "https://api.anthropic.com/v1/messages"

_SYSTEM = (
    "You are a semantic embedding assistant. "
    "When given a text, respond ONLY with a JSON array of exactly "
    f"{EMBEDDING_DIM} floating point numbers between -1 and 1 that captures "
    "the semantic meaning of the text. Output nothing else."
)


class EmbeddingError(Exception):
    """Raised when the embedding API call fails or returns unparseable output."""


def get_embedding(text: str) -> list[float]:
    """Return a float embedding vector for the given text via the Anthropic API."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    if not _ANTHROPIC_API_KEY:
        raise EmbeddingError("ANTHROPIC_API_KEY is not configured")

    payload = {
        "model": EMBEDDING_MODEL,
        "max_tokens": 2048,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": text.strip()}],
    }
    headers = {
        "x-api-key": _ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        # Structured per-phase timeouts: connect 10s (fast-fail on routing failures),
        # read 30s (room for a multi-token embedding response), write/pool 5s.
        with httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0, read=30.0, write=5.0, pool=5.0)
        ) as client:
            resp = client.post(_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise EmbeddingError(f"Anthropic API HTTP error {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise EmbeddingError(f"Anthropic API request failed: {exc}") from exc

    try:
        raw = resp.json()["content"][0]["text"].strip()
        vector = json.loads(raw)
        if not isinstance(vector, list) or len(vector) != EMBEDDING_DIM:
            raise ValueError(f"Expected list of {EMBEDDING_DIM}, got {type(vector).__name__} len={len(vector) if isinstance(vector, list) else 'N/A'}")
        return [float(x) for x in vector]
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise EmbeddingError(f"Failed to parse embedding response: {exc}") from exc


def upsert_embedding(case_id: str, text: str, db: Session) -> None:
    """Compute and store embedding for a case. Idempotent (upsert by case_id)."""
    vector = get_embedding(text)

    existing = (
        db.query(models.CaseEmbedding)
        .filter(models.CaseEmbedding.case_id == case_id)
        .first()
    )
    now = datetime.now(tz=timezone.utc)

    if existing:
        existing.embedding = json.dumps(vector)
        existing.model_version = EMBEDDING_MODEL
        existing.created_at = now
    else:
        emb = models.CaseEmbedding(
            case_id=case_id,
            embedding=json.dumps(vector),
            model_version=EMBEDDING_MODEL,
            created_at=now,
        )
        db.add(emb)

    db.commit()
