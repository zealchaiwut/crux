"""Tests for issue #202: Service-token auth and auth-on-by-default.

Acceptance criteria:
  AC1 — Auth on by default; opt-out via CRUX_DISABLE_AUTH=1; render.yaml explicit
  AC2 — Bearer token with read/write scopes
  AC3 — Env vars in render.yaml and .env.example, rotation documented
  AC4 — README matches actual auth behaviour
  AC5 — Verdict-only token scope
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent

_WRITE_TOKEN = "test_write_token_for_202_abc"
_READ_TOKEN = "test_read_token_for_202_def"
_VERDICT_TOKEN = "test_verdict_token_for_202_ghi"


def fresh_client(raise_server_exceptions: bool = True):
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


# ---------------------------------------------------------------------------
# AC1 — Auth on by default
# ---------------------------------------------------------------------------

def test_auth_on_by_default_redirects_unauthenticated():
    """Without any credentials, protected routes redirect to /login."""
    client = fresh_client()
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_auth_disabled_with_crux_disable_auth(monkeypatch):
    """Patching _REQUIRE_AUTH=False (simulates CRUX_DISABLE_AUTH=1) bypasses the gate."""
    monkeypatch.setattr("app.main._REQUIRE_AUTH", False)
    client = fresh_client()
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 200


def test_render_yaml_sets_crux_disable_auth_explicitly():
    """render.yaml must declare CRUX_DISABLE_AUTH so the production config is unambiguous."""
    content = (REPO_ROOT / "render.yaml").read_text()
    config = yaml.safe_load(content)
    web = next(s for s in config["services"] if s.get("type") == "web")
    env_keys = [e["key"] for e in web.get("envVars", [])]
    assert "CRUX_DISABLE_AUTH" in env_keys


# ---------------------------------------------------------------------------
# AC2 — Bearer token with read / write scopes
# ---------------------------------------------------------------------------

def test_bearer_write_token_passes_get(monkeypatch):
    """Write-scoped Bearer token can access GET endpoints."""
    monkeypatch.setattr("app.main._TOKEN_WRITE", _WRITE_TOKEN)
    client = fresh_client()
    resp = client.get("/healthz", headers={"Authorization": f"Bearer {_WRITE_TOKEN}"})
    assert resp.status_code == 200


def test_bearer_write_token_passes_post(monkeypatch):
    """Write-scoped Bearer token can access POST endpoints (auth passes, may fail at DB layer)."""
    monkeypatch.setattr("app.main._TOKEN_WRITE", _WRITE_TOKEN)
    client = fresh_client(raise_server_exceptions=False)
    resp = client.post(
        "/api/cases",
        json={"raw_problem": "test"},
        headers={"Authorization": f"Bearer {_WRITE_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code not in (401, 403)


def test_bearer_read_token_passes_get(monkeypatch):
    """Read-scoped Bearer token can access GET endpoints."""
    monkeypatch.setattr("app.main._TOKEN_READ", _READ_TOKEN)
    client = fresh_client()
    resp = client.get("/healthz", headers={"Authorization": f"Bearer {_READ_TOKEN}"})
    assert resp.status_code == 200


def test_bearer_read_token_blocks_post(monkeypatch):
    """Read-scoped Bearer token is rejected on POST endpoints with 403."""
    monkeypatch.setattr("app.main._TOKEN_READ", _READ_TOKEN)
    client = fresh_client()
    resp = client.post(
        "/api/cases",
        json={"raw_problem": "test"},
        headers={"Authorization": f"Bearer {_READ_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_unknown_bearer_token_returns_401(monkeypatch):
    """An unrecognised Bearer token returns 401, not a redirect."""
    monkeypatch.setattr("app.main._TOKEN_WRITE", _WRITE_TOKEN)
    client = fresh_client()
    resp = client.get(
        "/healthz",
        headers={"Authorization": "Bearer completely_wrong_token_xyz"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


def test_no_auth_header_without_cookie_still_redirects():
    """No Authorization header and no session cookie → 302 to /login (not 401)."""
    client = fresh_client()
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# AC3 — Env vars in render.yaml and .env.example, rotation documented
# ---------------------------------------------------------------------------

def test_env_example_documents_token_vars():
    """.env.example must mention CRUX_TOKEN_ service token variables."""
    content = (REPO_ROOT / ".env.example").read_text()
    assert "CRUX_TOKEN_" in content


def test_env_example_documents_rotation():
    """.env.example or README must mention token rotation."""
    example = (REPO_ROOT / ".env.example").read_text()
    readme = (REPO_ROOT / "README.md").read_text()
    combined = example + readme
    assert "rotat" in combined.lower()


def test_render_yaml_has_at_least_one_token_env_var():
    """render.yaml must declare at least one CRUX_TOKEN_* service token slot."""
    content = (REPO_ROOT / "render.yaml").read_text()
    config = yaml.safe_load(content)
    web = next(s for s in config["services"] if s.get("type") == "web")
    env_keys = [e["key"] for e in web.get("envVars", [])]
    assert any(k.startswith("CRUX_TOKEN_") for k in env_keys)


# ---------------------------------------------------------------------------
# AC4 — README matches actual auth behaviour
# ---------------------------------------------------------------------------

def test_readme_mentions_bearer_token():
    """README must describe Bearer token authentication for service callers."""
    content = (REPO_ROOT / "README.md").read_text()
    assert "Bearer" in content or "bearer" in content.lower()


def test_readme_does_not_say_auth_is_opt_in():
    """README must not describe auth as opt-in (CRUX_REQUIRE_AUTH was the old opt-in var)."""
    content = (REPO_ROOT / "README.md").read_text()
    assert "CRUX_REQUIRE_AUTH" not in content


def test_readme_describes_auth_on_by_default():
    """README must describe auth as on by default."""
    content = (REPO_ROOT / "README.md").read_text()
    lower = content.lower()
    assert "by default" in lower or "default" in lower


# ---------------------------------------------------------------------------
# AC5 — Verdict-only token scope
# ---------------------------------------------------------------------------

def test_verdict_token_allows_case_verdict_post(monkeypatch):
    """Verdict-scoped token can POST to /api/cases/{id}/verdict."""
    monkeypatch.setattr("app.main._TOKEN_VERDICT", _VERDICT_TOKEN)
    client = fresh_client(raise_server_exceptions=False)
    resp = client.post(
        "/api/cases/nonexistent-id/verdict",
        json={"outcome": "confirmed"},
        headers={"Authorization": f"Bearer {_VERDICT_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code not in (401, 403)


def test_verdict_token_allows_probe_verdict_post(monkeypatch):
    """Verdict-scoped token can POST to /api/probes/{id}/verdict."""
    monkeypatch.setattr("app.main._TOKEN_VERDICT", _VERDICT_TOKEN)
    client = fresh_client(raise_server_exceptions=False)
    resp = client.post(
        "/api/probes/nonexistent-probe/verdict",
        json={"outcome": "confirmed"},
        headers={"Authorization": f"Bearer {_VERDICT_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code not in (401, 403)


def test_verdict_token_allows_hub_verify_claim(monkeypatch):
    """Verdict-scoped token can POST to /api/hub/verify-claim (content-post verdicts)."""
    monkeypatch.setattr("app.main._TOKEN_VERDICT", _VERDICT_TOKEN)
    client = fresh_client()
    resp = client.post(
        "/api/hub/verify-claim",
        json={"claim": "some claim text"},
        headers={"Authorization": f"Bearer {_VERDICT_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code not in (401, 403)


def test_verdict_token_blocks_general_post(monkeypatch):
    """Verdict-scoped token cannot POST to non-verdict endpoints (403)."""
    monkeypatch.setattr("app.main._TOKEN_VERDICT", _VERDICT_TOKEN)
    client = fresh_client()
    resp = client.post(
        "/api/cases",
        json={"raw_problem": "test"},
        headers={"Authorization": f"Bearer {_VERDICT_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_verdict_token_blocks_general_get(monkeypatch):
    """Verdict-scoped token cannot GET general endpoints (403 — not verdict scope)."""
    monkeypatch.setattr("app.main._TOKEN_VERDICT", _VERDICT_TOKEN)
    client = fresh_client()
    resp = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {_VERDICT_TOKEN}"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
