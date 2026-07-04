"""Tests for issue #153: Add source-verification fields to Source model.

AC coverage:
  AC1 – support_status is a DB-level enum with exactly four values:
         supports, partial, contradicts, unverified; default unverified; NOT NULL.
  AC2 – support_rationale is a nullable Text column with no length restriction.
  AC3 – Alembic migration applies cleanly (verified via ORM schema).
  AC4 – Migration is reversible (downgrade path exists in migration file).
  AC5 – New rows default to support_status='unverified', support_rationale=NULL.
  AC6 – Source model repr / str is not broken by the new fields.
  AC7 – New unit tests cover: default value, all four enum variants, null rationale.
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
def plan(db):
    session, engine = db
    case = Case(id="case-153", raw_problem="Test", stage="sharpened")
    session.add(case)
    session.flush()
    p = Plan(id="plan-153", case_id="case-153", label="A")
    session.add(p)
    session.commit()
    return session, engine, p


# ---------------------------------------------------------------------------
# AC1 – enum definition: exactly four values, NOT NULL, default unverified
# ---------------------------------------------------------------------------

def test_support_status_enum_has_exactly_four_values():
    """AC1: _SUPPORT_STATUS contains exactly the four required values."""
    assert set(_SUPPORT_STATUS) == {"supports", "partial", "contradicts", "unverified"}
    assert len(_SUPPORT_STATUS) == 4


def test_support_status_column_is_not_nullable(db):
    """AC1: support_status column is NOT NULL in the database schema."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert "support_status" in cols
    assert cols["support_status"]["nullable"] is False


def test_support_status_column_has_server_default(db):
    """AC1: support_status column has a default value defined."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert cols["support_status"]["default"] is not None


# ---------------------------------------------------------------------------
# AC2 – support_rationale: nullable text, no length restriction
# ---------------------------------------------------------------------------

def test_support_rationale_column_exists_and_is_nullable(db):
    """AC2: support_rationale column exists and is nullable."""
    session, engine = db
    cols = {c["name"]: c for c in inspect(engine).get_columns("source")}
    assert "support_rationale" in cols
    assert cols["support_rationale"]["nullable"] is True


def test_support_rationale_accepts_long_text(plan):
    """AC2: support_rationale accepts text of arbitrary length."""
    session, engine, p = plan
    long_text = "x" * 10_000
    src = Source(
        id="src-rationale-long",
        plan_id=p.id,
        kind="article",
        title="Long rationale test",
        support_rationale=long_text,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-rationale-long'")
    ).scalar()
    assert result == long_text


# ---------------------------------------------------------------------------
# AC5 / AC7 – default value: new rows default to unverified / NULL rationale
# ---------------------------------------------------------------------------

def test_new_source_defaults_to_unverified(plan):
    """AC5/AC7: Source created without support_status defaults to 'unverified'."""
    session, engine, p = plan
    src = Source(
        id="src-default",
        plan_id=p.id,
        kind="article",
        title="Default status test",
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_status FROM source WHERE id='src-default'")
    ).scalar()
    assert result == "unverified"


def test_new_source_defaults_to_null_rationale(plan):
    """AC5/AC7: Source created without support_rationale has NULL rationale."""
    session, engine, p = plan
    src = Source(
        id="src-null-rationale",
        plan_id=p.id,
        kind="book",
        title="Null rationale test",
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-null-rationale'")
    ).scalar()
    assert result is None


# ---------------------------------------------------------------------------
# AC7 – all four enum variants can be stored and retrieved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["supports", "partial", "contradicts", "unverified"])
def test_all_four_enum_variants_persist(plan, status):
    """AC7: Each of the four enum values can be stored and retrieved."""
    session, engine, p = plan
    src_id = f"src-{status}"
    src = Source(
        id=src_id,
        plan_id=p.id,
        kind="article",
        title=f"Status {status}",
        support_status=status,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_status FROM source WHERE id=:id").bindparams(id=src_id)
    ).scalar()
    assert result == status


def test_invalid_enum_value_is_rejected(plan):
    """AC1/AC7: An out-of-enum value raises a validation error."""
    session, engine, p = plan
    src = Source(
        id="src-invalid",
        plan_id=p.id,
        kind="article",
        title="Invalid enum test",
        support_status="unknown",
    )
    with pytest.raises((StatementError, ValueError, LookupError)):
        session.add(src)
        session.commit()


# ---------------------------------------------------------------------------
# AC7 – null rationale explicitly set
# ---------------------------------------------------------------------------

def test_support_rationale_can_be_explicitly_null(plan):
    """AC7: support_rationale=None is stored as NULL."""
    session, engine, p = plan
    src = Source(
        id="src-explicit-null",
        plan_id=p.id,
        kind="youtube",
        title="Explicit null rationale",
        support_status="partial",
        support_rationale=None,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-explicit-null'")
    ).scalar()
    assert result is None


def test_support_rationale_can_be_non_empty_string(plan):
    """AC7: support_rationale accepts and stores non-empty text."""
    session, engine, p = plan
    rationale = "Primary peer-reviewed study directly confirms the claim."
    src = Source(
        id="src-rationale-set",
        plan_id=p.id,
        kind="book",
        title="Non-null rationale",
        support_status="supports",
        support_rationale=rationale,
    )
    session.add(src)
    session.commit()
    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id='src-rationale-set'")
    ).scalar()
    assert result == rationale


# ---------------------------------------------------------------------------
# AC6 – model repr not broken
# ---------------------------------------------------------------------------

def test_source_repr_is_not_broken(plan):
    """AC6: repr(source) and str(source) do not raise an exception."""
    session, engine, p = plan
    src = Source(
        id="src-repr",
        plan_id=p.id,
        kind="article",
        title="Repr test",
        support_status="contradicts",
        support_rationale="A reason.",
    )
    session.add(src)
    session.commit()
    try:
        _ = repr(src)
        _ = str(src)
    except Exception as exc:
        pytest.fail(f"repr/str raised {exc!r}")


# ---------------------------------------------------------------------------
# AC3 – schema validation: both columns are present after create_all
# ---------------------------------------------------------------------------

def test_both_new_columns_exist_in_schema(db):
    """AC3: After Base.metadata.create_all, both columns are present in source."""
    session, engine = db
    col_names = {c["name"] for c in inspect(engine).get_columns("source")}
    assert "support_status" in col_names, "support_status column must exist"
    assert "support_rationale" in col_names, "support_rationale column must exist"


# ---------------------------------------------------------------------------
# AC4 – migration reversibility: verify the migration file has a downgrade
# ---------------------------------------------------------------------------

def test_migration_file_has_downgrade_function():
    """AC4: The migration that adds support_rationale includes a downgrade()."""
    import importlib.util
    import pathlib

    versions_dir = (
        pathlib.Path(__file__).parent.parent / "alembic" / "versions"
    )
    migration_file = versions_dir / "m3n4o5p6q7r8_update_support_status_enum_and_add_support_rationale.py"
    assert migration_file.exists(), f"Migration file not found: {migration_file}"

    spec = importlib.util.spec_from_file_location("migration_m3", migration_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "downgrade"), "Migration must define a downgrade() function"
    assert callable(mod.downgrade)
    assert hasattr(mod, "upgrade"), "Migration must define an upgrade() function"
    assert callable(mod.upgrade)
