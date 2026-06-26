"""Database session factory for crux.

Production: Neon Postgres via DATABASE_URL environment variable.
Tests: caller overrides get_db() dependency with an in-memory SQLite session.
"""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DATABASE_URL = os.environ.get("DATABASE_URL", "")

if _DATABASE_URL:
    # pool_pre_ping revalidates a pooled connection before use; pool_recycle
    # drops connections older than 5 min. Both guard against Neon (serverless
    # Postgres) closing idle connections during slow Claude calls, which
    # otherwise surfaces as "SSL connection has been closed unexpectedly".
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
else:
    engine = None

_SessionLocal: sessionmaker | None = (
    sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
)


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure it or override get_db() in tests."
        )
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
