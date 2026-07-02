import os
from pathlib import Path

# Load .env before importing app.config (which reads env at import time).
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import (
    check_password,
    create_session_cookie,
    is_rate_limited,
    record_attempt,
    verify_session_cookie,
)
from app.config import AUTH_SECRET, ENV
from app.routers import (
    cases_router,
    gather_router,
    notebooklm_router,
    probes_router,
    related_cases_router,
    settings_router,
    sources_router,
    verdicts_router,
)

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"

_LOGIN_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Login – Crux</title></head>
<body>
  <h1>Login</h1>
  {error}
  <form method="post" action="/login">
    <label>Password: <input type="password" name="password" autofocus></label>
    <button type="submit">Login</button>
  </form>
</body>
</html>
"""

_UNPROTECTED = {"/login"}


# Auth disabled for single-user local use. Set CRUX_REQUIRE_AUTH=1 to re-enable
# the session-cookie gate (login page + AUTH_SECRET password).
_REQUIRE_AUTH = os.environ.get("CRUX_REQUIRE_AUTH", "") == "1"


class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _REQUIRE_AUTH or request.url.path in _UNPROTECTED:
            return await call_next(request)
        token = request.cookies.get("session", "")
        if not token or not verify_session_cookie(token, AUTH_SECRET):
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)


app = FastAPI(title="crux", version="0.1.0")
app.add_middleware(_AuthMiddleware)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(cases_router)
app.include_router(gather_router)
app.include_router(notebooklm_router)
app.include_router(probes_router)
app.include_router(related_cases_router)
app.include_router(settings_router)
app.include_router(sources_router)
app.include_router(verdicts_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "env": ENV}


@app.get("/login", response_class=HTMLResponse)
def login_form():
    return _LOGIN_PAGE.format(error="")


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, password: str = Form(...)):
    ip = request.client.host if request.client else "unknown"

    if is_rate_limited(ip):
        msg = '<p style="color:red">Too many attempts. Try again later.</p>'
        return HTMLResponse(
            _LOGIN_PAGE.format(error=msg),
            status_code=429,
        )

    record_attempt(ip)

    if not check_password(password, AUTH_SECRET):
        msg = '<p style="color:red">Invalid password.</p>'
        return HTMLResponse(
            _LOGIN_PAGE.format(error=msg),
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_cookie(AUTH_SECRET),
        httponly=True,
        samesite="strict",
    )
    return response


@app.get("/logout")
@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session", httponly=True, samesite="strict")
    return response


@app.get("/")
def index():
    return FileResponse(_INDEX_HTML)


@app.get("/cases")
def cases():
    return FileResponse(_INDEX_HTML)


@app.get("/cases/{case_id}")
def case_detail(case_id: str):
    return FileResponse(_INDEX_HTML)


@app.get("/probes")
def probes():
    return FileResponse(_INDEX_HTML)


@app.get("/verdicts")
def verdicts():
    return FileResponse(_INDEX_HTML)
