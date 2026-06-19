"""Related-case matching API router.

GET /api/cases/{case_id}/related
  Returns a ranked list of prior Cases with logged Verdicts that are
  semantically similar to the given Case.

POST /api/cases/related-text
  Returns a ranked list of related Cases given raw sharpened text and
  mechanisms, without requiring an existing Case record. Used by the
  New Case creation flow before a Case is persisted.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.related_cases import find_related_cases, find_related_by_text

router = APIRouter(prefix="/api")


class RelatedTextRequest(BaseModel):
    sharpened: str
    mechanisms: Optional[List[str]] = None


@router.post("/cases/related-text")
def get_related_by_text(body: RelatedTextRequest, db: Session = Depends(get_db)):
    matches = find_related_by_text(
        sharpened=body.sharpened,
        mechanisms=body.mechanisms or [],
        db=db,
    )
    return {"matches": matches}


@router.get("/cases/{case_id}/related")
def get_related_cases(case_id: str, db: Session = Depends(get_db)):
    matches = find_related_cases(case_id, db)
    if matches is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"matches": matches}
