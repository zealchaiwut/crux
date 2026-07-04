"""Tests for issue #142: Verify WeighPanel error messages don't reference 'required context'.

AC coverage:
  AC1 — No error message in WeighPanel JS contains 'context is required' or equivalent wording.
  AC2 — WeighPanel fallback error message describes failure, not a context-validation message.
  AC3 — Error handling for null/omitted context does not reference context; null context returns 200.
  AC4 — Client converts whitespace-only context to null before sending (no client-side context error).
  AC5 — No 'context is required', 'context required', or 'required context' string in cases.js.
"""
import os
import re
import uuid
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

STATIC = __import__("pathlib").Path(__file__).parent.parent / "app" / "static"
JS_DIR = STATIC / "js"


def _read_cases_js():
    return (JS_DIR / "cases.js").read_text()


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
        sharpened="Performance dropped 15% over 6 weeks.",
        stage=stage,
    )
    session.add(c)
    session.flush()
    for label, rank in [("A", 1), ("B", 2)]:
        session.add(
            models.Plan(
                id=str(uuid.uuid4()),
                case_id=c.id,
                label=label,
                name=f"Plan {label}",
                mechanism="Some mechanism.",
                prior="0.5",
                current_rank=rank,
            )
        )
    session.commit()
    return c


_MOCK_RERANK = [
    {"label": "A", "rank": 1, "standing": "ruled-in"},
    {"label": "B", "rank": 2, "standing": None},
]


# ---------------------------------------------------------------------------
# AC1 / AC5: No "context is required" phrases anywhere in cases.js
# ---------------------------------------------------------------------------


def test_no_context_is_required_phrase_in_cases_js():
    """AC1/AC5: 'context is required' must not appear in any string in cases.js."""
    src = _read_cases_js()
    assert "context is required" not in src.lower(), (
        "cases.js must not contain the phrase 'context is required'"
    )


def test_no_required_context_phrase_in_cases_js():
    """AC5: 'required context' must not appear in cases.js."""
    src = _read_cases_js()
    assert "required context" not in src.lower(), (
        "cases.js must not contain the phrase 'required context'"
    )


def test_no_context_required_phrase_in_cases_js():
    """AC5: 'context required' must not appear in cases.js."""
    src = _read_cases_js()
    assert "context required" not in src.lower(), (
        "cases.js must not contain the phrase 'context required'"
    )


# ---------------------------------------------------------------------------
# AC2: WeighPanel fallback error message is neutral (no context/required wording)
# ---------------------------------------------------------------------------


def test_weigh_panel_fallback_error_message_is_neutral():
    """AC2: Hard-coded fallback error string in WeighPanel must not mention context or 'required'."""
    src = _read_cases_js()
    weigh_panel_start = src.find("// WeighPanel")
    assert weigh_panel_start != -1, "cases.js must contain a WeighPanel section"
    weigh_panel_section = src[weigh_panel_start : weigh_panel_start + 3000]

    # Find all string literals that follow '|| "' or "|| '" patterns (fallback strings in setError)
    fallback_strings = re.findall(r'\|\|\s*["\']([^"\']+)["\']', weigh_panel_section)
    for s in fallback_strings:
        assert "context" not in s.lower(), (
            f"WeighPanel fallback string '{s}' must not reference 'context'"
        )
        assert "required" not in s.lower(), (
            f"WeighPanel fallback string '{s}' must not reference 'required'"
        )


def test_weigh_panel_fallback_message_exists_and_is_generic():
    """AC2: WeighPanel must have a generic fallback error message (not a context-validation string)."""
    src = _read_cases_js()
    weigh_panel_start = src.find("// WeighPanel")
    assert weigh_panel_start != -1
    weigh_panel_section = src[weigh_panel_start : weigh_panel_start + 3000]
    # A generic fallback like "Re-rank failed. Please try again." must be present
    assert "Re-rank failed" in weigh_panel_section or "failed" in weigh_panel_section.lower(), (
        "WeighPanel must have a generic fallback error message for rerank failures"
    )


# ---------------------------------------------------------------------------
# AC3: WeighPanel uses server-provided error detail, not a hard-coded context message
# ---------------------------------------------------------------------------


def test_weigh_panel_error_handling_uses_server_detail():
    """AC3: WeighPanel _postRerank uses data.detail from server response for error messages."""
    src = _read_cases_js()
    weigh_panel_start = src.find("// WeighPanel")
    assert weigh_panel_start != -1
    weigh_panel_section = src[weigh_panel_start : weigh_panel_start + 3000]
    assert "data.detail" in weigh_panel_section, (
        "WeighPanel must use 'data.detail' from the server response to display error reasons"
    )


def test_rerank_with_null_context_returns_200(api_client, db_session):
    """AC3: POST with null context returns 200 — no context error triggered when context is omitted."""
    c = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock, return_value=_MOCK_RERANK):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": None})
    assert r.status_code == 200, (
        f"null context must return 200 (no error); got {r.status_code}: {r.text}"
    )


def test_rerank_with_omitted_context_returns_200(api_client, db_session):
    """AC3: POST with context field omitted returns 200 — no context error for missing context."""
    c = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock, return_value=_MOCK_RERANK):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={})
    assert r.status_code == 200, (
        f"Omitted context must return 200 (no error); got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# AC4: Client trims context and sends null for whitespace-only input
# ---------------------------------------------------------------------------


def test_handle_rerank_converts_whitespace_to_null_in_js():
    """AC4: WeighPanel handleRerank must use context.trim() || null to convert whitespace to null."""
    src = _read_cases_js()
    assert "context.trim() || null" in src, (
        "cases.js must contain 'context.trim() || null' in handleRerank — "
        "this ensures whitespace-only context is sent as null, not as whitespace"
    )


def test_no_client_side_context_validation_in_weigh_panel():
    """AC4: WeighPanel must not have a client-side guard that errors on empty/whitespace context."""
    src = _read_cases_js()
    weigh_panel_start = src.find("// WeighPanel")
    assert weigh_panel_start != -1
    weigh_panel_section = src[weigh_panel_start : weigh_panel_start + 3000]
    # There must be no client-side early-return that fires an error for empty/blank context
    # (e.g., 'if (!context.trim()) { setError("..."); return; }')
    assert 'setError("context' not in weigh_panel_section.lower(), (
        "WeighPanel must not have a client-side setError call guarding on context content"
    )


def test_rerank_with_empty_string_context_returns_200(api_client, db_session):
    """AC4: POST with empty string context (treated as null by validator) returns 200."""
    c = _seed_case_with_plans(db_session)
    with patch("app.routers.cases.rerank_plans", new_callable=AsyncMock, return_value=_MOCK_RERANK):
        r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": ""})
    assert r.status_code == 200, (
        f"Empty string context must be accepted (treated as null); got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# AC1 / server side: 422 validator error message does not say "context is required"
# ---------------------------------------------------------------------------


def test_not_blank_validator_error_does_not_say_context_is_required():
    """AC1: Server-side not_blank validator error for whitespace context does not say 'context is required'."""
    from app.routers.cases import RerankRequest

    try:
        RerankRequest(context="   ")
        pytest.fail("Expected a validation error for whitespace-only context")
    except Exception as e:
        err_str = str(e).lower()
        assert "context is required" not in err_str, (
            f"Validator error must not say 'context is required'; got: {e}"
        )
        assert "required context" not in err_str, (
            f"Validator error must not say 'required context'; got: {e}"
        )
        assert "context required" not in err_str, (
            f"Validator error must not say 'context required'; got: {e}"
        )


def test_rerank_422_response_does_not_mention_context_is_required(api_client, db_session):
    """AC1: HTTP 422 response body for whitespace context does not contain 'context is required'."""
    c = _seed_case_with_plans(db_session)
    r = api_client.post(f"/api/cases/{c.id}/rerank", json={"context": "   "})
    assert r.status_code == 422
    body_lower = r.text.lower()
    assert "context is required" not in body_lower, (
        f"422 response must not contain 'context is required'; got: {r.text}"
    )
    assert "required context" not in body_lower, (
        f"422 response must not contain 'required context'; got: {r.text}"
    )
    assert "context required" not in body_lower, (
        f"422 response must not contain 'context required'; got: {r.text}"
    )
