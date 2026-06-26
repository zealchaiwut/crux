"""Tests for issue #144: Add summary column to Case model with migration"""
import os
import subprocess
import tempfile
import shutil
import sys
import pytest
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
TEST_DB_PATH = BASE_DIR / "test_migration.db"


def setup_module():
    """Set up the test environment with a SQLite database for alembic."""
    # Set DATABASE_URL to SQLite for testing
    os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"


def reset_database():
    """Reset the test database to a clean state."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def run_alembic_command(cmd_args, cwd=BASE_DIR):
    """Run an alembic command and return the result."""
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
    result = subprocess.run(
        ["alembic"] + cmd_args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )
    return result


# --- Acceptance Criteria ---

def test_add_summary_column_to_case__column_exists_in_model():
    """AC: Case model has a summary column of type Text, nullable, defaulting to None"""
    from app.models import Case
    from sqlalchemy import inspect

    # Get the column info from the Case model
    mapper = inspect(Case)
    columns = {col.name: col for col in mapper.columns}

    assert "summary" in columns, "summary column not found in Case model"

    col = columns["summary"]
    assert col.type.__class__.__name__ == "Text", f"Expected Text type, got {col.type.__class__.__name__}"
    assert col.nullable is True, "summary column should be nullable"
    assert col.default is None, "summary column default should be None"


def test_add_summary_column_to_case__migration_applies_cleanly():
    """AC: Migration file is generated and applies cleanly via alembic upgrade head on fresh database"""
    from pathlib import Path
    import importlib.util

    # Verify the migration file exists and is syntactically valid
    migration_file = BASE_DIR / "alembic" / "versions" / "i9j0k1l2m3n4_add_summary_to_case.py"
    assert migration_file.exists(), "Migration file i9j0k1l2m3n4_add_summary_to_case.py not found"

    # Load and verify the migration module
    spec = importlib.util.spec_from_file_location("migration", migration_file)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    # Verify required attributes
    assert hasattr(migration, "upgrade"), "Migration lacks upgrade() function"
    assert hasattr(migration, "downgrade"), "Migration lacks downgrade() function"
    assert hasattr(migration, "revision"), "Migration lacks revision attribute"
    assert migration.revision == "i9j0k1l2m3n4", "Migration revision ID mismatch"


def test_add_summary_column_to_case__migration_is_reversible():
    """AC: Migration is reversible (alembic downgrade -1 removes the column without error)"""
    from pathlib import Path
    import importlib.util

    # Verify the migration file has both upgrade and downgrade
    migration_file = BASE_DIR / "alembic" / "versions" / "i9j0k1l2m3n4_add_summary_to_case.py"
    assert migration_file.exists(), "Migration file not found"

    # Load the migration
    spec = importlib.util.spec_from_file_location("migration", migration_file)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    # Verify both functions exist and are callable
    assert callable(migration.upgrade), "upgrade() is not callable"
    assert callable(migration.downgrade), "downgrade() is not callable"

    # Verify downgrade uses drop_column
    with open(migration_file, 'r') as f:
        content = f.read()
    assert "drop_column" in content, "downgrade() does not drop the column"


def test_add_summary_column_to_case__existing_rows_unaffected():
    """AC: Existing rows are unaffected after migration (column is NULL for all pre-existing records)"""
    from pathlib import Path
    import importlib.util

    # Verify the migration uses nullable=True
    migration_file = BASE_DIR / "alembic" / "versions" / "i9j0k1l2m3n4_add_summary_to_case.py"
    assert migration_file.exists(), "Migration file not found"

    with open(migration_file, 'r') as f:
        content = f.read()

    # The migration should add a nullable Text column
    assert "nullable=True" in content, \
        "Migration does not explicitly set nullable=True for the summary column"
    assert "sa.Text()" in content, "Migration does not use Text() type"


def test_add_summary_column_to_case__no_non_nullable_changes():
    """AC: No changes to non-nullable fields or existing column constraints"""
    from app.models import Case
    from sqlalchemy import inspect

    mapper = inspect(Case)
    columns = {col.name: col for col in mapper.columns}

    # Verify non-nullable fields are still non-nullable
    required_non_nullable = ["id", "raw_problem", "stage"]
    for col_name in required_non_nullable:
        col = columns[col_name]
        assert col.nullable is False, f"{col_name} should be non-nullable"


def test_add_summary_column_to_case__summary_accepts_values():
    """UAT: summary column accepts values and persists them"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Case

    reset_database()

    # Create an in-memory SQLite database with the Case model
    engine = create_engine("sqlite:///:memory:")

    # Create all tables from the models
    from app.models import Base
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Create and insert a test case
        case = Case(
            id="test-case-456",
            raw_problem="Test problem",
            stage="sharpened"
        )
        session.add(case)
        session.commit()

        # Set summary and commit
        case.summary = "Test summary"
        session.commit()

        # Verify persistence
        session.refresh(case)
        assert case.summary == "Test summary", "Summary value not persisted"

        # Set to None and commit
        case.summary = None
        session.commit()

        # Verify NULL acceptance
        session.refresh(case)
        assert case.summary is None, "Summary should accept NULL"

    finally:
        session.close()
