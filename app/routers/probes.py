"""Probes API router — status transitions and due-date management."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

# Only the designed→running transition is supported here.
# The running→closed transition is owned by the Verdict gate.
_VALID_TRANSITIONS = {
    "designed": "running",
}


class ProbeStatusRequest(BaseModel):
    status: str


@router.patch("/probes/{probe_id}/status")
def update_probe_status(
    probe_id: str,
    body: ProbeStatusRequest,
    db: Session = Depends(get_db),
):
    probe = db.query(models.Probe).filter(models.Probe.id == probe_id).first()
    if probe is None:
        raise HTTPException(status_code=404, detail="Probe not found")

    allowed_next = _VALID_TRANSITIONS.get(probe.status)
    if allowed_next != body.status:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid transition: {probe.status!r} → {body.status!r}; "
                "only 'designed' → 'running' is allowed"
            ),
        )

    probe.status = body.status
    db.commit()
    db.refresh(probe)

    return {"id": probe.id, "status": probe.status}


class ProbeDueDateRequest(BaseModel):
    due_date: datetime.date | None


@router.patch("/probes/{probe_id}/due-date")
def update_probe_due_date(
    probe_id: str,
    body: ProbeDueDateRequest,
    db: Session = Depends(get_db),
):
    probe = db.query(models.Probe).filter(models.Probe.id == probe_id).first()
    if probe is None:
        raise HTTPException(status_code=404, detail="Probe not found")

    probe.due_date = body.due_date
    db.commit()
    db.refresh(probe)

    return {
        "id": probe.id,
        "due_date": str(probe.due_date) if probe.due_date else None,
    }
