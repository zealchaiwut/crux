"""Verdicts list API router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, contains_eager, joinedload

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

_VALID_OUTCOMES = {"confirmed", "killed", "inconclusive"}


@router.get("/verdicts")
def list_verdicts(
    outcome: str | None = Query(default=None),
    q: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
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

    search_term = keyword or q

    if search_term:
        search_pattern = f"%{search_term.lower()}%"
        query = (
            db.query(models.Verdict)
            .join(models.Probe, models.Verdict.probe_id == models.Probe.id)
            .join(models.Case, models.Probe.case_id == models.Case.id)
            .options(
                contains_eager(models.Verdict.probe).contains_eager(models.Probe.case)
            )
            .filter(
                or_(
                    func.lower(models.Verdict.notes).like(search_pattern),
                    func.lower(models.Case.sharpened).like(search_pattern),
                )
            )
            .order_by(models.Verdict.decided_at.desc())
        )
    else:
        query = (
            db.query(models.Verdict)
            .options(
                joinedload(models.Verdict.probe).joinedload(models.Probe.case)
            )
            .order_by(models.Verdict.decided_at.desc())
        )

    if outcome is not None:
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
            "created_at": str(v.decided_at or v.created_at) if (v.decided_at or v.created_at) else None,
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
