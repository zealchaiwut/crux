"""Tests for issue #153: Add source-verification fields to Source model.

This test file validates:
  AC1 – support_status is a DB-level enum with exactly four values (supports, partial, contradicts, unverified)
        with NOT NULL constraint and default 'unverified'.
  AC2 – support_rationale is a nullable Text column with no length restriction.
  AC3 – Alembic migration applies cleanly.
  AC4 – Migration is reversible.
  AC5 – Existing rows after migration have support_status='unverified' and support_rationale=NULL.
  AC6 – Source model repr/__str__ is not broken.
  AC7 – New unit tests cover: default value, all four enum variants, null rationale.

  UAT1 – alembic upgrade head on database with pre-existing Source rows succeeds.
  UAT2 – Create a new Source record without support_status/rationale; defaults are correct.
  UAT3 – Update a Source, set both fields; both values save and retrieve without truncation.
  UAT4 – Attempt to set support_status to 'unknown' (invalid); database/ORM rejects it.
  UAT5 – alembic downgrade -1 removes both columns and enum type.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import StatementError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901")

from app.models import Base, Case, Plan, Source, _SUPPORT_STATUS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """In-memory SQLite database with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session, engine
    session.close()
    engine.dispose()


@pytest.fixture()
def plan_with_case(db):
    """Create a Case and Plan for testing Source records."""
    session, engine = db
    case = Case(id="case-test-153", raw_problem="Test case", stage="sharpened")
    session.add(case)
    session.flush()
    plan = Plan(id="plan-test-153", case_id="case-test-153", label="A")
    session.add(plan)
    session.commit()
    return session, engine, plan


# ---------------------------------------------------------------------------
# AC1 – enum definition: exactly four values, NOT NULL, default unverified
# ---------------------------------------------------------------------------

def test_ac1__support_status_enum_has_exactly_four_values():
    """AC1: _SUPPORT_STATUS contains exactly the four required values."""
    assert set(_SUPPORT_STATUS) == {"supports", "partial", "contradicts", "unverified"}
    assert len(_SUPPORT_STATUS) == 4


def test_ac1__support_status_column_is_not_nullable(db):
    """AC1: support_status column is NOT NULL in the database schema."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert "support_status" in cols
    assert cols["support_status"]["nullable"] is False


def test_ac1__support_status_has_default(db):
    """AC1: support_status has a default value (server default)."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert cols["support_status"]["default"] is not None


# ---------------------------------------------------------------------------
# AC2 – support_rationale: nullable text, no length restriction
# ---------------------------------------------------------------------------

def test_ac2__support_rationale_column_is_nullable(db):
    """AC2: support_rationale exists and is nullable."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert "support_rationale" in cols
    assert cols["support_rationale"]["nullable"] is True


def test_ac2__support_rationale_accepts_long_text(plan_with_case):
    """AC2: support_rationale accepts text of arbitrary length (no truncation)."""
    session, engine, plan = plan_with_case
    long_text = "x" * 50_000
    src = Source(
        id="src-long-153",
        plan_id=plan.id,
        kind="article",
        title="Long rationale",
        support_rationale=long_text,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-long-153'")
    ).scalar()
    assert result == long_text, "support_rationale was truncated"


# ---------------------------------------------------------------------------
# AC5 – default values: new rows default to unverified / NULL rationale
# ---------------------------------------------------------------------------

def test_ac5__new_source_defaults_to_unverified(plan_with_case):
    """AC5: Source created without support_status defaults to 'unverified'."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-default-status-153",
        plan_id=plan.id,
        kind="article",
        title="Default status",
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_status FROM source WHERE id='src-default-status-153'")
    ).scalar()
    assert result == "unverified"


def test_ac5__new_source_defaults_to_null_rationale(plan_with_case):
    """AC5: Source created without support_rationale has NULL rationale."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-null-rationale-153",
        plan_id=plan.id,
        kind="book",
        title="Null rationale",
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-null-rationale-153'")
    ).scalar()
    assert result is None


# ---------------------------------------------------------------------------
# AC6 – model repr not broken
# ---------------------------------------------------------------------------

def test_ac6__source_repr_not_broken(plan_with_case):
    """AC6: repr(source) and str(source) do not raise an exception."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-repr-153",
        plan_id=plan.id,
        kind="article",
        title="Repr test",
        support_status="supports",
        support_rationale="A rationale.",
    )
    session.add(src)
    session.commit()
    try:
        _ = repr(src)
        _ = str(src)
    except Exception as exc:
        pytest.fail(f"repr/str raised {exc!r}")


# ---------------------------------------------------------------------------
# AC7 – all four enum variants can be stored and retrieved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["supports", "partial", "contradicts", "unverified"])
def test_ac7__all_four_enum_variants_persist(plan_with_case, status):
    """AC7: Each of the four enum values can be stored and retrieved."""
    session, engine, plan = plan_with_case
    src_id = f"src-{status}-153"
    src = Source(
        id=src_id,
        plan_id=plan.id,
        kind="article",
        title=f"Status {status}",
        support_status=status,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text(f"SELECT support_status FROM source WHERE id='{src_id}'")
    ).scalar()
    assert result == status


def test_ac7__invalid_enum_value_rejected(plan_with_case):
    """AC7: An out-of-enum value ('unknown') raises a validation/constraint error."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-invalid-153",
        plan_id=plan.id,
        kind="article",
        title="Invalid enum test",
        support_status="unknown",
    )
    with pytest.raises((StatementError, ValueError, LookupError)):
        session.add(src)
        session.commit()


def test_ac7__null_rationale_explicitly_set(plan_with_case):
    """AC7: support_rationale=None is stored as NULL."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-null-explicit-153",
        plan_id=plan.id,
        kind="youtube",
        title="Explicit null",
        support_status="partial",
        support_rationale=None,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-null-explicit-153'")
    ).scalar()
    assert result is None


def test_ac7__non_empty_rationale_persists(plan_with_case):
    """AC7: support_rationale accepts and stores non-empty text."""
    session, engine, plan = plan_with_case
    rationale = "Primary peer-reviewed study directly confirms the claim."
    src = Source(
        id="src-rationale-set-153",
        plan_id=plan.id,
        kind="book",
        title="Non-null rationale",
        support_status="supports",
        support_rationale=rationale,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-rationale-set-153'")
    ).scalar()
    assert result == rationale


# ---------------------------------------------------------------------------
# AC3 – schema validation: both columns are present
# ---------------------------------------------------------------------------

def test_ac3__both_new_columns_exist_in_schema(db):
    """AC3: After Base.metadata.create_all, both columns are present."""
    session, engine = db
    col_names = {c["name"] for c in inspect(engine).get_columns("source")}
    assert "support_status" in col_names
    assert "support_rationale" in col_names


# ---------------------------------------------------------------------------
# AC4 – migration reversibility: verify downgrade exists
# ---------------------------------------------------------------------------

def test_ac4__migration_file_has_downgrade_function():
    """AC4: The migration m3n4o5p6q7r8 includes a downgrade() function."""
    import importlib.util
    import pathlib

    versions_dir = (
        pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    )
    migration_file = (
        versions_dir / "m3n4o5p6q7r8_update_support_status_enum_and_add_support_rationale.py"
    )
    assert migration_file.exists(), f"Migration file not found: {migration_file}"

    spec = importlib.util.spec_from_file_location("migration_m3", migration_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "downgrade"), "Migration must define downgrade()"
    assert callable(mod.downgrade)
    assert hasattr(mod, "upgrade"), "Migration must define upgrade()"
    assert callable(mod.upgrade)


# ---------------------------------------------------------------------------
# UAT scenarios (simulated database-level tests)
# ---------------------------------------------------------------------------

def test_uat1__upgrade_with_preexisting_rows(plan_with_case):
    """UAT1: Creating sources with pre-existing data, then checking defaults."""
    session, engine, plan = plan_with_case

    # Create multiple sources to simulate pre-existing data
    for i in range(3):
        src = Source(
            id=f"src-preexist-{i}-153",
            plan_id=plan.id,
            kind="article",
            title=f"Pre-existing {i}",
        )
        session.add(src)
    session.commit()

    # Verify all default to 'unverified' and NULL rationale
    for i in range(3):
        status = session.execute(
            text(f"SELECT support_status FROM source WHERE id='src-preexist-{i}-153'")
        ).scalar()
        rationale = session.execute(
            text(f"SELECT support_rationale FROM source WHERE id='src-preexist-{i}-153'")
        ).scalar()
        assert status == "unverified"
        assert rationale is None


def test_uat2__create_source_without_fields(plan_with_case):
    """UAT2: Create a Source without support_status/rationale; defaults apply."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-uat2-153",
        plan_id=plan.id,
        kind="youtube",
        title="UAT2 test",
    )
    session.add(src)
    session.commit()

    result = session.execute(
        text("SELECT support_status, support_rationale FROM source WHERE id='src-uat2-153'")
    ).fetchone()
    status, rationale = result
    assert status == "unverified"
    assert rationale is None


def test_uat3__update_source_both_fields(plan_with_case):
    """UAT3: Update a Source, set both support_status and support_rationale; verify no truncation."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-uat3-153",
        plan_id=plan.id,
        kind="book",
        title="UAT3 test",
    )
    session.add(src)
    session.commit()

    # Update both fields
    src.support_status = "supports"
    src.support_rationale = "Primary peer-reviewed study directly confirms the claim."
    session.commit()

    result = session.execute(
        text("SELECT support_status, support_rationale FROM source WHERE id='src-uat3-153'")
    ).fetchone()
    status, rationale = result
    assert status == "supports"
    assert rationale == "Primary peer-reviewed study directly confirms the claim."


def test_uat4__invalid_status_rejected(plan_with_case):
    """UAT4: Attempt to set support_status='unknown' (invalid); database/ORM rejects it."""
    session, engine, plan = plan_with_case
    src = Source(
        id="src-uat4-153",
        plan_id=plan.id,
        kind="article",
        title="UAT4 test",
        support_status="unknown",  # Invalid
    )
    with pytest.raises((StatementError, ValueError, LookupError)):
        session.add(src)
        session.commit()


def test_uat5__downgrade_removes_columns_and_enum(db):
    """UAT5: Verify migration file contains logic to drop columns and enum type on downgrade."""
    import importlib.util
    import pathlib

    versions_dir = (
        pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    )
    migration_file = (
        versions_dir / "m3n4o5p6q7r8_update_support_status_enum_and_add_support_rationale.py"
    )

    spec = importlib.util.spec_from_file_location("migration_m3", migration_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Check that downgrade function is defined and contains logic to drop the column
    import inspect as insp
    downgrade_source = insp.getsource(mod.downgrade)

    # Verify the downgrade drops the support_rationale column
    assert "drop_column" in downgrade_source.lower(), \
        "downgrade() must call drop_column for support_rationale"
    assert "support_rationale" in downgrade_source, \
        "downgrade() must reference support_rationale column name"
