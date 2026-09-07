"""Hub API router — claim-verification entry point for viral-radar.

POST /api/hub/verify-claim             — verify a claim; returns sources + persists result
GET  /api/hub/verify-claim/{id}        — retrieve a previously persisted verification
"""
from __future__ import annotations

import hashlib
import uuid as _uuid_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter(prefix="/api/hub")


# ---------------------------------------------------------------------------
# Source-gathering service (injectable for tests)
# ---------------------------------------------------------------------------

async def gather_sources_for_claim(claim: str, context: dict | None = None) -> list[dict]:
    """Return sources for a claim using the existing research pipeline.

    Each source dict has: title, url, citation, support_status.
    Context is passed as supplementary signal but the pipeline currently uses
    only the claim text as the primary research query.
    """
    from app.research import tavily_search
    from app.routers.gather import _SUPPORT_STATUS_MAP, _SUGGEST_RETURN_MAX

    if tavily_search.available():
        from app.research.tavily_suggest import suggest_sources as tavily_suggest
        kept = await tavily_suggest(mechanism=claim, prior="", name="")
        top = kept[:_SUGGEST_RETURN_MAX]
        sources = []
        for src, res in top:
            sources.append({
                "title": getattr(src, "title", "") or "",
                "url": getattr(src, "url", "") or "",
                "citation": getattr(src, "citation", "") or "",
                "support_status": _SUPPORT_STATUS_MAP.get(
                    res.get("support_status"), "unverified"
                ),
            })
        return sources
    else:
        from app.research.llm_suggest import suggest_sources
        proposed = await suggest_sources(mechanism=claim, prior="", name="", count=5)
        sources = []
        for src in proposed:
            sources.append({
                "title": getattr(src, "title", "") or "",
                "url": getattr(src, "url", "") or "",
                "citation": getattr(src, "citation", "") or "",
                "support_status": "unverified",
            })
        return sources


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class VerifyClaimRequest(BaseModel):
    claim: str
    context: dict | None = None

    @field_validator("claim")
    @classmethod
    def claim_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("claim must not be empty")
        return v


def _claim_hash(claim: str) -> str:
    return hashlib.sha256(claim.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# POST /api/hub/verify-claim
# ---------------------------------------------------------------------------

@router.post("/verify-claim")
async def verify_claim(body: VerifyClaimRequest, db: Session = Depends(get_db)):
    """Verify a claim and return supporting sources.

    If the same claim was already verified, return the cached result immediately.
    """
    h = _claim_hash(body.claim)
    existing = (
        db.query(models.ClaimVerification)
        .filter(models.ClaimVerification.claim_hash == h)
        .first()
    )
    if existing:
        return {
            "verification_id": existing.id,
            "claim": existing.claim,
            "cached": True,
            "sources": existing.sources_json,
        }

    sources = await gather_sources_for_claim(body.claim, context=body.context)

    row = models.ClaimVerification(
        id=str(_uuid_mod.uuid4()),
        claim=body.claim,
        claim_hash=h,
        context_json=body.context,
        sources_json=sources,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "verification_id": row.id,
        "claim": row.claim,
        "cached": False,
        "sources": row.sources_json,
    }


# ---------------------------------------------------------------------------
# GET /api/hub/verify-claim/{verification_id}
# ---------------------------------------------------------------------------

@router.get("/verify-claim/{verification_id}")
def get_verification(verification_id: str, db: Session = Depends(get_db)):
    """Retrieve a previously persisted claim verification by ID."""
    row = (
        db.query(models.ClaimVerification)
        .filter(models.ClaimVerification.id == verification_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Verification not found")
    return {
        "verification_id": row.id,
        "claim": row.claim,
        "cached": True,
        "sources": row.sources_json,
    }
