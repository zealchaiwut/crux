"""NotebookLM debate-podcast generation for a case.

Uses the unofficial ``notebooklm-py`` framework to: create a notebook, add the
case's source URLs, generate a DEBATE-format audio overview, download the mp3,
and record the notebook URL so the user can open NotebookLM to listen/chat.

This is OPTIONAL. It requires:
  * ``pip install notebooklm-py`` (in requirements.txt), and
  * a one-time auth bootstrap on the server:
      notebooklm login --master-token --account you@gmail.com

``available()`` returns False (and the API degrades gracefully) until both are
in place. Generation is long (minutes), so it runs as a background task with an
in-memory status store; the final artifacts are persisted on the case row.

Caveat: notebooklm-py rides undocumented Google endpoints and can break without
notice — treat failures as expected and surface them.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Where downloaded podcasts are written (served for download via the router).
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "notebooklm")

# case_id -> {"status": "running"|"done"|"error", "error": str,
#             "notebook_url": str|None, "audio": bool}
_STATUS: dict[str, dict] = {}


def available() -> bool:
    """True when notebooklm-py is installed and an auth session is bootstrapped."""
    try:
        import notebooklm  # noqa: F401
        from notebooklm.paths import get_storage_path
    except ImportError:
        return False
    try:
        return os.path.exists(get_storage_path())
    except Exception:
        return False


def get_status(case_id: str) -> dict:
    return _STATUS.get(case_id, {"status": "idle", "error": "", "notebook_url": None, "audio": False})


def audio_path(case_id: str) -> str:
    return os.path.join(MEDIA_DIR, f"{case_id}.mp3")


def _persist(case_id: str, notebook_url: str | None, audio: str | None) -> None:
    """Write the artifacts onto the case row using a fresh DB session."""
    from app.db import _SessionLocal
    from app import models

    if _SessionLocal is None:
        return
    db = _SessionLocal()
    try:
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if case is not None:
            if notebook_url:
                case.notebooklm_url = notebook_url
            if audio:
                case.notebooklm_audio = audio
            db.commit()
    finally:
        db.close()


async def generate_debate(case_id: str, title: str, source_urls: list[str]) -> None:
    """Background task: build the notebook, generate the DEBATE podcast, download it.

    Updates ``_STATUS[case_id]`` throughout and persists the notebook URL + audio
    path onto the case row on success.
    """
    from notebooklm import NotebookLMClient, AudioFormat, AudioLength

    _STATUS[case_id] = {"status": "running", "error": "", "notebook_url": None, "audio": False}
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        async with NotebookLMClient.from_storage() as client:
            nb = await client.notebooks.create(title)
            notebook_url = f"https://notebooklm.google.com/notebook/{nb.id}"
            _STATUS[case_id]["notebook_url"] = notebook_url
            _persist(case_id, notebook_url, None)

            for url in source_urls:
                try:
                    await client.sources.add_url(nb.id, url, wait=True)
                except Exception as exc:  # one bad URL shouldn't sink the batch
                    logger.warning("notebooklm: add_url failed for %s: %s", url, exc)

            status = await client.artifacts.generate_audio(
                nb.id,
                audio_format=AudioFormat.DEBATE,
                audio_length=AudioLength.DEFAULT,
                language="en",
            )
            await client.artifacts.wait_for_completion(nb.id, status.task_id, timeout=1800)

            out = audio_path(case_id)
            await client.artifacts.download_audio(nb.id, out)

            _STATUS[case_id] = {
                "status": "done", "error": "",
                "notebook_url": notebook_url, "audio": True,
            }
            _persist(case_id, notebook_url, out)
    except Exception as exc:
        logger.warning("notebooklm: generation failed for case %s: %s", case_id, exc)
        prev = _STATUS.get(case_id, {})
        _STATUS[case_id] = {
            "status": "error", "error": str(exc),
            "notebook_url": prev.get("notebook_url"), "audio": False,
        }
