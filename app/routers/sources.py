"""Sources API router.

GET  /api/sources?plan_id=<id>       — list all sources for a plan.
POST /api/sources                    — add a source to a plan (manual paste fallback).
POST /api/sources/batch              — add multiple sources in a single transaction.
POST /api/sources/{id}/verify        — record verification result for a single source.
POST /api/plans/{id}/verify-sources  — batch summary of verification state for a plan.
"""
import re
import uuid as _uuid_mod
from typing import Any, List, Literal, Optional

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
        if v not in ("book", "article", "youtube"):
            raise ValueError("kind must be one of: book, article, youtube")
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

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, v: str) -> str:
        if v not in ("book", "article", "youtube"):
            raise ValueError("kind must be one of: book, article, youtube")
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
    sources: List[Any]


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
    }


# ---------------------------------------------------------------------------
# Verification models
# ---------------------------------------------------------------------------

_SUPPORT_STATUS_VALUES = ("supports", "contradicts", "neutral", "inconclusive")


class VerifySourceRequest(BaseModel):
    support_status: Literal["supports", "contradicts", "neutral", "inconclusive"]
    rationale: str = Field(..., min_length=1, max_length=2000)


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
    source.rationale = body.rationale
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
    total = len(sources)
    verified = sum(1 for s in sources if s.support_status is not None)
    results = [
        {
            "source_id": s.id,
            "support_status": s.support_status,
            "rationale": s.rationale,
        }
        for s in sources
    ]
    return {"total": total, "verified": verified, "failed": 0, "results": results}


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
    return {
        "sources": [
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
    }
