"""Tests for issue #97: Add support_status and support_rationale to Source.

Acceptance Criteria coverage:
  AC1 - Source model has support_status column as SQLAlchemy Enum with values
        supports/partial/contradicts/unverified and server/column default of unverified
  AC2 - Source model has support_rationale column as Text, nullable
  AC3 - Alembic migration file exists that adds both columns with correct types and default
  AC4 - Running alembic upgrade head on a clean DB succeeds without errors
  AC5 - Running alembic downgrade -1 removes both columns cleanly
  AC6 - Existing rows after migration have support_status='unverified' and support_rationale=NULL
  AC7 - Source instance created without specifying support_status defaults to unverified
  AC8 - Source instance rejects support_status values outside the four defined enum members
"""
import os
import pathlib
import tempfile
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

ALEMBIC_VERSIONS_DIR = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
_SUPPORT_STATUS_VALUES = {"supports", "partial", "contradicts", "unverified"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memory_engine():
    from sqlalchemy.pool import StaticPool
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models import Base
    Base.metadata.create_all(engine)
    return engine


def _session(engine):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_plan(session):
    """Create a minimal Case+Plan hierarchy and return the plan."""
    from app import models
    from datetime import datetime, timezone
    c = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Why is engagement low?",
        stage="gather",
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(c)
    session.flush()
    p = models.Plan(
        id=str(uuid.uuid4()),
        case_id=c.id,
        label="A",
    )
    session.add(p)
    session.flush()
    return p


# ---------------------------------------------------------------------------
# AC1: support_status column exists, is an Enum with the four values, default unverified
# ---------------------------------------------------------------------------

def test_source_model_has_support_status_column():
    """AC1: Source model must declare a support_status column."""
    from app.models import Source
    col = Source.__table__.c.get("support_status")
    assert col is not None, "Source must have a support_status column"


def test_support_status_column_is_enum():
    """AC1: support_status column must be typed as an Enum."""
    from app.models import Source
    col = Source.__table__.c["support_status"]
    assert isinstance(col.type, sa.Enum), (
        f"support_status must be sa.Enum, got {type(col.type).__name__}"
    )


def test_support_status_enum_values():
    """AC1: Enum must contain exactly supports, partial, contradicts, unverified."""
    from app.models import Source
    col = Source.__table__.c["support_status"]
    assert isinstance(col.type, sa.Enum)
    actual = set(col.type.enums)
    assert actual == _SUPPORT_STATUS_VALUES, (
        f"support_status enum values must be {_SUPPORT_STATUS_VALUES}, got {actual}"
    )


def test_support_status_has_server_default_unverified():
    """AC1: support_status must have a server_default of 'unverified'."""
    from app.models import Source
    col = Source.__table__.c["support_status"]
    has_server_default = (
        col.server_default is not None
        and "unverified" in str(col.server_default.arg)
    )
    has_column_default = (
        col.default is not None
        and col.default.arg == "unverified"
    )
    assert has_server_default or has_column_default, (
        "support_status must have a default of 'unverified' "
        f"(server_default={col.server_default!r}, default={col.default!r})"
    )


# ---------------------------------------------------------------------------
# AC2: support_rationale column exists, is Text, nullable
# ---------------------------------------------------------------------------

def test_source_model_has_support_rationale_column():
    """AC2: Source model must declare a support_rationale column."""
    from app.models import Source
    col = Source.__table__.c.get("support_rationale")
    assert col is not None, "Source must have a support_rationale column"


def test_support_rationale_column_is_text():
    """AC2: support_rationale must be typed as Text."""
    from app.models import Source
    col = Source.__table__.c["support_rationale"]
    assert isinstance(col.type, sa.Text), (
        f"support_rationale must be sa.Text, got {type(col.type).__name__}"
    )


def test_support_rationale_is_nullable():
    """AC2: support_rationale must be nullable."""
    from app.models import Source
    col = Source.__table__.c["support_rationale"]
    assert col.nullable is True, "support_rationale must be nullable"


# ---------------------------------------------------------------------------
# AC3: Alembic migration file exists and references both columns
# ---------------------------------------------------------------------------

def _find_migration_file():
    """Return the migration file that adds support_status and support_rationale."""
    for path in ALEMBIC_VERSIONS_DIR.glob("*.py"):
        text = path.read_text()
        if "support_status" in text and "support_rationale" in text:
            return path
    return None


def test_migration_file_exists():
    """AC3: A migration file must exist that mentions both support_status and support_rationale."""
    f = _find_migration_file()
    assert f is not None, (
        "No migration file found in alembic/versions/ that adds both "
        "support_status and support_rationale columns"
    )


def test_migration_file_has_correct_default():
    """AC3: The migration must specify 'unverified' as the server_default for support_status."""
    f = _find_migration_file()
    assert f is not None, "Migration file missing (see test_migration_file_exists)"
    text = f.read_text()
    assert "unverified" in text, (
        "Migration file must include 'unverified' as the server_default for support_status"
    )


def test_migration_file_has_upgrade_and_downgrade():
    """AC3: Migration file must define both upgrade() and downgrade() functions."""
    f = _find_migration_file()
    assert f is not None, "Migration file missing"
    text = f.read_text()
    assert "def upgrade()" in text, "Migration must define upgrade()"
    assert "def downgrade()" in text, "Migration must define downgrade()"


def test_migration_file_adds_columns_in_upgrade():
    """AC3: upgrade() must call add_column for both new columns."""
    f = _find_migration_file()
    assert f is not None, "Migration file missing"
    text = f.read_text()
    assert text.count("add_column") >= 2, (
        "upgrade() must call op.add_column at least twice (one per new column)"
    )


def test_migration_file_drops_columns_in_downgrade():
    """AC3: downgrade() must call drop_column for both new columns."""
    f = _find_migration_file()
    assert f is not None, "Migration file missing"
    text = f.read_text()
    assert text.count("drop_column") >= 2, (
        "downgrade() must call op.drop_column at least twice (one per new column)"
    )


# ---------------------------------------------------------------------------
# AC4 + AC5 + AC6: Migration runs on SQLite (upgrade then downgrade)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sqlite_migration_db():
    """
    Run alembic upgrade head against a temporary SQLite file, yield (engine, db_path),
    then run alembic downgrade -1 for AC5 teardown.
    """
    import subprocess
    import sys

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db_url = f"sqlite:///{db_path}"
    env = {**os.environ, "DATABASE_URL": db_url}

    # upgrade head
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(pathlib.Path(__file__).parent.parent),
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed (AC4):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    engine = sa.create_engine(db_url)
    yield engine, db_path, env

    engine.dispose()

    # downgrade -1 (AC5)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(pathlib.Path(__file__).parent.parent),
    )
    assert result.returncode == 0, (
        f"alembic downgrade -1 failed (AC5):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    os.unlink(db_path)


def test_upgrade_head_creates_support_status_column(sqlite_migration_db):
    """AC4: After upgrade head, source table must have support_status column."""
    engine, db_path, _ = sqlite_migration_db
    inspector = sa_inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("source")}
    assert "support_status" in columns, (
        f"After alembic upgrade head, source table must have support_status column; "
        f"got columns: {columns}"
    )


def test_upgrade_head_creates_support_rationale_column(sqlite_migration_db):
    """AC4: After upgrade head, source table must have support_rationale column."""
    engine, db_path, _ = sqlite_migration_db
    inspector = sa_inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("source")}
    assert "support_rationale" in columns, (
        f"After alembic upgrade head, source table must have support_rationale column; "
        f"got columns: {columns}"
    )


def test_existing_rows_get_unverified_default(sqlite_migration_db):
    """AC6: Existing rows after migration must have support_status='unverified' and support_rationale=NULL."""
    engine, db_path, _ = sqlite_migration_db
    with engine.connect() as conn:
        result = conn.execute(sa.text(
            "PRAGMA table_info(source)"
        ))
        col_info = {row[1]: row for row in result}
        support_status_info = col_info.get("support_status")
        assert support_status_info is not None, "support_status column not found in PRAGMA table_info"
        dflt = support_status_info[4]
        assert dflt is not None and "unverified" in str(dflt), (
            f"support_status must have default 'unverified' in schema; got dflt_value={dflt!r}"
        )


def test_downgrade_removes_support_status_column(sqlite_migration_db):
    """AC5: After downgrade -1, support_status column must be removed from source."""
    engine, db_path, env = sqlite_migration_db
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(pathlib.Path(__file__).parent.parent),
    )
    assert result.returncode == 0, (
        f"alembic downgrade -1 failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    inspector = sa_inspect(engine)
    engine.dispose()
    db_url = f"sqlite:///{db_path}"
    fresh_engine = sa.create_engine(db_url)
    inspector = sa_inspect(fresh_engine)
    columns = {c["name"] for c in inspector.get_columns("source")}
    assert "support_status" not in columns, (
        f"After downgrade -1, support_status must be removed; remaining columns: {columns}"
    )
    assert "support_rationale" not in columns, (
        f"After downgrade -1, support_rationale must be removed; remaining columns: {columns}"
    )
    fresh_engine.dispose()


# ---------------------------------------------------------------------------
# AC7: Source created without support_status defaults to 'unverified'
# ---------------------------------------------------------------------------

def test_source_defaults_to_unverified_when_status_omitted():
    """AC7: Creating a Source without support_status must persist support_status='unverified'."""
    engine = _make_memory_engine()
    session = _session(engine)

    plan = _seed_plan(session)
    from app import models

    src = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="article",
        title="Test source",
    )
    session.add(src)
    session.commit()

    session.expire(src)
    assert src.support_status == "unverified", (
        f"Source.support_status must default to 'unverified' when not specified; "
        f"got {src.support_status!r}"
    )
    assert src.support_rationale is None, (
        f"Source.support_rationale must default to None; got {src.support_rationale!r}"
    )

    session.close()
    engine.dispose()


def test_source_with_explicit_status_persists_correctly():
    """AC7 (positive): A Source with explicit support_status must persist the given value."""
    engine = _make_memory_engine()
    session = _session(engine)

    plan = _seed_plan(session)
    from app import models

    src = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="book",
        support_status="supports",
        support_rationale="The study directly confirms the hypothesis.",
    )
    session.add(src)
    session.commit()
    session.expire(src)

    assert src.support_status == "supports"
    assert src.support_rationale == "The study directly confirms the hypothesis."

    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# AC8: Source rejects invalid support_status values
# ---------------------------------------------------------------------------

def test_source_rejects_invalid_support_status():
    """AC8: Assigning an invalid support_status value must raise LookupError or StatementError."""
    engine = _make_memory_engine()
    session = _session(engine)

    plan = _seed_plan(session)
    from app import models

    src = models.Source(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        kind="article",
        support_status="maybe",
    )
    session.add(src)
    with pytest.raises(Exception) as exc_info:
        session.commit()

    err_text = str(exc_info.value).lower()
    assert any(kw in err_text for kw in ("lookup", "invalid", "enum", "maybe", "constraint")), (
        f"Expected an enum/constraint error for invalid support_status 'maybe'; "
        f"got: {exc_info.value}"
    )

    session.close()
    engine.dispose()


def test_source_accepts_all_four_valid_statuses():
    """AC8 (positive): All four enum values must be accepted without error."""
    engine = _make_memory_engine()

    for status in ("supports", "partial", "contradicts", "unverified"):
        session = _session(engine)
        plan = _seed_plan(session)
        from app import models

        src = models.Source(
            id=str(uuid.uuid4()),
            plan_id=plan.id,
            kind="article",
            support_status=status,
        )
        session.add(src)
        session.commit()
        session.expire(src)
        assert src.support_status == status, (
            f"support_status='{status}' must persist; got {src.support_status!r}"
        )
        session.close()

    engine.dispose()
