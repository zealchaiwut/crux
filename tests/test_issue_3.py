"""Tests for issue #3: Single-user password auth with session cookies."""
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).parent.parent
_AUTH_SECRET = os.environ["AUTH_SECRET"]


def fresh_client():
    from app.main import app
    return TestClient(app)


# AC1 — App reads AUTH_SECRET from env var

def test_auth_secret_readable_from_env():
    from app.config import AUTH_SECRET
    assert AUTH_SECRET == _AUTH_SECRET


# AC2 — App refuses to start without valid AUTH_SECRET

def test_startup_fails_without_auth_secret():
    env = {k: v for k, v in os.environ.items() if k != "AUTH_SECRET"}
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "AUTH_SECRET" in combined


def test_startup_fails_with_short_auth_secret():
    env = {**os.environ, "AUTH_SECRET": "tooshort"}
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0


def test_startup_fails_with_empty_auth_secret():
    env = {**os.environ, "AUTH_SECRET": ""}
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0


def test_startup_error_message_is_descriptive():
    env = {k: v for k, v in os.environ.items() if k != "AUTH_SECRET"}
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    combined = result.stdout + result.stderr
    # Error must mention the variable and the constraint
    assert "AUTH_SECRET" in combined
    assert any(word in combined.lower() for word in ["required", "missing", "must", "fatal"])


# AC3 — GET /login serves HTML form with password field

def test_login_page_returns_200():
    client = fresh_client()
    response = client.get("/login")
    assert response.status_code == 200


def test_login_page_returns_html():
    client = fresh_client()
    response = client.get("/login")
    assert "text/html" in response.headers.get("content-type", "")


def test_login_form_has_password_field():
    client = fresh_client()
    body = client.get("/login").text
    assert "<form" in body
    assert 'type="password"' in body or "type='password'" in body


def test_login_form_posts_to_login():
    client = fresh_client()
    body = client.get("/login").text
    assert 'action="/login"' in body or "action='/login'" in body or 'method="post"' in body.lower() or "method='post'" in body.lower()


# AC4 — POST /login validates password with constant-time comparison

def test_login_wrong_password_returns_401():
    client = fresh_client()
    response = client.post("/login", data={"password": "wrongpassword!!!"}, follow_redirects=False)
    assert response.status_code == 401


def test_login_correct_password_returns_redirect():
    client = fresh_client()
    response = client.post("/login", data={"password": _AUTH_SECRET}, follow_redirects=False)
    assert response.status_code in (302, 303)


# AC5 — Successful login: signed HttpOnly SameSite=Strict cookie + redirect to /

def test_successful_login_redirects_to_root():
    client = fresh_client()
    response = client.post("/login", data={"password": _AUTH_SECRET}, follow_redirects=False)
    location = response.headers.get("location", "")
    assert location in ("/", "http://testserver/")


def test_successful_login_sets_httponly_cookie():
    client = fresh_client()
    response = client.post("/login", data={"password": _AUTH_SECRET}, follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()


def test_successful_login_sets_samesite_strict():
    client = fresh_client()
    response = client.post("/login", data={"password": _AUTH_SECRET}, follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    assert "samesite=strict" in set_cookie.lower()


def test_successful_login_sets_session_cookie():
    client = fresh_client()
    response = client.post("/login", data={"password": _AUTH_SECRET}, follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    assert set_cookie != ""


# AC6 — Failed login: 401 + re-render form with generic error, no info leakage

def test_failed_login_rerenders_form():
    client = fresh_client()
    response = client.post("/login", data={"password": "wrongpassword!!!"})
    body = response.text
    assert "<form" in body
    assert 'type="password"' in body or "type='password'" in body


def test_failed_login_shows_generic_error_message():
    client = fresh_client()
    response = client.post("/login", data={"password": "wrongpassword!!!"})
    body = response.text.lower()
    assert any(word in body for word in ["invalid", "incorrect", "error", "wrong"])


def test_failed_login_no_session_cookie():
    client = fresh_client()
    response = client.post("/login", data={"password": "wrongpassword!!!"}, follow_redirects=False)
    assert response.status_code == 401
    set_cookie = response.headers.get("set-cookie", "")
    # No session cookie should be set on failure
    assert "session=" not in set_cookie.lower() or "session=;" in set_cookie.lower() or set_cookie == ""


# AC7 — All non-/login routes redirect to /login without session cookie

def test_root_redirects_to_login_without_session():
    client = fresh_client()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_healthz_redirects_to_login_without_session():
    client = fresh_client()
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_protected_route_accessible_with_valid_session(authed_client):
    response = authed_client.get("/healthz", follow_redirects=False)
    assert response.status_code == 200


# AC8 — Logout clears cookie and redirects to /login

def test_logout_redirects_to_login():
    client = fresh_client()
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers.get("location", "")


def test_logout_clears_session_cookie(auth_cookie):
    client = fresh_client()
    client.cookies.set("session", auth_cookie)
    response = client.post("/logout", follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    # Cookie cleared: either max-age=0, expires in past, or empty value
    assert "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()


def test_after_logout_protected_routes_redirect():
    client = fresh_client()
    # Login via the proper form flow so httpx tracks the cookie with full domain context
    client.post("/login", data={"password": _AUTH_SECRET})
    assert client.get("/healthz", follow_redirects=False).status_code == 200
    # Logout
    client.post("/logout")
    # Now protected route must redirect again
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_get_logout_also_works(auth_cookie):
    client = fresh_client()
    client.cookies.set("session", auth_cookie)
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers.get("location", "")


# AC9 — Session cookie is signed; tampered cookie is rejected

def test_tampered_cookie_redirects_to_login():
    client = fresh_client()
    client.cookies.set("session", "tampered.invalid.cookie.value")
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_empty_cookie_redirects_to_login():
    client = fresh_client()
    client.cookies.set("session", "")
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 302


def test_forged_unsigned_cookie_is_rejected():
    client = fresh_client()
    # Plain JSON that looks like the payload but isn't signed
    client.cookies.set("session", '{"auth": true}')
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


# AC10 — Rate limiting: max 10 attempts per 15 minutes per IP

def test_rate_limit_after_ten_failed_logins():
    from app.auth import reset_rate_limiter
    reset_rate_limiter()
    client = fresh_client()
    for _ in range(10):
        client.post("/login", data={"password": "wrongpassword!!!"})
    response = client.post("/login", data={"password": "wrongpassword!!!"})
    assert response.status_code == 429


def test_rate_limit_blocks_before_password_check():
    """After 10 attempts, even a correct password returns 429 (checked before password)."""
    from app.auth import reset_rate_limiter
    reset_rate_limiter()
    client = fresh_client()
    for _ in range(10):
        client.post("/login", data={"password": "wrongpassword!!!"})
    response = client.post("/login", data={"password": _AUTH_SECRET})
    assert response.status_code == 429


# AC11 — No plaintext password in server logs

def test_no_plaintext_password_in_logs(caplog):
    import logging
    client = fresh_client()
    secret = _AUTH_SECRET
    with caplog.at_level(logging.DEBUG):
        client.post("/login", data={"password": secret})
    for record in caplog.records:
        assert secret not in record.getMessage(), f"Password leaked to logs: {record.getMessage()}"
