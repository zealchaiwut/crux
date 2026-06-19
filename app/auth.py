import hmac
import time

from itsdangerous import BadSignature, URLSafeSerializer

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
