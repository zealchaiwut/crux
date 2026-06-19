from pathlib import Path

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
from app.routers import cases_router, related_cases_router, sources_router

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


class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _UNPROTECTED:
            return await call_next(request)
        token = request.cookies.get("session", "")
        if not token or not verify_session_cookie(token, AUTH_SECRET):
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)


app = FastAPI(title="crux", version="0.1.0")
app.add_middleware(_AuthMiddleware)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(cases_router)
app.include_router(related_cases_router)
app.include_router(sources_router)


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
        return HTMLResponse(
            _LOGIN_PAGE.format(error='<p style="color:red">Too many attempts. Try again later.</p>'),
            status_code=429,
        )

    record_attempt(ip)

    if not check_password(password, AUTH_SECRET):
        return HTMLResponse(
            _LOGIN_PAGE.format(error='<p style="color:red">Invalid password.</p>'),
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
