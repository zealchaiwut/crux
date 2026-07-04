"""Cases API router."""
import json
import uuid as _uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app import models
from app.bake_off import BakeOffError, generate_plans
from app.commander_spec import CommanderSpecError, generate_commander_spec
from app.db import get_db
from app.probe import ProbeError, design_probes
from app.sharpen import SharpenError, sharpen_problem
from app.summary import SummaryError, generate_summary
from app.weigh import WeighError, apply_source_penalties, rerank_plans
from app.services.embeddings import upsert_embedding, EmbeddingError


def _latest_probe(probes):
    """Return the most recently created probe from a list, or None."""
    if not probes:
        return None
    with_ts = [p for p in probes if p.created_at is not None]
    without_ts = [p for p in probes if p.created_at is None]
    if with_ts:
        return max(with_ts, key=lambda p: p.created_at)
    return without_ts[0] if without_ts else None


_VERDICTED_STATUSES = {"confirmed", "killed", "inconclusive"}


def compute_action_plan_state(probes) -> str:
    """Return 'locked', 'provisional', or 'final' based on probe verdict states.

    - locked:      no probe has a verdict yet
    - provisional: at least one probe has a verdict, but not the long-horizon probe
    - final:       the long-horizon probe has a verdict
    """
    if not probes:
        return "locked"
    any_verdict = any(p.status in _VERDICTED_STATUSES for p in probes)
    if not any_verdict:
        return "locked"
    long_probe = next((p for p in probes if p.horizon == "long"), None)
    if long_probe and long_probe.status in _VERDICTED_STATUSES:
        return "final"
    return "provisional"


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


_VALID_STAGES = {"sharpened", "bake_off", "gather", "weigh", "probe", "verdict"}
_VALID_VERDICT_PARAMS = {"confirmed", "killed", "inconclusive", "open"}


def _validate_query_param(name: str, value: str | None, valid: set) -> None:
    """Raise HTTPException(400) if value is not None and not in valid."""
    if value is not None and value not in valid:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid {name} value {value!r}. "
                f"Valid values: {', '.join(sorted(valid))}"
            ),
        )


@router.get("/cases")
def list_cases(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    verdict: str | None = Query(default=None),
):
    _validate_query_param("stage", stage, _VALID_STAGES)
    _validate_query_param("verdict", verdict, _VALID_VERDICT_PARAMS)

    query = db.query(models.Case).options(
        joinedload(models.Case.plans),
        joinedload(models.Case.probes).joinedload(models.Probe.verdicts),
    )

    if stage is not None:
        query = query.filter(models.Case.stage == stage)

    if q is not None:
        keyword = f"%{q}%"
        matching_case_ids = (
            db.query(models.Plan.case_id)
            .filter(models.Plan.mechanism.ilike(keyword))
        )
        query = query.filter(
            or_(
                models.Case.sharpened.ilike(keyword),
                models.Case.id.in_(matching_case_ids),
            )
        )

    if verdict is not None:
        if verdict == "open":
            # No logged verdict: case has no probe or probe has no verdicts
            cases_with_verdict = (
                db.query(models.Verdict.probe_id)
                .join(models.Probe, models.Probe.id == models.Verdict.probe_id)
                .with_entities(models.Probe.case_id)
            )
            query = query.filter(models.Case.id.notin_(cases_with_verdict))
        elif verdict in {"confirmed", "killed", "inconclusive"}:
            cases_with_outcome = (
                db.query(models.Probe.case_id)
                .join(models.Verdict, models.Verdict.probe_id == models.Probe.id)
                .filter(models.Verdict.outcome == verdict)
            )
            query = query.filter(models.Case.id.in_(cases_with_outcome))

    cases = query.order_by(models.Case.created_at.desc()).all()

    result = []
    for case in cases:
        probe = _latest_probe(case.probes)
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
            "stage": case.stage,
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

    probe = _latest_probe(case.probes)
    # Use any probe that has verdict records — long-horizon takes priority (final state)
    _probes_with_verdict = [p for p in case.probes if p.verdicts]
    _long_with_verdict = next((p for p in _probes_with_verdict if p.horizon == "long"), None)
    _verdict_probe = _long_with_verdict or (_probes_with_verdict[0] if _probes_with_verdict else None)
    verdict_obj = _verdict_probe.verdicts[0] if _verdict_probe else None

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
            "rationale": plan.rationale,
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
                    "support_status": s.support_status,
                    "rationale": s.rationale,
                    "support_rationale": s.support_rationale,
                    "manually_overridden": bool(s.manually_overridden),
                    "extracted_content": s.extracted_content,
                    "content_summary": s.content_summary,
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
            "steps": probe.steps if probe.steps is not None else [],
            "duration": probe.duration or "",
            "decision_rule": probe.decision_rule or "",
            "status": probe.status,
            "horizon": probe.horizon,
            "commander_spec": probe.commander_spec,
        }

    probes_out = [
        {
            "id": p.id,
            "type": p.type,
            "target_metric": p.target_metric or "",
            "cost": p.cost or "",
            "time": p.time or "",
            "note": p.note or "",
            "steps": p.steps if p.steps is not None else [],
            "duration": p.duration or "",
            "decision_rule": p.decision_rule or "",
            "status": p.status,
            "horizon": p.horizon,
            "commander_spec": p.commander_spec,
        }
        for p in sorted(case.probes, key=lambda p: ("short", "mid", "long").index(p.horizon)
                         if p.horizon in ("short", "mid", "long") else 99)
    ]

    verdict_log = None
    if verdict_obj:
        verdict_log = {
            "outcome": verdict_obj.outcome,
            "notes": verdict_obj.notes or "",
            "decided_at": str(verdict_obj.decided_at) if verdict_obj.decided_at else None,
        }

    summary_out = None
    if case.summary:
        try:
            summary_out = json.loads(case.summary)
        except (ValueError, TypeError):
            summary_out = None

    return {
        "id": case.id,
        "raw_problem": case.raw_problem,
        "sharpened": case.sharpened or "",
        "not_investigating": not_investigating,
        "stage": case.stage,
        "verdict": (verdict_obj.outcome if verdict_obj else
                    ("progress" if probe and probe.status == "running" else "awaiting")),
        "verdict_log": verdict_log,
        "created_at": str(case.created_at) if case.created_at else None,
        "weigh_context": case.weigh_context or "",
        "plans": plans_out,
        "probe": probe_out,
        "probes": probes_out,
        "summary": summary_out,
        "action_plan_state": compute_action_plan_state(case.probes),
    }


class PatchCaseRequest(BaseModel):
    sharpened: str | None = None
    not_investigating: list[str] | None = None

    @field_validator("sharpened")
    @classmethod
    def sharpened_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("sharpened must not be empty if provided")
        return v

    @field_validator("not_investigating")
    @classmethod
    def items_not_empty(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for item in v:
                if not item or not item.strip():
                    raise ValueError("not_investigating items must be non-empty strings")
        return v


@router.patch("/cases/{case_id}")
def patch_case(case_id: str, body: PatchCaseRequest, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.stage == "verdict":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit a case in verdict stage; it is immutable.",
        )
    if body.sharpened is not None:
        case.sharpened = body.sharpened
    if body.not_investigating is not None:
        case.not_investigating = json.dumps(body.not_investigating)
    db.commit()
    db.refresh(case)
    not_investigating_out = []
    if case.not_investigating:
        try:
            not_investigating_out = json.loads(case.not_investigating)
        except (ValueError, TypeError):
            not_investigating_out = []
    return {
        "id": case.id,
        "sharpened": case.sharpened or "",
        "not_investigating": not_investigating_out,
        "stage": case.stage,
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

    try:
        upsert_embedding(case.id, case.sharpened or case.raw_problem, db)
    except EmbeddingError:
        pass  # embedding failure must not fail case creation

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
    context: str | None = None

    @field_validator("context")
    @classmethod
    def not_blank(cls, v: str | None) -> str | None:
        if v == "":
            return None
        if v is not None and not v.strip():
            raise ValueError("context must not be blank")
        return v


@router.post("/cases/{case_id}/rerank")
async def rerank_case(case_id: str, body: RerankRequest, db: Session = Depends(get_db)):
    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans).joinedload(models.Plan.sources))
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

    plans_with_sources = [
        {
            "label": p.label,
            "sources": [
                {"support_status": s.support_status, "title": s.title, "id": s.id}
                for s in (p.sources or [])
            ],
        }
        for p in plans
    ]
    result = apply_source_penalties(result, plans_with_sources)

    rank_map = {item["label"]: item for item in result}
    for plan in plans:
        item = rank_map.get(plan.label)
        if item:
            plan.current_rank = item["rank"]
            plan.standing = item["standing"]
            plan.rationale = item.get("rationale") or None

    case.weigh_context = body.context
    case.stage = "weigh"
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

    is_first_probe = len(case.probes) == 0

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
        results = await design_probes(
            sharpened=case.sharpened or case.raw_problem,
            plans=plans_input,
        )
    except ProbeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Replace all existing probes (cascade delete via relationship assignment)
    case.probes = []
    db.flush()

    now = datetime.now(tz=timezone.utc)
    new_probes = []
    for result in results:
        probe = models.Probe(
            id=str(_uuid_mod.uuid4()),
            case_id=case.id,
            type=result["type"],
            target_metric=result["target_metric"],
            cost=result["cost"],
            time=result["time"],
            note=result["note"],
            steps=result.get("steps") or [],
            duration=result.get("duration") or "",
            decision_rule=result.get("decision_rule") or "",
            horizon=result["horizon"],
            status="designed",
            created_at=now,
        )
        db.add(probe)
        new_probes.append(probe)

    if is_first_probe:
        case.stage = "probe"
    db.commit()
    for probe in new_probes:
        db.refresh(probe)

    horizon_order = ("short", "mid", "long")
    sorted_probes = sorted(new_probes, key=lambda p: horizon_order.index(p.horizon)
                           if p.horizon in horizon_order else 99)

    return {
        "probes": [
            {
                "id": p.id,
                "type": p.type,
                "target_metric": p.target_metric or "",
                "cost": p.cost or "",
                "time": p.time or "",
                "note": p.note or "",
                "steps": p.steps if p.steps is not None else [],
                "duration": p.duration or "",
                "decision_rule": p.decision_rule or "",
                "horizon": p.horizon,
                "status": p.status,
                "commander_spec": p.commander_spec,
            }
            for p in sorted_probes
        ]
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

    probe = _latest_probe(case.probes)
    if probe is None:
        raise HTTPException(status_code=422, detail="Case has no probe; cannot log a verdict")

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
    case.stage = "verdict"
    db.commit()
    db.refresh(verdict)

    return {
        "id": verdict.id,
        "outcome": verdict.outcome,
        "notes": verdict.notes,
        "decided_at": str(verdict.decided_at),
    }


# ---------------------------------------------------------------------------
# POST /api/cases/{id}/probe/commander-spec
# ---------------------------------------------------------------------------

@router.post("/cases/{case_id}/probe/commander-spec")
async def generate_probe_commander_spec(
    case_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Generate and persist a commander spec for a prototype Probe.

    Only applies to Probes with type='prototype'. Returns 422 for other types.
    Returns 502 if the Claude API call fails; Probe.commander_spec is not written.

    Pass ?force=true to regenerate even when a spec already exists.
    """
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

    probe = _latest_probe(case.probes)
    if probe is None:
        raise HTTPException(status_code=422, detail="Case has no probe; design one first")

    if probe.type != "prototype":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Commander spec only applies to prototype probes; "
                f"this probe has type={probe.type!r}"
            ),
        )

    # Idempotency: if spec already generated and not forcing, return cached
    if probe.commander_spec and not force:
        return {"commander_spec": probe.commander_spec}

    plans = sorted(case.plans, key=lambda p: p.current_rank or 99)
    if not plans:
        raise HTTPException(
            status_code=422,
            detail="At least one plan is required for spec generation.",
        )
    if not any(p.current_rank is not None for p in plans):
        raise HTTPException(
            status_code=422,
            detail="At least one ranked plan is required for spec generation.",
        )
    plans_input = [
        {
            "label": p.label,
            "name": p.name or f"Plan {p.label}",
            "mechanism": p.mechanism or "",
            "current_rank": p.current_rank,
        }
        for p in plans
    ]

    spec_input = {
        "target_metric": probe.target_metric or "",
        "note": probe.note or "",
        "sharpened": case.sharpened or case.raw_problem,
        "plans": plans_input,
    }
    try:
        spec = await generate_commander_spec(spec_input)
    except CommanderSpecError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    probe.commander_spec = spec
    db.commit()
    db.refresh(probe)

    return {"commander_spec": probe.commander_spec}


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/summary
# ---------------------------------------------------------------------------

_PRE_PROBE_STAGES = {"sharpened", "bake_off", "gather", "weigh"}


@router.get("/cases/{case_id}/summary")
async def generate_case_summary(
    case_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Return a literature-review-style cited summary for a case at the probe stage.

    Response body: {"paragraphs": [...], "references": [...], "cached": bool}

    Pass ?force=true to discard the cached value and regenerate.
    Returns 422 when the case has not yet reached the probe stage.
    """
    import json as _json

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

    if case.stage in _PRE_PROBE_STAGES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Summary is only available from the probe stage onward; "
                f"this case is at stage '{case.stage}'."
            ),
        )

    if case.summary and not force:
        cached = _json.loads(case.summary)
        return {**cached, "cached": True}

    plans_input = [
        {
            "label": p.label,
            "name": p.name or f"Plan {p.label}",
            "mechanism": p.mechanism or "",
            "current_rank": p.current_rank,
            "sources": [
                {
                    "id": s.id,
                    "title": s.title or "",
                    "url": s.url or "",
                    "claim": s.claim or "",
                }
                for s in (p.sources or [])
            ],
        }
        for p in sorted(case.plans, key=lambda p: p.current_rank or 99)
    ]

    case_data = {
        "sharpened": case.sharpened or case.raw_problem,
        "raw_problem": case.raw_problem,
        "plans": plans_input,
    }

    try:
        summary_json = await generate_summary(case_data)
    except SummaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    case.summary = summary_json
    db.commit()

    result = _json.loads(summary_json)
    return {**result, "cached": False}
