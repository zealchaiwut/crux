"""Related-case matching API router.

GET /api/cases/{case_id}/related
  Returns a ranked list of prior Cases with logged Verdicts that are
  semantically similar to the given Case.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.related_cases import find_related_cases

router = APIRouter(prefix="/api")


@router.get("/cases/{case_id}/related")
def get_related_cases(case_id: str, db: Session = Depends(get_db)):
    matches = find_related_cases(case_id, db)
    if matches is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"matches": matches}
