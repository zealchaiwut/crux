"""Tests for issue #74: Add fallback for API error messages in edit modal.

AC coverage (static analysis of cases.js + backend API):
  AC1 – handleSave() uses data.detail as the error message when detail is present
  AC2 – When detail is absent, a fallback message is shown (not undefined or blank)
  AC3 – The fallback message is 'An unexpected error occurred.' (or err.message if present)
  AC4 – Happy path: successful save closes the modal (onClose called, no error set)
"""
import re
import pathlib
import json
import uuid
import os

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

CASES_JS = pathlib.Path(__file__).parent.parent / "app" / "static" / "js" / "cases.js"
FALLBACK_MSG = "An unexpected error occurred."


def _src():
    return CASES_JS.read_text()


def _handleSave_block(src):
    """Extract the handleSave function body from cases.js."""
    match = re.search(
        r'async function handleSave\(\)\s*\{(.+?)(?=\n  (?:async function|function|const (?!data|items|resp)|}\s*$))',
        src,
        re.DOTALL,
    )
    assert match, "handleSave function not found in cases.js"
    return match.group(0)


# ---------------------------------------------------------------------------
# AC1: data.detail is used when present
# ---------------------------------------------------------------------------

def test_ac1_handleSave_reads_data_detail():
    """AC1: handleSave accesses data.detail from the API error response."""
    src = _src()
    block = _handleSave_block(src)
    assert "data.detail" in block, (
        "handleSave must access data.detail from the API error response"
    )


def test_ac1_handleSave_detail_used_in_error_throw():
    """AC1: data.detail is used (directly or via err) when constructing the error."""
    src = _src()
    block = _handleSave_block(src)
    # detail must flow into the error path — either throw or setError
    assert "data.detail" in block, (
        "data.detail must appear in handleSave error path"
    )
    # The error must be passed to err.message or setError
    assert "err.message" in block or "setError" in block, (
        "handleSave must propagate the error message to the UI"
    )


# ---------------------------------------------------------------------------
# AC2: fallback exists when detail is absent
# ---------------------------------------------------------------------------

def test_ac2_handleSave_has_fallback_for_missing_detail():
    """AC2: When data.detail is absent, handleSave shows a fallback, not undefined."""
    src = _src()
    block = _handleSave_block(src)
    # Either the throw uses a fallback or the catch uses a fallback
    # Pattern: data.detail || <something>  OR  err.message || <something>
    has_throw_fallback = bool(re.search(r'data\.detail\s*\|\|', block))
    has_catch_fallback = bool(re.search(r'err\.message\s*\|\|', block))
    assert has_throw_fallback or has_catch_fallback, (
        "handleSave must have a fallback (||) for when data.detail is absent"
    )


def test_ac2_handleSave_does_not_set_error_from_raw_detail_only():
    """AC2: setError is not called with data.detail directly (without a fallback)."""
    src = _src()
    block = _handleSave_block(src)
    # setError(data.detail) with no fallback would show undefined
    direct_detail_only = re.search(r'setError\(\s*data\.detail\s*\)', block)
    assert not direct_detail_only, (
        "setError must not be called with bare data.detail — "
        "a fallback is required to prevent undefined from being displayed"
    )


# ---------------------------------------------------------------------------
# AC3: fallback message is 'An unexpected error occurred.'
# ---------------------------------------------------------------------------

def test_ac3_fallback_message_is_correct_string():
    """AC3: The literal fallback string is 'An unexpected error occurred.'"""
    src = _src()
    block = _handleSave_block(src)
    assert FALLBACK_MSG in block, (
        f"handleSave must contain the fallback string '{FALLBACK_MSG}'"
    )


def test_ac3_fallback_is_non_empty_human_readable():
    """AC3: The fallback message is a non-empty, human-readable string."""
    src = _src()
    block = _handleSave_block(src)
    # Any || "..." fallback in the block must be non-empty
    fallbacks = re.findall(r'\|\|\s*["\']([^"\']+)["\']', block)
    assert any(len(f.strip()) > 0 for f in fallbacks), (
        "handleSave must have at least one non-empty fallback string"
    )


# ---------------------------------------------------------------------------
# AC4: happy path — successful save closes modal (backend integration)
# ---------------------------------------------------------------------------

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
    cookie = create_session_cookie(AUTH_SECRET)
    client = TestClient(app)
    client.cookies.set("session", cookie)
    yield client
    app.dependency_overrides.pop(get_db, None)


def _create_case(db, sharpened="Test statement", not_investigating=None):
    from datetime import datetime, timezone
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="raw problem",
        sharpened=sharpened,
        not_investigating=json.dumps(not_investigating or []),
        stage="sharpened",
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def test_ac4_successful_patch_returns_200(api_client, db_session):
    """AC4: A valid PATCH /api/cases/{id} returns 200 (modal would close normally)."""
    case = _create_case(db_session)
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated statement", "not_investigating": []},
    )
    assert resp.status_code == 200, (
        f"Successful PATCH must return 200, got {resp.status_code}"
    )


def test_ac4_successful_patch_returns_updated_case(api_client, db_session):
    """AC4: A valid PATCH returns the updated case data (used by onSaved callback)."""
    case = _create_case(db_session, sharpened="Original")
    resp = api_client.patch(
        f"/api/cases/{case.id}",
        json={"sharpened": "Updated statement"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sharpened"] == "Updated statement", (
        "Response must contain the updated sharpened value for the onSaved callback"
    )


def test_ac4_handleSave_calls_onClose_on_success():
    """AC4: handleSave calls onClose() on the happy path (static analysis)."""
    src = _src()
    block = _handleSave_block(src)
    assert "onClose()" in block, (
        "handleSave must call onClose() after a successful save"
    )
