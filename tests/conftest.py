import os

import pytest

# Must be set before any app module is imported at collection time
os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")


@pytest.fixture(autouse=True)
def reset_auth_state():
    from app.auth import reset_rate_limiter
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def auth_cookie():
    from app.auth import create_session_cookie
    from app.config import AUTH_SECRET
    return create_session_cookie(AUTH_SECRET)


@pytest.fixture
def authed_client(auth_cookie):
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    client.cookies.set("session", auth_cookie)
    return client
