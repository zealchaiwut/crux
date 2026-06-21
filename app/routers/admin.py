"""Admin API router.

GET /api/admin/reindex
  Recomputes embeddings for all cases. Requires a valid session cookie.
  Returns { reindexed: N, errors: M }.
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app import models
from app.config import AUTH_SECRET
from app.auth import verify_session_cookie
from app.db import get_db
from app.services import embeddings as _emb
from app.services.embeddings import upsert_case_embedding, EMBEDDING_MODEL_VERSION

router = APIRouter(prefix="/api/admin")
logger = logging.getLogger(__name__)


def _require_admin(request: Request) -> None:
    token = request.cookies.get("session", "")
    if not token or not verify_session_cookie(token, AUTH_SECRET):
        raise_401 = True
    else:
        raise_401 = False
    if raise_401:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/reindex")
def reindex_all_cases(
    request: Request,
    db: Session = Depends(get_db),
):
    """Recompute embeddings for all cases. Returns { reindexed, errors }."""
    _require_admin(request)

    cases = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans))
        .all()
    )

    reindexed = 0
    errors = 0

    for case in cases:
        try:
            vector = _emb.compute_case_embedding(case)
            upsert_case_embedding(case.id, vector, EMBEDDING_MODEL_VERSION, db)
            reindexed += 1
        except Exception:
            logger.exception("Failed to reindex embedding for case %s", case.id)
            errors += 1

    return {"reindexed": reindexed, "errors": errors}
