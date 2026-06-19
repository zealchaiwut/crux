"""Tests for issue #3: Single-user password auth with session cookies (UAT environment)."""
import os
import time

import httpx
import pytest

# Resolved from UAT .env at runtime; see tester skill Step 0.
# Default kept only as a last-resort fallback if BASE_URL not exported.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        yield c


# --- Acceptance Criteria ---

def test_issue_3__login_page_accessible(client):
    # AC3 — GET /login serves an HTML login form with a password field
    r = client.get("/login")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "<form" in r.text
    assert 'type="password"' in r.text or "type='password'" in r.text


def test_issue_3__failed_login_returns_401(client):
    # AC6 — On failed login, the server returns a 401 response and re-renders the login form
    r = client.post("/login", data={"password": "wrongpassword123"})
    assert r.status_code == 401
    assert "text/html" in r.headers.get("content-type", "")
    assert "<form" in r.text


def test_issue_3__failed_login_shows_error_message(client):
    # AC6 — Failed login re-renders the form with a generic error message
    r = client.post("/login", data={"password": "wrongpassword123"})
    body = r.text.lower()
    # Must contain some error indicator (invalid, incorrect, error, etc.)
    assert any(word in body for word in ["invalid", "incorrect", "error", "wrong", "too many"])


def test_issue_3__successful_login_redirects_to_root(client):
    # AC5 — On successful login, the server redirects to /
    # Note: AUTH_SECRET must be set in the UAT environment
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    r = client.post("/login", data={"password": secret})
    assert r.status_code in (302, 303)
    assert "/" in r.headers.get("location", "")


def test_issue_3__successful_login_sets_session_cookie(client):
    # AC5 — Session cookie is set on successful login with HttpOnly and SameSite=Strict
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    r = client.post("/login", data={"password": secret})
    set_cookie = r.headers.get("set-cookie", "")
    assert "session=" in set_cookie.lower()
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()


def test_issue_3__protected_route_without_session_redirects(client):
    # AC7 — All app routes (excluding /login) return 302 redirect to /login without valid session
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_issue_3__healthz_redirects_without_session(client):
    # AC7 — Even /healthz redirects to /login without valid session
    r = client.get("/healthz")
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_issue_3__protected_route_accessible_with_session(client):
    # AC5 & AC7 — With valid session cookie, protected routes are accessible
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    # Login first
    r = client.post("/login", data={"password": secret}, follow_redirects=False)
    cookies = client.cookies
    # Now access a protected route — should get 200, not redirect
    r = client.get("/healthz")
    assert r.status_code == 200


def test_issue_3__logout_clears_session(client):
    # AC8 — POST /logout clears the session cookie and redirects to /login
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    # Login first
    client.post("/login", data={"password": secret})
    # Then logout
    r = client.post("/logout")
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("location", "")
    # Try to access protected route — should redirect to /login
    r = client.get("/healthz", follow_redirects=False)
    assert r.status_code == 302


def test_issue_3__get_logout_works(client):
    # AC8 — GET /logout also works
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    client.post("/login", data={"password": secret})
    r = client.get("/logout")
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("location", "")


def test_issue_3__tampered_cookie_rejected(client):
    # AC9 — Tampered or forged cookies are rejected; browser is redirected to /login
    client.cookies.set("session", "tampered.invalid.forged.cookie")
    r = client.get("/healthz")
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_issue_3__empty_cookie_redirects(client):
    # AC9 — Empty session cookie is rejected
    client.cookies.set("session", "")
    r = client.get("/healthz")
    assert r.status_code == 302


def test_issue_3__rate_limit_after_10_attempts():
    # AC10 — Brute-force is mitigated; max 10 failed attempts per 15 minutes per IP
    # Create a fresh client to avoid rate-limit carryover from prior tests.
    with httpx.Client(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        # Make login attempts until we hit the rate limit (429)
        status_codes = []
        for i in range(15):
            r = c.post("/login", data={"password": "wrongpassword123"})
            status_codes.append(r.status_code)
        # We should see 401 errors initially, then 429 once rate limit is hit
        assert 401 in status_codes, f"Expected some 401 responses, got: {status_codes}"
        assert 429 in status_codes, f"Expected 429 rate-limit response, got: {status_codes}"
        # Verify that once 429 appears, it continues (rate limit stays active)
        first_429_idx = status_codes.index(429)
        assert all(s == 429 for s in status_codes[first_429_idx:]), \
            f"Rate limit should persist after first 429, got: {status_codes[first_429_idx:]}"


def test_issue_3__rate_limit_message_shown():
    # AC10 — Rate-limit response shows a message (e.g., "Too many attempts")
    # Use fresh client to avoid rate-limit carryover
    with httpx.Client(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        for i in range(10):
            c.post("/login", data={"password": "wrongpassword123"})
        r = c.post("/login", data={"password": "wrongpassword123"})
        assert r.status_code == 429
        body = r.text.lower()
        assert any(word in body for word in ["too many", "rate limit", "try again later"])


def test_issue_3__rate_limit_blocks_correct_password():
    # AC10 — Even a correct password is rejected when rate-limited
    secret = os.environ.get("AUTH_SECRET", "")
    if not secret:
        pytest.skip("AUTH_SECRET not set in UAT environment")
    # Use fresh client to avoid rate-limit carryover
    with httpx.Client(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        # Exhaust rate limit with wrong passwords
        for i in range(10):
            c.post("/login", data={"password": "wrongpassword123"})
        # Now try with correct password — should still get 429
        r = c.post("/login", data={"password": secret})
        assert r.status_code == 429
