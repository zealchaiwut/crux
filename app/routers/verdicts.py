"""Verdicts API router.

GET /api/verdicts          — all Verdict rows, newest first, with Case info.
GET /api/verdicts?outcome= — filter by outcome (confirmed|killed|inconclusive|all).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

_VALID_OUTCOMES = {"confirmed", "killed", "inconclusive", "all"}


@router.get("/verdicts")
def list_verdicts(outcome: Optional[str] = None, db: Session = Depends(get_db)):
    if outcome is not None and outcome not in _VALID_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"outcome must be one of {sorted(_VALID_OUTCOMES)}",
        )

    query = (
        db.query(models.Verdict)
        .join(models.Probe, models.Verdict.probe_id == models.Probe.id)
        .join(models.Case, models.Probe.case_id == models.Case.id)
        .options(
            joinedload(models.Verdict.probe).joinedload(models.Probe.case)
        )
        .order_by(models.Verdict.decided_at.desc())
    )

    if outcome and outcome != "all":
        query = query.filter(models.Verdict.outcome == outcome)

    verdicts = query.all()

    result = []
    for v in verdicts:
        probe = v.probe
        case = probe.case if probe else None
        result.append({
            "id": v.id,
            "outcome": v.outcome,
            "notes": v.notes or "",
            "decided_at": str(v.decided_at) if v.decided_at else None,
            "decided_metric": probe.target_metric or "" if probe else "",
            "case_id": case.id if case else None,
            "case_title": (case.sharpened or case.raw_problem) if case else "",
        })

    return {"verdicts": result}
