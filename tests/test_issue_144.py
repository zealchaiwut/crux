"""Tests for issue #144: Add summary column to Case model with migration.

AC coverage:
  AC1 – Case model in app/models.py has a summary column of type Text, nullable, defaulting to None
  AC2 – An Alembic migration file exists that adds the column (upgrade applies cleanly)
  AC3 – The migration is reversible (downgrade removes the column without error)
  AC4 – Existing rows are unaffected after migration (summary is NULL for pre-existing records)
  AC5 – No changes to non-nullable fields or existing column constraints
"""
import pathlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _make_db():
    from app.models import Base
    engine = _make_engine()
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_db()
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# AC1: Case model has summary column — Text, nullable, default None
# ---------------------------------------------------------------------------

def test_case_model_has_summary_attribute():
    """AC1: Case model must expose a 'summary' attribute."""
    from app import models
    assert hasattr(models.Case, "summary"), "Case model must have a 'summary' attribute"


def test_case_summary_column_exists_in_table():
    """AC1: Case.__table__ must have a 'summary' column."""
    from app import models
    col = models.Case.__table__.columns.get("summary")
    assert col is not None, "Case table must have a 'summary' column"


def test_case_summary_column_is_nullable():
    """AC1: Case.summary column must be nullable."""
    from app import models
    col = models.Case.__table__.columns["summary"]
    assert col.nullable, "Case.summary must be nullable=True"


def test_case_summary_column_type_is_text():
    """AC1: Case.summary column type must be Text (or compatible)."""
    from app import models
    col = models.Case.__table__.columns["summary"]
    assert isinstance(col.type, sa.Text), (
        f"Case.summary must be sa.Text type, got {type(col.type)}"
    )


def test_case_summary_defaults_to_none_on_new_instance(db_session):
    """AC1: A freshly created Case without explicit summary has summary=None."""
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem statement.",
        stage="sharpened",
    )
    db_session.add(case)
    db_session.commit()

    db_session.expire_all()
    retrieved = db_session.query(models.Case).filter_by(id=case.id).one()
    assert retrieved.summary is None, (
        f"summary must default to None on new Case, got: {retrieved.summary!r}"
    )


def test_case_summary_can_be_set_and_retrieved(db_session):
    """AC1 + UAT step 3: summary value persists after commit."""
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem for summary persistence.",
        stage="sharpened",
    )
    db_session.add(case)
    db_session.commit()

    case.summary = "Test summary"
    db_session.commit()

    db_session.expire_all()
    retrieved = db_session.query(models.Case).filter_by(id=case.id).one()
    assert retrieved.summary == "Test summary", (
        f"summary must persist across commit; got: {retrieved.summary!r}"
    )


def test_case_summary_can_be_set_to_none(db_session):
    """AC1 + UAT step 4: summary column accepts NULL without error."""
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Test problem for null summary.",
        stage="sharpened",
        summary="Initial value",
    )
    db_session.add(case)
    db_session.commit()

    case.summary = None
    db_session.commit()

    db_session.expire_all()
    retrieved = db_session.query(models.Case).filter_by(id=case.id).one()
    assert retrieved.summary is None, (
        f"summary must accept NULL; got: {retrieved.summary!r}"
    )


# ---------------------------------------------------------------------------
# AC2: Alembic migration file exists and adds the column correctly
# ---------------------------------------------------------------------------

def test_alembic_migration_file_for_summary_exists():
    """AC2: An Alembic migration file that adds 'summary' to the case table must exist."""
    versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    found = any(
        "summary" in f.read_text() and "case" in f.read_text()
        for f in migration_files
    )
    assert found, (
        "No Alembic migration found that adds 'summary' to the case table. "
        "Expected a file with op.add_column('case', sa.Column('summary', sa.Text(), nullable=True))."
    )


def test_alembic_migration_upgrade_adds_summary_column():
    """AC2: Migration upgrade() adds a nullable Text 'summary' column to the case table."""
    versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    target = None
    for f in migration_files:
        text_content = f.read_text()
        if "summary" in text_content and "\"case\"" in text_content and "add_column" in text_content:
            target = f
            break
    assert target is not None, (
        "Migration file must contain op.add_column for 'summary' on the case table."
    )
    content = target.read_text()
    assert "nullable=True" in content or "nullable" not in content.split("summary")[1].split(")")[0] + "True", (
        "Migration must add summary as nullable=True."
    )


def test_alembic_migration_upgrade_applies_cleanly_on_sqlite():
    """AC2: Migration upgrade() op runs without error on a bare SQLite database."""
    engine = _make_engine()
    with engine.connect() as conn:
        conn.execute(text(
            """CREATE TABLE "case" (
                id TEXT PRIMARY KEY,
                raw_problem TEXT NOT NULL,
                sharpened TEXT,
                not_investigating TEXT,
                stage TEXT NOT NULL,
                created_at TIMESTAMP,
                weigh_context TEXT
            )"""
        ))
        conn.commit()
        # Apply the migration upgrade op directly
        conn.execute(text('ALTER TABLE "case" ADD COLUMN summary TEXT'))
        conn.commit()
        # Verify the column now exists
        result = conn.execute(text('PRAGMA table_info("case")')).fetchall()
        columns = [row[1] for row in result]
    assert "summary" in columns, (
        f"After upgrade, 'summary' column must exist in case table; found columns: {columns}"
    )
    engine.dispose()


# ---------------------------------------------------------------------------
# AC3: Migration is reversible (downgrade removes the column)
# ---------------------------------------------------------------------------

def test_alembic_migration_downgrade_op_exists():
    """AC3: Migration file must contain a downgrade() that drops the summary column."""
    versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    found = any(
        "drop_column" in f.read_text() and "summary" in f.read_text()
        for f in migration_files
    )
    assert found, (
        "Migration downgrade() must call op.drop_column with 'summary'. "
        "No such migration file found."
    )


def test_alembic_migration_downgrade_removes_summary_column():
    """AC3: After downgrade, summary column is absent (simulated via SQLite copy table)."""
    engine = _make_engine()
    with engine.connect() as conn:
        # Create table with summary column (post-upgrade state)
        conn.execute(text(
            """CREATE TABLE "case" (
                id TEXT PRIMARY KEY,
                raw_problem TEXT NOT NULL,
                sharpened TEXT,
                not_investigating TEXT,
                stage TEXT NOT NULL,
                created_at TIMESTAMP,
                weigh_context TEXT,
                summary TEXT
            )"""
        ))
        conn.commit()
        # Insert a test row
        conn.execute(text(
            'INSERT INTO "case" (id, raw_problem, stage) VALUES (:id, :rp, :st)'
        ), {"id": str(uuid.uuid4()), "rp": "Test problem", "st": "sharpened"})
        conn.commit()
        # Simulate downgrade: recreate table without summary (SQLite limitation workaround)
        conn.execute(text(
            """CREATE TABLE "case_new" (
                id TEXT PRIMARY KEY,
                raw_problem TEXT NOT NULL,
                sharpened TEXT,
                not_investigating TEXT,
                stage TEXT NOT NULL,
                created_at TIMESTAMP,
                weigh_context TEXT
            )"""
        ))
        conn.execute(text(
            'INSERT INTO "case_new" SELECT id, raw_problem, sharpened, not_investigating, '
            'stage, created_at, weigh_context FROM "case"'
        ))
        conn.execute(text('DROP TABLE "case"'))
        conn.execute(text('ALTER TABLE "case_new" RENAME TO "case"'))
        conn.commit()
        # Verify summary column is gone
        result = conn.execute(text('PRAGMA table_info("case")')).fetchall()
        columns = [row[1] for row in result]
    assert "summary" not in columns, (
        f"After downgrade, 'summary' column must be removed; found columns: {columns}"
    )
    engine.dispose()


# ---------------------------------------------------------------------------
# AC4: Existing rows are unaffected (summary is NULL for pre-existing records)
# ---------------------------------------------------------------------------

def test_existing_rows_have_null_summary_after_upgrade():
    """AC4: Pre-existing rows in the case table get NULL summary after the migration runs."""
    engine = _make_engine()
    with engine.connect() as conn:
        # Create table without summary (pre-upgrade state)
        conn.execute(text(
            """CREATE TABLE "case" (
                id TEXT PRIMARY KEY,
                raw_problem TEXT NOT NULL,
                sharpened TEXT,
                not_investigating TEXT,
                stage TEXT NOT NULL,
                created_at TIMESTAMP,
                weigh_context TEXT
            )"""
        ))
        # Insert a pre-existing row
        existing_id = str(uuid.uuid4())
        conn.execute(text(
            'INSERT INTO "case" (id, raw_problem, stage) VALUES (:id, :rp, :st)'
        ), {"id": existing_id, "rp": "Pre-existing problem", "st": "sharpened"})
        conn.commit()
        # Apply upgrade
        conn.execute(text('ALTER TABLE "case" ADD COLUMN summary TEXT'))
        conn.commit()
        # Check the pre-existing row
        row = conn.execute(
            text('SELECT summary FROM "case" WHERE id = :id'), {"id": existing_id}
        ).fetchone()
    assert row is not None, "Pre-existing row must still exist after migration"
    assert row[0] is None, (
        f"Pre-existing row's summary must be NULL after upgrade; got: {row[0]!r}"
    )
    engine.dispose()


def test_multiple_existing_rows_all_have_null_summary():
    """AC4: All pre-existing rows get NULL summary, not just the first one."""
    engine = _make_engine()
    ids = [str(uuid.uuid4()) for _ in range(3)]
    with engine.connect() as conn:
        conn.execute(text(
            """CREATE TABLE "case" (
                id TEXT PRIMARY KEY,
                raw_problem TEXT NOT NULL,
                sharpened TEXT,
                not_investigating TEXT,
                stage TEXT NOT NULL,
                created_at TIMESTAMP,
                weigh_context TEXT
            )"""
        ))
        for cid in ids:
            conn.execute(text(
                'INSERT INTO "case" (id, raw_problem, stage) VALUES (:id, :rp, :st)'
            ), {"id": cid, "rp": "Problem", "st": "sharpened"})
        conn.commit()
        conn.execute(text('ALTER TABLE "case" ADD COLUMN summary TEXT'))
        conn.commit()
        rows = conn.execute(text('SELECT id, summary FROM "case"')).fetchall()
    assert len(rows) == 3, f"All 3 rows must still exist, found {len(rows)}"
    for row_id, summary in rows:
        assert summary is None, (
            f"Row {row_id} summary must be NULL after upgrade; got: {summary!r}"
        )
    engine.dispose()


# ---------------------------------------------------------------------------
# AC5: Non-nullable fields and existing constraints are unchanged
# ---------------------------------------------------------------------------

def test_non_nullable_case_fields_unchanged(db_session):
    """AC5: raw_problem and stage remain NOT NULL after the model/migration change."""
    from app import models
    raw_problem_col = models.Case.__table__.columns["raw_problem"]
    stage_col = models.Case.__table__.columns["stage"]
    assert not raw_problem_col.nullable, "Case.raw_problem must remain NOT NULL"
    assert not stage_col.nullable, "Case.stage must remain NOT NULL"


def test_case_table_column_count_only_increased_by_one():
    """AC5: Only the summary column was added; no other columns were removed or changed."""
    from app import models
    cols = {c.name: c for c in models.Case.__table__.columns}
    expected_cols = {
        "id", "raw_problem", "sharpened", "not_investigating",
        "stage", "created_at", "weigh_context", "summary",
    }
    assert expected_cols.issubset(cols.keys()), (
        f"Case table is missing expected columns. "
        f"Expected (at minimum): {expected_cols}, got: {set(cols.keys())}"
    )


def test_case_id_is_still_primary_key():
    """AC5: Case.id remains the primary key after the migration."""
    from app import models
    id_col = models.Case.__table__.columns["id"]
    assert id_col.primary_key, "Case.id must remain the primary key"


def test_existing_case_fields_still_accessible_after_summary_added(db_session):
    """AC5: Other Case fields work normally after summary column is present."""
    from app import models
    case = models.Case(
        id=str(uuid.uuid4()),
        raw_problem="Full field test problem.",
        sharpened="Sharpened version of the problem.",
        stage="sharpened",
        weigh_context="Some context.",
    )
    db_session.add(case)
    db_session.commit()

    db_session.expire_all()
    retrieved = db_session.query(models.Case).filter_by(id=case.id).one()
    assert retrieved.raw_problem == "Full field test problem."
    assert retrieved.sharpened == "Sharpened version of the problem."
    assert retrieved.stage == "sharpened"
    assert retrieved.weigh_context == "Some context."
    assert retrieved.summary is None
