"""NotebookLM debate-podcast router (optional feature).

POST /api/cases/{case_id}/notebooklm         — start generating the debate podcast
GET  /api/cases/{case_id}/notebooklm/status  — poll generation status
GET  /api/cases/{case_id}/notebooklm/audio   — download the generated mp3
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app import models
from app.db import get_db
from app.services import notebooklm_service as nlm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _case_source_urls(case: models.Case) -> list[str]:
    """All distinct http(s) source URLs across every plan in the case."""
    seen: set[str] = set()
    urls: list[str] = []
    for plan in case.plans:
        for src in plan.sources or []:
            url = (src.url or "").strip()
            if url.startswith("http") and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


@router.post("/cases/{case_id}/notebooklm")
async def start_notebooklm(case_id: str, db: Session = Depends(get_db)):
    """Kick off debate-podcast generation from the case's sources (background)."""
    if not nlm.available():
        raise HTTPException(
            status_code=503,
            detail=(
                "NotebookLM is not configured. Install notebooklm-py and run "
                "`notebooklm login --master-token --account <you>@gmail.com`."
            ),
        )

    case = (
        db.query(models.Case)
        .options(joinedload(models.Case.plans).joinedload(models.Plan.sources))
        .filter(models.Case.id == case_id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    current = nlm.get_status(case_id)
    if current["status"] == "running":
        return current

    urls = _case_source_urls(case)
    if not urls:
        raise HTTPException(status_code=422, detail="Case has no source URLs to send to NotebookLM")

    title = (case.sharpened or case.raw_problem or "Crux case")[:120]
    # Fire-and-forget; the service manages its own status + persistence.
    asyncio.create_task(nlm.generate_debate(case_id, title, urls))
    return {"status": "running", "error": "", "notebook_url": None, "audio": False, "source_count": len(urls)}


@router.get("/cases/{case_id}/notebooklm/status")
def notebooklm_status(case_id: str, db: Session = Depends(get_db)):
    """Return live status; fall back to persisted artifacts on the case row."""
    live = nlm.get_status(case_id)
    if live["status"] != "idle":
        return live

    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    audio_ready = bool(case.notebooklm_audio) and os.path.exists(nlm.audio_path(case_id))
    if case.notebooklm_url or audio_ready:
        return {
            "status": "done" if audio_ready else "idle",
            "error": "",
            "notebook_url": case.notebooklm_url,
            "audio": audio_ready,
        }
    return {"status": "idle", "error": "", "notebook_url": None, "audio": False}


@router.get("/cases/{case_id}/notebooklm/audio")
def notebooklm_audio(case_id: str):
    """Download the generated debate-podcast mp3."""
    path = nlm.audio_path(case_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No generated podcast for this case")
    return FileResponse(path, media_type="audio/mpeg", filename=f"crux-debate-{case_id}.mp3")
