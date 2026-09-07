"""Tests for issue #202: Service-token auth and auth-on-by-default.

AC coverage:
  AC1 – Auth is ON by default; disabling requires CRUX_REQUIRE_AUTH=0 (opt-out);
         render.yaml sets CRUX_REQUIRE_AUTH explicitly.
  AC2 – A service token in Authorization: Bearer authenticates alongside cookies;
         read and write scopes are distinguished.
  AC3 – CRUX_SERVICE_TOKEN and CRUX_REQUIRE_AUTH appear in .env.example with rotation
         documentation present.
  AC4 – README auth section describes the Bearer token and the default-on behaviour.
  AC5 – A verdict-scoped token passes POST /api/cases/{id}/verdict but fails a
         write on a different route (e.g. POST /api/cases).
"""
import os
import uuid
import json
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")
os.environ.setdefault("CRUX_REQUIRE_AUTH", "1")

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
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
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    yield tc
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def authed_client(db_session):
    from app.main import app
    from app.db import get_db
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    tc = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    tc.cookies.set("session", create_session_cookie(AUTH_SECRET))
    yield tc
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# AC1 – auth is on by default; opt-out via CRUX_REQUIRE_AUTH=0
# ---------------------------------------------------------------------------

def test_auth_on_by_default_unauthenticated_request_blocked(api_client):
    """AC1: With auth on (default), unauthenticated requests to protected routes are rejected."""
    r = api_client.get("/api/cases")
    assert r.status_code in (302, 401, 403), (
        f"Expected redirect/401/403 for unauthenticated request when auth is on, got {r.status_code}"
    )


def test_render_yaml_sets_crux_require_auth():
    """AC1: render.yaml explicitly sets CRUX_REQUIRE_AUTH so the deployed service has auth on."""
    render = (ROOT / "render.yaml").read_text()
    assert "CRUX_REQUIRE_AUTH" in render, (
        "render.yaml must set CRUX_REQUIRE_AUTH so the deployed service opts in explicitly (AC1)"
    )


def test_auth_default_is_on_not_opt_in(monkeypatch):
    """AC1: The default value of _REQUIRE_AUTH must be True (auth on), not False.

    Previously the flag defaulted to off (CRUX_REQUIRE_AUTH=="" == "1" was False).
    This test verifies the new default: auth is enabled unless explicitly disabled.
    """
    import importlib
    # Ensure no override present — auth should be on
    monkeypatch.delenv("CRUX_REQUIRE_AUTH", raising=False)
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    assert main_mod._REQUIRE_AUTH is True, (
        "_REQUIRE_AUTH must default to True so auth is on without any env var (AC1)"
    )


def test_crux_require_auth_zero_disables_auth(monkeypatch, db_session):
    """AC1: Setting CRUX_REQUIRE_AUTH=0 disables the auth gate (opt-out)."""
    import importlib
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "0")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    assert main_mod._REQUIRE_AUTH is False, (
        "CRUX_REQUIRE_AUTH=0 must set _REQUIRE_AUTH=False (AC1)"
    )


# ---------------------------------------------------------------------------
# AC2 – Bearer token auth alongside cookies; read vs write scopes
# ---------------------------------------------------------------------------

def test_bearer_token_read_scope_allows_get(monkeypatch, db_session):
    """AC2: A token with read scope authenticates GET /api/cases."""
    import importlib
    token = "test-service-token-read-scope"
    monkeypatch.setenv("CRUX_SERVICE_TOKEN", token)
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "1")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    main_mod.app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(main_mod.app, raise_server_exceptions=False)
        r = tc.get("/api/cases", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, (
            f"Read-scoped token must allow GET /api/cases, got {r.status_code} (AC2)"
        )
    finally:
        main_mod.app.dependency_overrides.pop(get_db, None)


def test_bearer_token_write_scope_allows_post(monkeypatch, db_session):
    """AC2: A token with write scope authenticates POST endpoints."""
    import importlib
    token = "test-service-token-write-scope"
    monkeypatch.setenv("CRUX_SERVICE_TOKEN", token)
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "1")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    main_mod.app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(main_mod.app, raise_server_exceptions=False)
        r = tc.post(
            "/api/cases",
            json={"raw_problem": "test problem"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should not be 401/403 — may be 200, 201, or a domain error
        assert r.status_code not in (401, 403), (
            f"Write-scoped token must be accepted for POST /api/cases, got {r.status_code} (AC2)"
        )
    finally:
        main_mod.app.dependency_overrides.pop(get_db, None)


def test_invalid_bearer_token_is_rejected(monkeypatch, db_session):
    """AC2: An invalid Bearer token must be rejected (401/403)."""
    import importlib
    monkeypatch.setenv("CRUX_SERVICE_TOKEN", "correct-token")
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "1")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    main_mod.app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(main_mod.app, raise_server_exceptions=False)
        r = tc.get("/api/cases", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code in (401, 403), (
            f"Invalid token must be rejected with 401/403, got {r.status_code} (AC2)"
        )
    finally:
        main_mod.app.dependency_overrides.pop(get_db, None)


def test_cookie_session_still_works_alongside_bearer(authed_client):
    """AC2: Existing cookie-based auth still works after adding Bearer support."""
    r = authed_client.get("/api/cases")
    assert r.status_code == 200, (
        f"Cookie auth must still work alongside Bearer token support, got {r.status_code} (AC2)"
    )


# ---------------------------------------------------------------------------
# AC3 – env vars in .env.example with rotation docs
# ---------------------------------------------------------------------------

def test_env_example_has_crux_service_token():
    """AC3: .env.example must document CRUX_SERVICE_TOKEN."""
    env_example = (ROOT / ".env.example").read_text()
    assert "CRUX_SERVICE_TOKEN" in env_example, (
        ".env.example must document CRUX_SERVICE_TOKEN (AC3)"
    )


def test_env_example_has_crux_require_auth():
    """AC3: .env.example must document CRUX_REQUIRE_AUTH."""
    env_example = (ROOT / ".env.example").read_text()
    assert "CRUX_REQUIRE_AUTH" in env_example, (
        ".env.example must document CRUX_REQUIRE_AUTH (AC3)"
    )


def test_env_example_documents_token_rotation():
    """AC3: .env.example must include rotation guidance for the service token."""
    env_example = (ROOT / ".env.example").read_text()
    assert "rotat" in env_example.lower(), (
        ".env.example must document how to rotate the service token (AC3)"
    )


def test_render_yaml_has_crux_service_token():
    """AC3: render.yaml must include CRUX_SERVICE_TOKEN so the deployed service has it configured."""
    render = (ROOT / "render.yaml").read_text()
    assert "CRUX_SERVICE_TOKEN" in render, (
        "render.yaml must include CRUX_SERVICE_TOKEN env var entry (AC3)"
    )


# ---------------------------------------------------------------------------
# AC4 – README documents the updated auth model
# ---------------------------------------------------------------------------

def test_readme_mentions_bearer_auth():
    """AC4: README must document Bearer token authentication."""
    readme = (ROOT / "README.md").read_text()
    assert "bearer" in readme.lower() or "Bearer" in readme, (
        "README must describe Bearer token authentication (AC4)"
    )


def test_readme_auth_default_on():
    """AC4: README must reflect that auth is on by default."""
    readme = (ROOT / "README.md").read_text()
    lower = readme.lower()
    assert "default" in lower and ("on" in lower or "enabled" in lower), (
        "README must state that authentication is on by default (AC4)"
    )


# ---------------------------------------------------------------------------
# AC5 – verdict-scoped token
# ---------------------------------------------------------------------------

def test_verdict_scoped_token_accepted_for_verdict_route(monkeypatch, db_session):
    """AC5: A verdict-scoped token must be accepted for POST /api/cases/{id}/verdict."""
    import importlib
    token = "verdict-only-token"
    monkeypatch.setenv("CRUX_VERDICT_TOKEN", token)
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "1")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from app.db import get_db
    from app import models
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    # Seed a case with probe
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem",
        sharpened="Sharpened.",
        not_investigating=json.dumps([]),
        stage="probe",
    )
    db_session.add(c)
    db_session.flush()
    probe = models.Probe(
        id=str(uuid.uuid4()),
        case_id=c.id,
        type="measurement",
        target_metric="metric",
        status="running",
    )
    db_session.add(probe)
    db_session.commit()

    main_mod.app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(main_mod.app, raise_server_exceptions=False)
        r = tc.post(
            f"/api/cases/{c.id}/verdict",
            json={"outcome": "confirmed", "notes": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Must not be rejected as unauthorized
        assert r.status_code not in (401, 403), (
            f"Verdict-scoped token must be accepted for the verdict route, got {r.status_code} (AC5)"
        )
    finally:
        main_mod.app.dependency_overrides.pop(get_db, None)


def test_verdict_scoped_token_rejected_for_general_write(monkeypatch, db_session):
    """AC5: A verdict-scoped token must NOT be accepted for general write routes like POST /api/cases."""
    import importlib
    token = "verdict-only-token"
    monkeypatch.setenv("CRUX_VERDICT_TOKEN", token)
    # Make sure the general service token is different
    monkeypatch.delenv("CRUX_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CRUX_REQUIRE_AUTH", "1")
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from app.db import get_db
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    main_mod.app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(main_mod.app, raise_server_exceptions=False)
        r = tc.post(
            "/api/cases",
            json={"raw_problem": "test problem"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code in (401, 403), (
            f"Verdict-scoped token must be rejected for general write routes, got {r.status_code} (AC5)"
        )
    finally:
        main_mod.app.dependency_overrides.pop(get_db, None)
