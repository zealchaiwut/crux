"""Probes API router — status transitions and per-probe verdict logging."""
import uuid as _uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.llm_providers import call_stage

_EVAL_MODEL = "claude-haiku-4-5-20251001"

_EVAL_SYSTEM = (
    "You are a verdict evaluator. Given a decision rule and a numeric metric value, "
    "determine whether the probe is confirmed, killed, or inconclusive.\n\n"
    "Rules:\n"
    "- Respond with ONLY one of: confirmed, killed, inconclusive\n"
    "- No explanation, no punctuation, just the single word.\n"
    "- Use 'inconclusive' only when the decision rule cannot be applied to the metric.\n"
)

_EVAL_SCHEMA_NAME = "numeric_verdict_outcome"
_EVAL_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["confirmed", "killed", "inconclusive"]},
    },
    "required": ["outcome"],
    "additionalProperties": False,
}


async def evaluate_numeric_verdict(decision_rule: str, metric_value: float) -> str:
    """Call Claude to evaluate metric_value against decision_rule; return outcome string."""
    user_message = (
        f"Decision rule: {decision_rule}\n"
        f"Metric value: {metric_value}\n\n"
        "What is the verdict outcome?"
    )
    result = await call_stage(
        _EVAL_SYSTEM, user_message, _EVAL_MODEL,
        _EVAL_SCHEMA_NAME, _EVAL_JSON_SCHEMA,
    )
    if isinstance(result, dict) and "outcome" in result:
        return result["outcome"]
    outcome = str(result).strip().lower()
    if outcome not in _VALID_OUTCOMES:
        return "inconclusive"
    return outcome

router = APIRouter(prefix="/api")

# Only the designed→running transition is supported here.
# The running→closed transition is owned by the Verdict gate.
_VALID_TRANSITIONS = {
    "designed": "running",
}

_VALID_OUTCOMES = {"confirmed", "killed", "inconclusive"}


class ProbeStatusRequest(BaseModel):
    status: str


class NumericVerdictRequest(BaseModel):
    metric_value: float


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


@router.post("/probes/{probe_id}/verdict/numeric")
async def log_numeric_verdict(
    probe_id: str,
    body: NumericVerdictRequest,
    db: Session = Depends(get_db),
):
    """Settle a content-post probe verdict by submitting a numeric engagement figure.

    The server evaluates metric_value against the probe's decision_rule to determine
    the outcome (confirmed / killed / inconclusive).  The metric value is persisted on
    the Verdict row so the number that decided it is never lost.
    """
    probe = db.query(models.Probe).filter(models.Probe.id == probe_id).first()
    if probe is None:
        raise HTTPException(status_code=404, detail="Probe not found")

    outcome = await evaluate_numeric_verdict(
        probe.decision_rule or "", body.metric_value
    )

    now = datetime.now(tz=timezone.utc)
    verdict = models.Verdict(
        id=str(_uuid_mod.uuid4()),
        probe_id=probe.id,
        outcome=outcome,
        notes=f"Metric value: {body.metric_value}",
        metric_value=body.metric_value,
        decided_at=now,
        created_at=now,
    )
    db.add(verdict)
    probe.status = outcome
    db.commit()
    db.refresh(verdict)

    return {
        "id": verdict.id,
        "outcome": verdict.outcome,
        "metric_value": verdict.metric_value,
        "decided_at": str(verdict.decided_at),
    }
