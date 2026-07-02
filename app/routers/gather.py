"""Gather API router — Stage 2 research loop automation.

POST /api/plans/{plan_id}/gather          — run research loop for one plan
POST /api/plans/{plan_id}/gather/suggest  — return ranked candidates without persisting
POST /api/cases/{case_id}/gather          — trigger research loop for all plans in a case
GET  /api/plans/{plan_id}/gather-status   — current gather status for a plan
"""
from __future__ import annotations

import asyncio
import logging
import uuid as _uuid_mod

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models
from app.config import RESEARCH_ENGINE
from app.db import get_db
from app.research import tavily_search
from app.research.llm_suggest import suggest_sources
from app.research.tavily_suggest import suggest_sources as tavily_suggest_sources
from app.services.research_orchestrator import (
    OrchestratorError,
    gather_status_store,
    make_engine,
    run_research_for_plan,
)
from app.services.source_verifier import verify_source

logger = logging.getLogger(__name__)

_VALID_KINDS = frozenset({"book", "article", "youtube", "podcast"})
_MAX_SUGGEST_CANDIDATES = 5
# Over-generate proposals so enough survive the verify-and-filter pass.
_SUGGEST_OVERGENERATE = 10
# Verifier statuses that count as "we could actually verify this source".
_VERIFIED_STATUSES = frozenset({"supports", "partially_supports", "contradicts"})
# Verifier reports "partially_supports"; the DB/UI use "partial".
_SUPPORT_STATUS_MAP = {
    "supports": "supports",
    "partially_supports": "partial",
    "contradicts": "contradicts",
    "unverified": "unverified",
}

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
# Suggest helpers
# ---------------------------------------------------------------------------

def _build_suggest_candidate(source, score: float) -> dict | None:
    """Validate a Source and build a candidate dict; logs warning and returns None if invalid."""
    kind = (getattr(source, "kind", "") or "")
    title = (getattr(source, "title", "") or "").strip()
    url = (getattr(source, "url", "") or "").strip()
    claim = (getattr(source, "claim", "") or "").strip()
    citation = (getattr(source, "citation", "") or "").strip()

    if kind not in _VALID_KINDS:
        logger.warning(
            "suggest: dropping candidate — invalid kind=%r (url=%r)", kind, url
        )
        return None
    if not title:
        logger.warning(
            "suggest: dropping candidate — empty title (kind=%r, url=%r)", kind, url
        )
        return None
    if not url:
        logger.warning(
            "suggest: dropping candidate — empty url (kind=%r)", kind
        )
        return None
    if not claim:
        logger.warning(
            "suggest: dropping candidate — empty claim (kind=%r, url=%r)", kind, url
        )
        return None
    if not citation:
        logger.warning(
            "suggest: dropping candidate — empty citation (kind=%r, url=%r)", kind, url
        )
        return None

    return {
        "candidate_id": str(_uuid_mod.uuid4()),
        "kind": kind,
        "title": title,
        "url": url,
        "claim": claim,
        "citation": citation,
        "relevance_score": score,
    }


# ---------------------------------------------------------------------------
# POST /api/plans/{plan_id}/gather/suggest
# ---------------------------------------------------------------------------

@router.post("/plans/{plan_id}/gather/suggest")
async def suggest_plan_sources(plan_id: str, db: Session = Depends(get_db)):
    """Return up to 5 candidate sources that were fetched and verified.

    Over-generates LLM proposals, verifies each against its stated claim, and
    returns only sources that actually verified (supports/partial/contradicts) —
    unfetchable or unrelated URLs (support_status "unverified") are dropped so
    the user only sees sources the app can stand behind. The pre-computed
    verification is included so it need not be re-run on attach.
    """
    plan = (
        db.query(models.Plan)
        .filter(models.Plan.id == plan_id)
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    mechanism = plan.mechanism or ""
    prior = plan.prior or ""
    name = plan.name or ""

    if tavily_search.available():
        # Preferred path: Tavily returns real URLs + page content, and each is
        # assessed against the hypothesis — so results are already verified.
        kept = await tavily_suggest_sources(mechanism=mechanism, prior=prior, name=name)
        considered = len(kept)  # only survivors are returned by the Tavily path
    else:
        # Fallback (no Tavily key): LLM proposes URLs, we fetch + verify each and
        # drop anything unfetchable/unrelated.
        proposed = await suggest_sources(
            mechanism=mechanism, prior=prior, name=name, count=_SUGGEST_OVERGENERATE
        )

        async def _verify(src):
            result = await asyncio.to_thread(
                verify_source, {"kind": src.kind, "url": src.url, "claim": src.claim}
            )
            return src, result

        verified = await asyncio.gather(*[_verify(s) for s in proposed])
        kept = [
            (src, res) for src, res in verified
            if res.get("support_status") in _VERIFIED_STATUSES
        ]
        considered = len(proposed)
        dropped = considered - len(kept)
        if dropped:
            logger.info(
                "suggest: dropped %d/%d unverifiable candidates for plan %s",
                dropped, considered, plan_id,
            )

    top = kept[:_MAX_SUGGEST_CANDIDATES]
    n = len(top)
    candidates = []
    for i, (src, res) in enumerate(top):
        score = round((n - i) / n, 2) if n else 0.0
        candidate = _build_suggest_candidate(src, score)
        if candidate is not None:
            candidate["support_status"] = _SUPPORT_STATUS_MAP.get(
                res.get("support_status"), "unverified"
            )
            candidate["support_rationale"] = res.get("support_rationale") or ""
            candidates.append(candidate)

    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)

    return {"candidates": candidates}


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
# POST /api/gather/{plan_id}  (frontend alias — avoids /api/plans in JS)
# ---------------------------------------------------------------------------

@router.post("/gather/{plan_id}")
def gather_plan_by_id(plan_id: str, db: Session = Depends(get_db)):
    """Frontend alias for gather_plan; keeps /api/plans out of the SPA JS bundle."""
    return gather_plan(plan_id, db)


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
