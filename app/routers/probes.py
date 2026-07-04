"""Probes API router — status transitions and per-probe verdict logging."""
import uuid as _uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

# Only the designed→running transition is supported here.
# The running→closed transition is owned by the Verdict gate.
_VALID_TRANSITIONS = {
    "designed": "running",
}

_VALID_OUTCOMES = {"confirmed", "killed", "inconclusive"}


class ProbeStatusRequest(BaseModel):
    status: str


class ProbeVerdictRequest(BaseModel):
    outcome: str
    notes: str

    @field_validator("outcome")
    @classmethod
    def outcome_valid(cls, v: str) -> str:
        if v not in _VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome {v!r}. Must be one of: "
                + ", ".join(sorted(_VALID_OUTCOMES))
            )
        return v

    @field_validator("notes")
    @classmethod
    def notes_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("notes must not be empty")
        return v


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


@router.post("/probes/{probe_id}/verdict")
def log_probe_verdict(
    probe_id: str,
    body: ProbeVerdictRequest,
    db: Session = Depends(get_db),
):
    """Log a verdict against a specific horizon probe.

    Each horizon probe (short/mid/long) can have its verdict logged independently
    without affecting sibling probes.
    """
    probe = db.query(models.Probe).filter(models.Probe.id == probe_id).first()
    if probe is None:
        raise HTTPException(status_code=404, detail="Probe not found")

    now = datetime.now(tz=timezone.utc)
    verdict = models.Verdict(
        id=str(_uuid_mod.uuid4()),
        probe_id=probe.id,
        outcome=body.outcome,
        notes=body.notes,
        decided_at=now,
        created_at=now,
    )
    db.add(verdict)
    probe.status = body.outcome
    db.commit()
    db.refresh(verdict)

    return {
        "id": verdict.id,
        "outcome": verdict.outcome,
        "notes": verdict.notes,
        "decided_at": str(verdict.decided_at),
    }
