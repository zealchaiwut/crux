"""Backfill script: populate case_embedding for all pre-existing cases (issue #68).

Usage:
    python -m scripts.backfill_embeddings

Idempotent: cases that already have a case_embedding row are skipped.
Logs progress to stdout. Exits with code 0 on success, 1 on error.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app import models
from app.services.embeddings import get_embedding, EMBEDDING_MODEL

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def backfill(db) -> dict:
    """Embed all cases that have no case_embedding row.

    Returns {"processed": N, "skipped": M} where:
      processed — number of new embeddings inserted
      skipped   — number of cases already embedded (skipped)
    """
    all_cases = db.query(models.Case).all()
    processed = 0
    skipped = 0

    for case in all_cases:
        existing = (
            db.query(models.CaseEmbedding)
            .filter(models.CaseEmbedding.case_id == case.id)
            .first()
        )
        if existing is not None:
            log.info("SKIP %s (already embedded with %s)", case.id, existing.model_version)
            skipped += 1
            continue

        text = case.sharpened or case.raw_problem
        if not text or not text.strip():
            log.warning("SKIP %s (no text to embed)", case.id)
            skipped += 1
            continue

        try:
            vector = get_embedding(text)
        except Exception as exc:
            log.error("ERROR %s: %s", case.id, exc)
            skipped += 1
            continue

        emb = models.CaseEmbedding(
            case_id=case.id,
            embedding=json.dumps(vector),
            model_version=EMBEDDING_MODEL,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(emb)
        db.commit()
        log.info("EMBEDDED %s", case.id)
        processed += 1

    log.info("Backfill complete: %d processed, %d skipped", processed, skipped)
    return {"processed": processed, "skipped": skipped}


def main() -> None:
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        log.error("DATABASE_URL is not set")
        sys.exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = backfill(db)
        print(json.dumps(result))
    except Exception as exc:
        log.error("Backfill failed: %s", exc)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
