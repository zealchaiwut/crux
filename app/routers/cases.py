"""Cases API router."""
import json
import uuid as _uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session, joinedload

from app import models
from app.bake_off import BakeOffError, generate_plans
from app.db import get_db
from app.probe import ProbeError, design_probe
from app.sharpen import SharpenError, sharpen_problem
from app.weigh import WeighError, rerank_plans

router = APIRouter(prefix="/api")

_STAGE_ORDER = {
    "sharpened": 0,
    "bake_off": 1,
    "gather": 2,
    "weigh": 3,
    "probe": 4,
    "verdict": 5,
}

_STANDING_BY_RANK = {1: 0.62, 2: 0.28, 3: 0.10}


def _plan_state(plan: models.Plan, probe: models.Probe | None,
                verdict: models.Verdict | None) -> str | None:
    if verdict and plan.current_rank == 1:
        return "won"
    if not verdict and probe and probe.status == "running" and plan.current_rank == 1:
        return "leading"
    return None


@router.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    cases = (
        db.query(models.Case)
        .options(
            joinedload(models.Case.plans),
            joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
        )
        .order_by(models.Case.created_at.desc())
        .all()
    )

    result = []
    for case in cases:
        probe = case.probes[0] if case.probes else None
        verdict_obj = (probe.verdicts[0] if probe and probe.verdicts else None)

        if verdict_obj:
            verdict = verdict_obj.outcome
        elif probe and probe.status == "running":
            verdict = "progress"
        else:
            verdict = "awaiting"

        verdict_log = None
        if verdict_obj:
            verdict_log = {
                "outcome": verdict_obj.outcome,
                "notes": verdict_obj.notes or "",
                "decided_at": str(verdict_obj.decided_at) if verdict_obj.decided_at else None,
            }

        plans_out = []
        for plan in sorted(case.plans, key=lambda p: p.current_rank or 99):
            rank = plan.current_rank or 99
            plans_out.append({
                "key": plan.label,
                "name": plan.mechanism or f"Plan {plan.label}",
                "standing": _STANDING_BY_RANK.get(rank, 0.15),
                "state": _plan_state(plan, probe, verdict_obj),
            })

        result.append({
            "id": case.id,
            "title": case.sharpened or case.raw_problem,
            "stage": _STAGE_ORDER.get(case.stage, 0),
            "verdict": verdict,
            "verdict_log": verdict_log,
            "plans": plans_out,
        })

    return {"cases": result}


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    from app.services.research_orchestrator import gather_status_store

    case = (
        db.query(models.Case)
        .options(
            joinedload(models.Case.plans).joinedload(models.Plan.sources),
            joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
        )
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    probe = case.probes[0] if case.probes else None
    verdict_obj = (probe.verdicts[0] if probe and probe.verdicts else None)

    not_investigating = []
    if case.not_investigating:
        try:
            not_investigating = json.loads(case.not_investigating)
        except (ValueError, TypeError):
            not_investigating = []

    plans_out = []
    for plan in sorted(case.plans, key=lambda p: p.current_rank or 99):
        rank = plan.current_rank or 99
        status_data = gather_status_store.get(plan.id)
        plans_out.append({
            "id": plan.id,
            "label": plan.label,
            "name": plan.name or f"Plan {plan.label}",
            "mechanism": plan.mechanism or "",
            "prior": plan.prior or "0",
            "bar_weight": _STANDING_BY_RANK.get(rank, 0.15),
            "standing": plan.standing,
            "current_rank": plan.current_rank,
            "state": _plan_state(plan, probe, verdict_obj),
            "gather_status": status_data["status"],
            "gather_error": status_data["error"],
            "sources": [
                {
                    "id": s.id,
                    "kind": s.kind,
                    "title": s.title,
                    "url": s.url,
                    "claim": s.claim,
                    "citation": s.citation,
                }
                for s in (plan.sources or [])
            ],
        })

    probe_out = None
    if probe:
        probe_out = {
            "id": probe.id,
            "type": probe.type,
            "target_metric": probe.target_metric or "",
            "cost": probe.cost or "",
            "time": probe.time or "",
            "note": probe.note or "",
            "status": probe.status,
        }

    verdict_log = None
    if verdict_obj:
        verdict_log = {
            "outcome": verdict_obj.outcome,
            "notes": verdict_obj.notes or "",
            "decided_at": str(verdict_obj.decided_at) if verdict_obj.decided_at else None,
        }

    return {
        "id": case.id,
        "raw_problem": case.raw_problem,
        "sharpened": case.sharpened or "",
        "not_investigating": not_investigating,
        "stage": _STAGE_ORDER.get(case.stage, 0),
        "verdict": (verdict_obj.outcome if verdict_obj else
                    ("progress" if probe and probe.status == "running" else "awaiting")),
        "verdict_log": verdict_log,
        "created_at": str(case.created_at) if case.created_at else None,
        "weigh_context": case.weigh_context or "",
        "plans": plans_out,
        "probe": probe_out,
    }


class SharpenRequest(BaseModel):
    raw_problem: str

    @field_validator("raw_problem")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("raw_problem must not be empty")
        return v


@router.post("/cases/sharpen")
async def sharpen_case(body: SharpenRequest):
    try:
        result = await sharpen_problem(body.raw_problem)
    except SharpenError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return result


class CreateCaseRequest(BaseModel):
    raw_problem: str
    sharpened: str
    not_investigating: list[str]

    @field_validator("sharpened")
    @classmethod
    def sharpened_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("sharpened must not be empty")
        return v


@router.post("/cases", status_code=201)
def create_case(body: CreateCaseRequest, db: Session = Depends(get_db)):
    case = models.Case(
        id=str(_uuid_mod.uuid4()),
        raw_problem=body.raw_problem,
        sharpened=body.sharpened,
        not_investigating=json.dumps(body.not_investigating),
        stage="sharpened",
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"id": case.id}


@router.post("/cases/{case_id}/bake-off")
async def run_bake_off(case_id: str, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans))
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    existing = sorted(case.plans, key=lambda p: p.current_rank or 99)
    if existing:
        plans_out = [
            {
                "label": p.label,
                "name": p.name or f"Plan {p.label}",
                "mechanism": p.mechanism or "",
                "prior": p.prior or "0",
                "standing": _STANDING_BY_RANK.get(p.current_rank or 99, 0.15),
                "state": None,
            }
            for p in existing
        ]
        return {"plans": plans_out}

    try:
        plans_data = await generate_plans(case.sharpened or case.raw_problem)
    except BakeOffError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    sorted_plans = sorted(plans_data, key=lambda p: float(p["prior"]), reverse=True)
    for rank, plan_dict in enumerate(sorted_plans, start=1):
        plan = models.Plan(
            id=str(_uuid_mod.uuid4()),
            case_id=case.id,
            label=plan_dict["label"],
            name=plan_dict["name"],
            mechanism=plan_dict["mechanism"],
            prior=str(plan_dict["prior"]),
            current_rank=rank,
        )
        db.add(plan)

    case.stage = "gather"
    db.commit()

    plans_out = [
        {
            "label": p["label"],
            "name": p["name"],
            "mechanism": p["mechanism"],
            "prior": str(p["prior"]),
            "bar_weight": _STANDING_BY_RANK.get(rank, 0.15),
            "standing": None,
            "current_rank": rank,
            "state": "leading" if rank == 1 else None,
        }
        for rank, p in enumerate(sorted_plans, start=1)
    ]
    return {"plans": plans_out}


class RerankRequest(BaseModel):
    context: str

    @field_validator("context")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("context must not be blank")
        return v


@router.post("/cases/{case_id}/rerank")
async def rerank_case(case_id: str, body: RerankRequest, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans))
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    plans = sorted(case.plans, key=lambda p: p.current_rank or 99)
    if not plans:
        raise HTTPException(status_code=422, detail="Case has no plans to re-rank")

    plans_input = [
        {"label": p.label, "name": p.name or f"Plan {p.label}", "mechanism": p.mechanism or ""}
        for p in plans
    ]

    try:
        result = await rerank_plans(
            sharpened=case.sharpened or case.raw_problem,
            plans=plans_input,
            context=body.context,
        )
    except WeighError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    rank_map = {item["label"]: item for item in result}
    for plan in plans:
        item = rank_map.get(plan.label)
        if item:
            plan.current_rank = item["rank"]
            plan.standing = item["standing"]

    case.weigh_context = body.context
    db.commit()

    db.refresh(case)
    updated_plans = sorted(case.plans, key=lambda p: p.current_rank or 99)
    plans_out = [
        {
            "id": p.id,
            "label": p.label,
            "name": p.name or f"Plan {p.label}",
            "mechanism": p.mechanism or "",
            "prior": p.prior or "0",
            "bar_weight": _STANDING_BY_RANK.get(p.current_rank or 99, 0.15),
            "standing": p.standing,
            "current_rank": p.current_rank,
        }
        for p in updated_plans
    ]
    return {"plans": plans_out, "weigh_context": case.weigh_context}


@router.post("/cases/{case_id}/probe")
async def design_probe_for_case(case_id: str, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(
            joinedload(models.Case.plans),
            joinedload(models.Case.probes),
        )
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    plans = sorted(case.plans, key=lambda p: p.current_rank or 99)
    if not plans:
        raise HTTPException(status_code=422, detail="Case has no plans to design a probe for")

    if case.probes:
        probe = case.probes[0]
        return {
            "id": probe.id,
            "type": probe.type,
            "target_metric": probe.target_metric or "",
            "cost": probe.cost or "",
            "time": probe.time or "",
            "note": probe.note or "",
            "status": probe.status,
        }

    plans_input = [
        {
            "label": p.label,
            "name": p.name or f"Plan {p.label}",
            "mechanism": p.mechanism or "",
            "current_rank": p.current_rank,
        }
        for p in plans
    ]
    try:
        result = await design_probe(
            sharpened=case.sharpened or case.raw_problem,
            plans=plans_input,
        )
    except ProbeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    probe = models.Probe(
        id=str(_uuid_mod.uuid4()),
        case_id=case.id,
        type=result["type"],
        target_metric=result["target_metric"],
        cost=result["cost"],
        time=result["time"],
        note=result["note"],
        status="designed",
    )
    db.add(probe)
    case.stage = "probe"
    db.commit()
    db.refresh(probe)

    return {
        "id": probe.id,
        "type": probe.type,
        "target_metric": probe.target_metric or "",
        "cost": probe.cost or "",
        "time": probe.time or "",
        "note": probe.note or "",
        "status": probe.status,
    }


_VERDICT_OUTCOMES = {"confirmed", "killed", "inconclusive"}


class LogVerdictRequest(BaseModel):
    outcome: str
    notes: str

    @field_validator("outcome")
    @classmethod
    def outcome_valid(cls, v: str) -> str:
        if v not in _VERDICT_OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(_VERDICT_OUTCOMES)}")
        return v

    @field_validator("notes")
    @classmethod
    def notes_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("notes must not be empty")
        return v


@router.post("/cases/{case_id}/verdict")
def log_verdict(case_id: str, body: LogVerdictRequest, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.probes).joinedload(models.Probe.verdicts))
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    probe = case.probes[0] if case.probes else None
    if probe is None:
        raise HTTPException(status_code=422, detail="Case has no probe; cannot log a verdict")

    verdict = models.Verdict(
        id=str(_uuid_mod.uuid4()),
        probe_id=probe.id,
        outcome=body.outcome,
        notes=body.notes,
        decided_at=datetime.now(tz=timezone.utc),
    )
    db.add(verdict)
    probe.status = body.outcome
    case.stage = "verdict"
    db.commit()
    db.refresh(verdict)

    return {
        "id": verdict.id,
        "outcome": verdict.outcome,
        "notes": verdict.notes,
        "decided_at": str(verdict.decided_at),
    }
