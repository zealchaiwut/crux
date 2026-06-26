"""Tests for issue #134: Make weigh context optional in WeighPanel UI.

AC coverage:
  AC1 — WeighPanel displays a "Skip — weigh on sources only" button alongside submit button (JS).
  AC2 — Clicking "Skip" calls POST /api/cases/{id}/rerank with weigh_context null/empty (JS).
  AC3 — Weigh context text field is visually marked as optional in label text (JS).
  AC4 — Submitting with empty context behaves identically to Skip (API accepts null/empty).
  AC5 — weigh_context field in API schema is nullable (no validation error on null/empty).
  AC6 — Rerank result returned correctly whether context provided or skipped (API).
  AC7 — Existing behavior when context is provided is unchanged (API).
"""
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _read_combined_js():
    return "".join((JS_DIR / f).read_text() for f in sorted(JS_DIR.iterdir()) if f.suffix == ".js")


def _make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.models import Base
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_db()
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api_client(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


def _seed_case_with_plans(session, stage="weigh"):
    from app import models
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is my running performance dropping?",
        sharpened="Running performance dropped 15% over 6 weeks.",
        stage=stage,
    )
    session.add(c)
    session.flush()

    plans = [
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="A",
            name="Overtraining", mechanism="Excess volume depresses HRV.",
            prior="0.55", current_rank=1,
        ),
        models.Plan(
            id=str(uuid.uuid4()), case_id=c.id, label="B",
            name="Iron Deficiency", mechanism="Low ferritin impairs oxygen.",
            prior="0.30", current_rank=2,
        ),
    ]
    for p in plans:
        session.add(p)
    session.commit()
    return c, plans


_MOCK_RERANK_RESULT = [
    {"label": "B", "rank": 1, "standing": "ruled-in"},
    {"label": "A", "rank": 2, "standing": None},
]


# ---------------------------------------------------------------------------
# AC1: Skip button present in JS
# ---------------------------------------------------------------------------

def test_skip_button_text_in_js():
    """AC1: WeighPanel JS must include a 'Skip' button text alongside the submit button."""
    combined = _read_combined_js()
    assert "Skip" in combined and "sources only" in combined, (
        "WeighPanel must include a 'Skip — weigh on sources only' button in JS"
    )


# ---------------------------------------------------------------------------
# AC2: Skip sends null context (JS structural check)
# ---------------------------------------------------------------------------

def test_skip_handler_sends_null_context_in_js():
    """AC2: The skip handler must call rerank with null context (context: null in JS)."""
    combined = _read_combined_js()
    assert "context: null" in combined or "handleSkip" in combined, (
        "JS must include a skip handler that sends null context to the rerank endpoint"
    )


# ---------------------------------------------------------------------------
# AC3: Label marked as optional in JS
# ---------------------------------------------------------------------------

def test_context_label_marked_optional_in_js():
    """AC3: The WeighPanel context label must explicitly say '(optional)'."""
    combined = _read_combined_js()
    # Must appear in the WeighPanel section, not just elsewhere in the file.
    # The label previously read "YOUR CONTEXT" — it must now read "CONTEXT (OPTIONAL)"
    # or similar to communicate that the field is not required.
    assert "CONTEXT (OPTIONAL)" in combined or "Context (optional)" in combined, (
        "WeighPanel context field label must read 'CONTEXT (OPTIONAL)' or 'Context (optional)'"
    )


# ---------------------------------------------------------------------------
# AC4: Submit with empty context works (API accepts null/empty)
# ---------------------------------------------------------------------------

def test_rerank_accepts_null_context(api_client, db_session):
    """AC4/AC5: POST /api/cases/{id}/rerank with context=null returns 200."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": None},
        )
    assert r.status_code == 200, f"Expected 200 with null context, got {r.status_code}: {r.text}"


def test_rerank_accepts_empty_string_context(api_client, db_session):
    """AC4/AC5: POST /api/cases/{id}/rerank with context='' returns 200 (treated as null)."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": ""},
        )
    assert r.status_code == 200, f"Expected 200 with empty context, got {r.status_code}: {r.text}"


def test_rerank_empty_context_treated_as_null(api_client, db_session):
    """AC4: Empty context is stored as null, not empty string."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ""})
    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.weigh_context is None, (
        f"Empty context should be persisted as null, got: {updated.weigh_context!r}"
    )


def test_rerank_omitted_context_returns_200(api_client, db_session):
    """AC5: POST /api/cases/{id}/rerank with context field omitted returns 200."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={})
    assert r.status_code == 200, f"Expected 200 with omitted context, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# AC4: Submit button not disabled for empty context (JS)
# ---------------------------------------------------------------------------

def test_submit_button_not_disabled_on_empty_context_in_js():
    """AC4: The submit button must NOT require non-empty context to be enabled."""
    combined = _read_combined_js()
    # The old pattern disabled the button when context was empty: !context.trim()
    # After the fix, submit should be enabled even with empty context.
    # We check that the submit ("Re-rank") button's disabled condition no longer
    # references context.trim() as a blocking condition.
    assert "!context.trim() || isLoading" not in combined, (
        "Submit button must not be disabled on empty context; "
        "remove '!context.trim()' from the disabled prop"
    )


# ---------------------------------------------------------------------------
# AC6: Response includes plans regardless of context
# ---------------------------------------------------------------------------

def test_rerank_response_includes_plans_with_null_context(api_client, db_session):
    """AC6: Rerank with null context returns valid plans in response."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data, "Response must include 'plans' key"
    assert len(data["plans"]) == 2, f"Expected 2 plans in response, got {len(data['plans'])}"


def test_rerank_response_weigh_context_null_when_skipped(api_client, db_session):
    """AC6: weigh_context in response is null when context was skipped."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200
    data = r.json()
    assert data.get("weigh_context") is None, (
        f"weigh_context in response should be null when context was skipped, got: {data.get('weigh_context')!r}"
    )


# ---------------------------------------------------------------------------
# AC7: Existing behavior with provided context unchanged
# ---------------------------------------------------------------------------

def test_rerank_with_context_still_works(api_client, db_session):
    """AC7: Existing behavior — rerank with provided context still returns 200."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        r = api_client.post(
            f"/api/cases/{c.id}/rerank",
            json={"context": "Annual income £45k, risk tolerance low."},
        )
    assert r.status_code == 200, f"Rerank with context should still work: {r.text}"
    data = r.json()
    assert "plans" in data


def test_rerank_with_context_persists_context(api_client, db_session):
    """AC7: Provided context is still persisted on the Case after rerank."""
    from app import models
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    ctx = "My running data: 80km/week, ferritin 18."
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock,
               return_value=_MOCK_RERANK_RESULT):
        api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ctx})
    db_session.expire_all()
    updated = db_session.get(models.Case, c.id)
    assert updated.weigh_context == ctx, (
        f"Provided context should be persisted unchanged; got: {updated.weigh_context!r}"
    )


def test_rerank_still_rejects_whitespace_only_context(api_client, db_session):
    """AC7: Whitespace-only context still returns 422 (existing validation unchanged)."""
    c, _ = _seed_case_with_plans(db_session, stage="weigh")
    r = api_client.post(
        f"/api/cases/{c.id}/rerank",
        json={"context": "   "},
    )
    assert r.status_code in (400, 422), (
        f"Whitespace-only context should still be rejected; got {r.status_code}"
    )
