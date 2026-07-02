"""Sources API router.

GET  /api/sources?plan_id=<id>          — list all sources for a plan.
POST /api/sources                       — add a source to a plan (manual paste fallback).
POST /api/sources/batch                 — add multiple sources in a single transaction.
POST /api/sources/{id}/verify           — record verification result for a single source.
POST /api/plans/{id}/verify-sources     — batch summary of verification state for a plan.
POST /api/sources/{id}/run-verify       — trigger AI verification for a single source.
POST /api/plans/{id}/run-verify-all     — trigger AI verification for every source on a plan.
PATCH /api/sources/{id}/status-override — manual accept/override of support_status.
POST /api/sources/{id}/accept-status    — clear manual override flag (accept AI result).
"""
import os
import re
import uuid as _uuid_mod
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api")

_URL_RE = re.compile(r"^https?://[^\s]+$")


class CreateSourceRequest(BaseModel):
    plan_id: str
    kind: str
    title: str
    url: str | None = None
    claim: str
    citation: str

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, v: str) -> str:
        if v not in ("book", "article", "youtube", "podcast"):
            raise ValueError("kind must be one of: book, article, youtube, podcast")
        return v

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v

    @field_validator("claim")
    @classmethod
    def claim_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("claim must not be empty")
        return v

    @field_validator("citation")
    @classmethod
    def citation_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("citation must not be empty")
        return v

    @field_validator("url")
    @classmethod
    def url_valid(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _URL_RE.match(v):
            raise ValueError("url must be a valid http/https URL")
        return v


class SourceItem(BaseModel):
    """Single source item for the batch endpoint (no plan_id — provided at top level)."""

    kind: str
    title: str
    url: str | None = None
    claim: str
    citation: str
    # Optional pre-computed verification (e.g. from Tavily-backed suggest) so the
    # attached source keeps its status/rationale instead of starting unverified.
    support_status: str | None = None
    support_rationale: str | None = None

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, v: str) -> str:
        if v not in ("book", "article", "youtube", "podcast"):
            raise ValueError("kind must be one of: book, article, youtube, podcast")
        return v

    @field_validator("support_status")
    @classmethod
    def valid_support_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ("supports", "partial", "contradicts", "unverified"):
            raise ValueError("support_status must be one of: supports, partial, contradicts, unverified")
        return v

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v

    @field_validator("claim")
    @classmethod
    def claim_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("claim must not be empty")
        return v

    @field_validator("citation")
    @classmethod
    def citation_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("citation must not be empty")
        return v

    @field_validator("url")
    @classmethod
    def url_valid(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _URL_RE.match(v):
            raise ValueError("url must be a valid http/https URL")
        return v


class BatchCreateSourceRequest(BaseModel):
    plan_id: str
    sources: List[Dict[str, Any]]


@router.post("/sources", status_code=201)
def create_source(body: CreateSourceRequest, db: Session = Depends(get_db)):
    plan = db.query(models.Plan).filter(models.Plan.id == body.plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    source = models.Source(
        id=str(_uuid_mod.uuid4()),
        plan_id=body.plan_id,
        kind=body.kind,
        title=body.title,
        url=body.url,
        claim=body.claim,
        citation=body.citation,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_to_dict(source)


def _source_to_dict(source: models.Source) -> dict:
    return {
        "id": source.id,
        "plan_id": source.plan_id,
        "kind": source.kind,
        "title": source.title,
        "url": source.url,
        "claim": source.claim,
        "citation": source.citation,
        "support_status": source.support_status,
        "rationale": source.rationale,
        "support_rationale": source.support_rationale,
        "manually_overridden": bool(source.manually_overridden),
    }


# ---------------------------------------------------------------------------
# Verification models
# ---------------------------------------------------------------------------

_SUPPORT_STATUS_VALUES = ("supports", "partial", "contradicts", "unverified")


class VerifySourceRequest(BaseModel):
    support_status: Literal["supports", "partial", "contradicts", "unverified"]
    support_rationale: str | None = Field(None, max_length=4000)


# ---------------------------------------------------------------------------
# POST /api/sources/{id}/verify
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/verify")
def verify_source(
    source_id: str,
    body: VerifySourceRequest,
    db: Session = Depends(get_db),
):
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source.support_status = body.support_status
    source.support_rationale = body.support_rationale
    db.commit()
    db.refresh(source)
    return _source_to_dict(source)


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/verify-sources
# ---------------------------------------------------------------------------

@router.post("/plans/{plan_id}/verify-sources")
def batch_verify_sources(plan_id: str, db: Session = Depends(get_db)):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    sources = db.query(models.Source).filter(models.Source.plan_id == plan_id).all()
    return [_source_to_dict(s) for s in sources]


@router.post("/sources/batch", status_code=201)
def batch_create_sources(body: BatchCreateSourceRequest, db: Session = Depends(get_db)):
    if not body.sources:
        raise HTTPException(status_code=422, detail="sources must not be empty")

    plan = db.query(models.Plan).filter(models.Plan.id == body.plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Validate all items before any insert; collect per-index errors.
    errors = []
    validated: list[SourceItem] = []
    for idx, raw in enumerate(body.sources):
        try:
            item = raw if isinstance(raw, dict) else (raw.model_dump() if hasattr(raw, "model_dump") else dict(raw))
            validated.append(SourceItem.model_validate(item))
        except ValidationError as exc:
            for err in exc.errors():
                field = err["loc"][0] if err["loc"] else "unknown"
                errors.append(f"sources[{idx}].{field}: {err['msg']}")

    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    # All valid — insert in a single transaction.
    created = []
    for item in validated:
        source = models.Source(
            id=str(_uuid_mod.uuid4()),
            plan_id=body.plan_id,
            kind=item.kind,
            title=item.title,
            url=item.url,
            claim=item.claim,
            citation=item.citation,
            support_status=item.support_status or "unverified",
            rationale=item.support_rationale or None,
        )
        db.add(source)
        created.append(source)

    db.commit()
    for source in created:
        db.refresh(source)

    return [_source_to_dict(s) for s in created]


@router.get("/sources")
def list_sources(plan_id: str = Query(...), db: Session = Depends(get_db)):
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    sources = db.query(models.Source).filter(models.Source.plan_id == plan_id).all()
    return {"sources": [_source_to_dict(s) for s in sources]}


# ---------------------------------------------------------------------------
# Source verifier stub — replaced by real AI service when available (issue #98)
# ---------------------------------------------------------------------------

# The verifier service reports "partially_supports"; the DB support_status enum
# uses "partial". Map service statuses onto the enum before persisting.
_STATUS_MAP = {
    "supports": "supports",
    "partially_supports": "partial",
    "contradicts": "contradicts",
    "unverified": "unverified",
}


def _run_verifier(source: models.Source) -> tuple[str, str]:
    """Return (support_status, rationale) for a source.

    Uses the real verifier service (fetch the source URL, classify with Claude)
    when VERIFIER_ENGINE is 'ai' (the default). Set VERIFIER_ENGINE=stub for a
    deterministic keyword-matching stub that exercises the UI without any network
    or AI calls.
    """
    engine = os.environ.get("VERIFIER_ENGINE", "ai")
    if engine == "ai":
        from app.services.source_verifier import verify_source as _verify_service

        result = _verify_service(source)
        status = _STATUS_MAP.get(result.get("support_status", "unverified"), "unverified")
        rationale = result.get("support_rationale") or "No rationale provided."
        return (status, rationale)

    # TEMPORARY stub: hardcoded keywords ("not"/"contradict"/"false" → contradicts;
    # "support"/"confirm"/"evidence" → supports) produce deterministic results for
    # testing and UI development.  These keywords are intentional — they give
    # reproducible variety across test fixtures without requiring a real AI call.
    # Replace this entire block when wiring up the real verifier (issue #98).
    claim = (source.claim or "").strip().lower()
    if not claim:
        return ("unverified", "No claim text provided for verification.")
    if "not" in claim or "contradict" in claim or "false" in claim:
        return ("contradicts", "Stub: claim appears to contradict the source.")
    if "support" in claim or "confirm" in claim or "evidence" in claim:
        return ("supports", "Stub: claim appears supported by the source.")
    return ("unverified", "Stub: automated verification unavailable — review manually.")


# ---------------------------------------------------------------------------
# POST /api/sources/{id}/run-verify
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/run-verify")
def run_verify_source(source_id: str, db: Session = Depends(get_db)):
    """Trigger AI verification for a single source.

    Skips re-verification if the source has been manually overridden.
    """
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.manually_overridden:
        return _source_to_dict(source)

    status, rationale = _run_verifier(source)
    source.support_status = status
    source.rationale = rationale
    source.manually_overridden = False
    db.commit()
    db.refresh(source)
    return _source_to_dict(source)


# ---------------------------------------------------------------------------
# POST /api/plans/{id}/run-verify-all
# ---------------------------------------------------------------------------

@router.post("/plans/{plan_id}/run-verify-all")
def run_verify_all_sources(plan_id: str, db: Session = Depends(get_db)):
    """Trigger AI verification for every source on a plan.

    Sources that have been manually overridden are returned as-is without
    re-running the verifier.
    """
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    sources = db.query(models.Source).filter(models.Source.plan_id == plan_id).all()
    results = []
    for source in sources:
        if not source.manually_overridden:
            status, rationale = _run_verifier(source)
            source.support_status = status
            source.rationale = rationale
            source.manually_overridden = False
        results.append(_source_to_dict(source))

    db.commit()
    for source in sources:
        db.refresh(source)

    return {"results": [_source_to_dict(s) for s in sources]}


# ---------------------------------------------------------------------------
# PATCH /api/sources/{id}/status-override
# ---------------------------------------------------------------------------

class StatusOverrideRequest(BaseModel):
    support_status: Literal["supports", "partial", "contradicts", "unverified"]
    rationale: str = Field(..., min_length=1, max_length=2000)


@router.patch("/sources/{source_id}/status-override")
def status_override(
    source_id: str,
    body: StatusOverrideRequest,
    db: Session = Depends(get_db),
):
    """Manually accept or override the AI-assigned support_status."""
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source.support_status = body.support_status
    source.rationale = body.rationale
    source.manually_overridden = True
    db.commit()
    db.refresh(source)
    return _source_to_dict(source)


# ---------------------------------------------------------------------------
# POST /api/sources/{id}/accept-status
# ---------------------------------------------------------------------------

@router.post("/sources/{source_id}/accept-status")
def accept_status(source_id: str, db: Session = Depends(get_db)):
    """Confirm the current AI-assigned status, clearing the manual override flag."""
    source = db.query(models.Source).filter(models.Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source.manually_overridden = False
    db.commit()
    db.refresh(source)
    return _source_to_dict(source)
