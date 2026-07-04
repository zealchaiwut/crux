"""Action plan gate router.

GET /api/cases/{case_id}/action-plan enforces the provisional/final gate:
  - 404 if case not found
  - 403 if no probe has a verdict yet (locked state)
  - 200 with action_plan_state ('provisional' or 'final') otherwise
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models
from app.db import get_db
from app.routers.cases import compute_action_plan_state, _STANDING_BY_RANK

router = APIRouter(prefix="/api")


@router.get("/cases/{case_id}/action-plan")
def get_action_plan(case_id: str, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(
            joinedload(models.Case.plans),
            joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
        )
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    state = compute_action_plan_state(case.probes)
    if state == "locked":
        raise HTTPException(
            status_code=403,
            detail="Action plan is locked until at least one probe verdict is logged.",
        )

    plans_out = [
        {
            "id": p.id,
            "label": p.label,
            "name": p.name or f"Plan {p.label}",
            "mechanism": p.mechanism or "",
            "current_rank": p.current_rank,
            "standing": p.standing,
            "bar_weight": _STANDING_BY_RANK.get(p.current_rank or 99, 0.15),
        }
        for p in sorted(case.plans, key=lambda p: p.current_rank or 99)
    ]

    verdicted_probes = [
        {
            "id": p.id,
            "horizon": p.horizon,
            "status": p.status,
            "target_metric": p.target_metric or "",
        }
        for p in case.probes
        if p.status in {"confirmed", "killed", "inconclusive"}
    ]

    return {
        "action_plan_state": state,
        "plans": plans_out,
        "verdicted_probes": verdicted_probes,
    }
