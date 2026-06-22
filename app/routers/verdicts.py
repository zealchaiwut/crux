"""Verdicts list API router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

_VALID_OUTCOMES = {"confirmed", "killed", "inconclusive"}


@router.get("/verdicts")
def list_verdicts(
    outcome: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if outcome is not None and outcome not in _VALID_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid outcome {outcome!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_OUTCOMES))}."
            ),
        )

    query = (
        db.query(models.Verdict)
        .options(
            joinedload(models.Verdict.probe).joinedload(models.Probe.case),
        )
        .order_by(models.Verdict.decided_at.desc())
    )

    if outcome is not None:
        query = query.filter(models.Verdict.outcome == outcome)

    verdicts = query.all()

    if q:
        keyword = q.lower()
        verdicts = [
            v for v in verdicts
            if (v.notes and keyword in v.notes.lower())
            or (v.probe and v.probe.case and v.probe.case.sharpened
                and keyword in v.probe.case.sharpened.lower())
        ]

    result = []
    for v in verdicts:
        probe = v.probe
        case = probe.case if probe else None
        result.append({
            "id": v.id,
            "outcome": v.outcome,
            "notes": v.notes or "",
            "created_at": str(v.decided_at) if v.decided_at else None,
            "probe": {
                "type": probe.type if probe else None,
                "target_metric": probe.target_metric or "" if probe else "",
            },
            "case": {
                "id": case.id if case else None,
                "sharpened_snippet": case.sharpened or "" if case else "",
            },
        })

    return result
