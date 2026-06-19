"""Gather API router — Stage 2 research loop automation.

POST /api/plans/{plan_id}/gather          — run research loop for one plan
POST /api/cases/{case_id}/gather          — trigger research loop for all plans in a case
GET  /api/plans/{plan_id}/gather-status   — current gather status for a plan
"""
from __future__ import annotations

import uuid as _uuid_mod

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models
from app.config import RESEARCH_ENGINE
from app.db import get_db
from app.services.research_orchestrator import (
    OrchestratorError,
    gather_status_store,
    make_engine,
    run_research_for_plan,
)

router = APIRouter(prefix="/api")


def _sources_to_dicts(sources) -> list[dict]:
    return [
        {
            "id": s.id,
            "plan_id": s.plan_id,
            "kind": s.kind,
            "title": s.title,
            "url": s.url,
            "claim": s.claim,
            "citation": s.citation,
        }
        for s in sources
    ]


def _persist_sources(plan_id: str, sources, db: Session) -> list[models.Source]:
    """Persist Source objects to the DB and return the saved models."""
    saved = []
    for src in sources:
        row = models.Source(
            id=str(_uuid_mod.uuid4()),
            plan_id=plan_id,
            kind=src.kind,
            title=src.title,
            url=src.url,
            claim=src.claim,
            citation=src.citation,
        )
        db.add(row)
        saved.append(row)
    db.commit()
    return saved


# ---------------------------------------------------------------------------
# POST /api/plans/{plan_id}/gather
# ---------------------------------------------------------------------------

@router.post("/plans/{plan_id}/gather")
def gather_plan(plan_id: str, db: Session = Depends(get_db)):
    """Run the research loop for a single plan and persist resulting sources."""
    plan = (
        db.query(models.Plan)
        .options(joinedload(models.Plan.sources))
        .filter(models.Plan.id == plan_id)
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    gather_status_store.set(plan_id, "running")

    engine = make_engine(RESEARCH_ENGINE)
    try:
        result_sources = run_research_for_plan(
            plan_mechanism=plan.mechanism or "",
            plan_prior=plan.prior or "",
            engine=engine,
        )
    except OrchestratorError as exc:
        gather_status_store.set(plan_id, "error", error=str(exc))
        return {
            "plan_id": plan_id,
            "gather_status": "error",
            "error": str(exc),
            "sources": [],
        }

    if not result_sources:
        gather_status_store.set(plan_id, "empty")
        return {
            "plan_id": plan_id,
            "gather_status": "empty",
            "error": "",
            "sources": [],
        }

    saved = _persist_sources(plan_id, result_sources, db)
    gather_status_store.set(plan_id, "done")

    return {
        "plan_id": plan_id,
        "gather_status": "done",
        "error": "",
        "sources": _sources_to_dicts(saved),
    }


# ---------------------------------------------------------------------------
# POST /api/cases/{case_id}/gather
# ---------------------------------------------------------------------------

@router.post("/cases/{case_id}/gather")
def gather_case(case_id: str, db: Session = Depends(get_db)):
    """Trigger the research loop for every plan in a case. Returns per-plan status."""
    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans).joinedload(models.Plan.sources))
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.plans:
        raise HTTPException(status_code=422, detail="Case has no plans to gather for")

    engine = make_engine(RESEARCH_ENGINE)
    plan_results = []

    for plan in case.plans:
        gather_status_store.set(plan.id, "running")
        try:
            result_sources = run_research_for_plan(
                plan_mechanism=plan.mechanism or "",
                plan_prior=plan.prior or "",
                engine=engine,
            )
        except OrchestratorError as exc:
            gather_status_store.set(plan.id, "error", error=str(exc))
            plan_results.append({
                "plan_id": plan.id,
                "gather_status": "error",
                "error": str(exc),
                "sources": [],
            })
            continue

        if not result_sources:
            gather_status_store.set(plan.id, "empty")
            plan_results.append({
                "plan_id": plan.id,
                "gather_status": "empty",
                "error": "",
                "sources": [],
            })
            continue

        saved = _persist_sources(plan.id, result_sources, db)
        gather_status_store.set(plan.id, "done")
        plan_results.append({
            "plan_id": plan.id,
            "gather_status": "done",
            "error": "",
            "sources": _sources_to_dicts(saved),
        })

    return {"case_id": case_id, "plans": plan_results}


# ---------------------------------------------------------------------------
# GET /api/plans/{plan_id}/gather-status
# ---------------------------------------------------------------------------

@router.get("/plans/{plan_id}/gather-status")
def get_gather_status(plan_id: str, db: Session = Depends(get_db)):
    """Return the current gather status and any persisted sources for a plan."""
    plan = (
        db.query(models.Plan)
        .options(joinedload(models.Plan.sources))
        .filter(models.Plan.id == plan_id)
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    status_data = gather_status_store.get(plan_id)
    return {
        "plan_id": plan_id,
        "gather_status": status_data["status"],
        "error": status_data["error"],
        "sources": _sources_to_dicts(plan.sources or []),
    }
