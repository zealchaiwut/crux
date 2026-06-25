"""Tests for issue #97: Add support_status and support_rationale to Source"""
import os
import sys
import tempfile

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import ArgumentError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import Base, Case, Plan, Source


@pytest.fixture
def temp_db():
    """Create an in-memory SQLite database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session, engine

    session.close()
    engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def setup_case_plan(temp_db):
    """Create a case and plan for testing sources."""
    session, engine = temp_db
    case = Case(
        id="case-1",
        raw_problem="Test case",
        stage="sharpened"
    )
    session.add(case)
    session.flush()

    plan = Plan(
        id="plan-1",
        case_id="case-1",
        label="A"
    )
    session.add(plan)
    session.commit()

    return session, engine, case, plan


# --- Acceptance Criteria Tests ---

def test_source_model_has_support_status_column(temp_db):
    """AC: Source model has support_status column with correct enum values and defaults"""
    session, engine = temp_db

    # Verify the column exists and has the correct enum values
    inspector_obj = inspect(engine)
    columns = {c['name']: c for c in inspector_obj.get_columns('source')}

    assert 'support_status' in columns
    col = columns['support_status']

    # Verify it's non-nullable with a server default
    assert col['nullable'] is False
    assert col['default'] is not None


def test_source_model_has_support_rationale_column(temp_db):
    """AC: Source model has support_rationale column (Text, nullable)"""
    session, engine = temp_db

    inspector_obj = inspect(engine)
    columns = {c['name']: c for c in inspector_obj.get_columns('source')}

    assert 'support_rationale' in columns
    col = columns['support_rationale']
    assert col['nullable'] is True


def test_source_enum_values_are_correct(temp_db):
    """AC: support_status enum has values: supports, partial, contradicts, unverified"""
    session, engine = temp_db

    # Check the enum constraint in the model
    from app.models import _SUPPORT_STATUS
    assert set(_SUPPORT_STATUS) == {'supports', 'partial', 'contradicts', 'unverified'}


def test_source_support_status_defaults_to_unverified(setup_case_plan):
    """AC: Source instance defaults support_status to 'unverified' when not specified"""
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-1",
        plan_id="plan-1",
        kind="article",
        title="Test Article"
    )
    session.add(source)
    session.commit()

    # Verify the default was applied
    result = session.execute(
        text("SELECT support_status FROM source WHERE id = 'source-1'")
    ).scalar()
    assert result == 'unverified'


def test_source_support_status_can_be_set_to_supports(setup_case_plan):
    """AC: Source can be created with support_status = 'supports'"""
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-2",
        plan_id="plan-1",
        kind="book",
        title="Test Book",
        support_status="supports"
    )
    session.add(source)
    session.commit()

    result = session.execute(
        text("SELECT support_status FROM source WHERE id = 'source-2'")
    ).scalar()
    assert result == 'supports'


def test_source_support_status_can_be_set_to_partial(setup_case_plan):
    """AC: Source can be created with support_status = 'partial'"""
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-3",
        plan_id="plan-1",
        kind="article",
        title="Test Article",
        support_status="partial"
    )
    session.add(source)
    session.commit()

    result = session.execute(
        text("SELECT support_status FROM source WHERE id = 'source-3'")
    ).scalar()
    assert result == 'partial'


def test_source_support_status_can_be_set_to_contradicts(setup_case_plan):
    """AC: Source can be created with support_status = 'contradicts'"""
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-4",
        plan_id="plan-1",
        kind="youtube",
        title="Test Video",
        support_status="contradicts"
    )
    session.add(source)
    session.commit()

    result = session.execute(
        text("SELECT support_status FROM source WHERE id = 'source-4'")
    ).scalar()
    assert result == 'contradicts'


def test_source_support_rationale_can_be_set(setup_case_plan):
    """AC: Source can be created with non-empty support_rationale"""
    session, engine, case, plan = setup_case_plan

    rationale_text = "This source directly supports the claim because it contains empirical evidence"
    source = Source(
        id="source-5",
        plan_id="plan-1",
        kind="article",
        title="Test Article",
        support_status="supports",
        support_rationale=rationale_text
    )
    session.add(source)
    session.commit()

    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id = 'source-5'")
    ).scalar()
    assert result == rationale_text


def test_source_rejects_invalid_support_status(setup_case_plan):
    """AC: Source rejects invalid support_status values (not in enum)"""
    from sqlalchemy.exc import StatementError
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-6",
        plan_id="plan-1",
        kind="article",
        title="Test Article",
        support_status="maybe"  # Invalid value
    )

    with pytest.raises((ArgumentError, ValueError, LookupError, StatementError)):
        session.add(source)
        session.commit()


def test_source_support_rationale_nullable(setup_case_plan):
    """AC: source_rationale can be NULL when not specified"""
    session, engine, case, plan = setup_case_plan

    source = Source(
        id="source-7",
        plan_id="plan-1",
        kind="article",
        title="Test Article",
        support_status="unverified"
        # support_rationale not specified
    )
    session.add(source)
    session.commit()

    result = session.execute(
        text("SELECT support_rationale FROM source WHERE id = 'source-7'")
    ).scalar()
    assert result is None


def test_migration_support_status_not_null_constraint(temp_db):
    """AC: support_status column has NOT NULL constraint"""
    session, engine = temp_db

    inspector_obj = inspect(engine)
    columns = {c['name']: c for c in inspector_obj.get_columns('source')}

    assert columns['support_status']['nullable'] is False
