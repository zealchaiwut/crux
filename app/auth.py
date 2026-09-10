import hmac
import re
import time

from itsdangerous import BadSignature, URLSafeSerializer

# Paths that the verdict-scoped token is allowed to POST to.
_VERDICT_PATH_RE = re.compile(r"^/api/(cases|probes)/[^/]+/verdict$")
_VERDICT_PATHS_EXACT = frozenset({"/api/hub/verify-claim"})

_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 900  # 15 minutes

_attempts: dict[str, list[float]] = {}


def reset_rate_limiter() -> None:
    _attempts.clear()


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    _attempts[ip] = recent
    return len(recent) >= _RATE_LIMIT_MAX


def record_attempt(ip: str) -> None:
    _attempts.setdefault(ip, []).append(time.time())


def check_password(submitted: str, secret: str) -> bool:
    return hmac.compare_digest(submitted.encode("utf-8"), secret.encode("utf-8"))


def create_session_cookie(secret: str) -> str:
    return URLSafeSerializer(secret, salt="session").dumps({"auth": True})


def verify_session_cookie(token: str, secret: str) -> bool:
    try:
        data = URLSafeSerializer(secret, salt="session").loads(token)
        return data.get("auth") is True
    except (BadSignature, Exception):
        return False


def check_bearer_scope(
    token: str,
    method: str,
    path: str,
    token_read: str,
    token_write: str,
    token_verdict: str,
) -> tuple[bool, bool]:
    """Return (token_known, scope_sufficient) for a Bearer token.

    token_known=False means the token didn't match any configured token → 401.
    token_known=True, scope_sufficient=False → 403.
    token_known=True, scope_sufficient=True → allow.
    """
    if not token:
        return False, False

    m = method.upper()

    if token_write and hmac.compare_digest(token.encode(), token_write.encode()):
        return True, True

    if token_read and hmac.compare_digest(token.encode(), token_read.encode()):
        return True, m == "GET"

    if token_verdict and hmac.compare_digest(token.encode(), token_verdict.encode()):
        allowed = m == "POST" and (
            bool(_VERDICT_PATH_RE.match(path)) or path in _VERDICT_PATHS_EXACT
        )
        return True, allowed

    return False, False
