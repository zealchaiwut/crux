import os
import sys

PORT: int = int(os.environ.get("PORT", "8000"))
ENV: str = os.environ.get("ENV", "development")

_raw_secret = os.environ.get("AUTH_SECRET", "")
if not _raw_secret:
    print(
        "FATAL: AUTH_SECRET environment variable is required and must be at least 16 characters long.",
        file=sys.stderr,
    )
    sys.exit(1)
if len(_raw_secret) < 16:
    print(
        f"FATAL: AUTH_SECRET must be at least 16 characters long (got {len(_raw_secret)}).",
        file=sys.stderr,
    )
    sys.exit(1)

AUTH_SECRET: str = _raw_secret
