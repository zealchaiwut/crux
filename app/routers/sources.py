"""Sources API router.

GET  /api/sources?plan_id=<id>   — list all sources for a plan.
POST /api/sources                — add a source to a plan (manual paste fallback).
"""
import re
import uuid as _uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
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
    return {
        "id": source.id,
        "plan_id": source.plan_id,
        "kind": source.kind,
        "title": source.title,
        "url": source.url,
        "claim": source.claim,
        "citation": source.citation,
    }


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
