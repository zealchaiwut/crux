"""Tests for issue #2: Neon Postgres schema and Alembic migrations."""
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MIGRATION_DIR = REPO_ROOT / "alembic" / "versions"
HAS_DATABASE_URL = bool(os.environ.get("DATABASE_URL"))


def _get_migration_files():
    return sorted([m for m in MIGRATION_DIR.glob("*.py") if m.name != "__init__.py"])


def _get_migration_content():
    files = _get_migration_files()
    assert files, "No migration files found in alembic/versions/"
    return files[0].read_text()


# AC1: DATABASE_URL documented in .env.example
def test_env_example_exists():
    assert (REPO_ROOT / ".env.example").exists()


def test_env_example_has_database_url():
    content = (REPO_ROOT / ".env.example").read_text()
    assert "DATABASE_URL" in content


def test_env_example_has_neon_description():
    content = (REPO_ROOT / ".env.example").read_text()
    assert "neon" in content.lower() or "postgres" in content.lower()


# AC2: Alembic in dependencies and config committed
def test_alembic_in_requirements():
    content = (REPO_ROOT / "requirements.txt").read_text()
    assert re.search(r"alembic==", content, re.IGNORECASE)


def test_sqlalchemy_in_requirements():
    content = (REPO_ROOT / "requirements.txt").read_text()
    assert re.search(r"sqlalchemy==", content, re.IGNORECASE)


def test_alembic_ini_exists():
    assert (REPO_ROOT / "alembic.ini").exists()


def test_alembic_env_py_exists():
    assert (REPO_ROOT / "alembic" / "env.py").exists()


# AC3: Initial migration file generated and committed
def test_migration_versions_dir_exists():
    assert MIGRATION_DIR.exists()


def test_at_least_one_migration_exists():
    non_init = _get_migration_files()
    assert len(non_init) >= 1, "At least one migration file must exist"


# AC4–AC9: Migration creates all five tables with correct columns
def test_migration_creates_case_table():
    content = _get_migration_content()
    assert "create_table" in content
    assert "'case'" in content or '"case"' in content


def test_migration_creates_plan_table():
    content = _get_migration_content()
    assert "'plan'" in content or '"plan"' in content


def test_migration_creates_source_table():
    content = _get_migration_content()
    assert "'source'" in content or '"source"' in content


def test_migration_creates_probe_table():
    content = _get_migration_content()
    assert "'probe'" in content or '"probe"' in content


def test_migration_creates_verdict_table():
    content = _get_migration_content()
    assert "'verdict'" in content or '"verdict"' in content


# AC5: Case columns
def test_migration_case_has_raw_problem():
    assert "raw_problem" in _get_migration_content()


def test_migration_case_has_sharpened():
    assert "sharpened" in _get_migration_content()


def test_migration_case_has_not_investigating():
    assert "not_investigating" in _get_migration_content()


def test_migration_case_has_stage():
    assert "stage" in _get_migration_content()


def test_migration_case_has_created_at():
    assert "created_at" in _get_migration_content()


# AC6: Plan columns
def test_migration_plan_has_case_id():
    assert "case_id" in _get_migration_content()


def test_migration_plan_has_label():
    assert "label" in _get_migration_content()


def test_migration_plan_has_mechanism():
    assert "mechanism" in _get_migration_content()


def test_migration_plan_has_prior():
    assert "prior" in _get_migration_content()


def test_migration_plan_has_current_rank():
    assert "current_rank" in _get_migration_content()


# AC7: Source columns
def test_migration_source_has_plan_id():
    assert "plan_id" in _get_migration_content()


def test_migration_source_has_kind():
    assert "kind" in _get_migration_content()


def test_migration_source_has_title():
    assert "title" in _get_migration_content()


def test_migration_source_has_url():
    assert "url" in _get_migration_content()


def test_migration_source_has_claim():
    assert "claim" in _get_migration_content()


def test_migration_source_has_citation():
    assert "citation" in _get_migration_content()


# AC8: Probe columns
def test_migration_probe_has_case_id():
    assert "case_id" in _get_migration_content()


def test_migration_probe_has_type():
    assert "type" in _get_migration_content()


def test_migration_probe_has_target_metric():
    assert "target_metric" in _get_migration_content()


def test_migration_probe_has_status():
    assert "status" in _get_migration_content()


def test_migration_probe_has_due_date():
    assert "due_date" in _get_migration_content()


def test_migration_probe_has_commander_spec():
    assert "commander_spec" in _get_migration_content()


# AC9: Verdict columns
def test_migration_verdict_has_probe_id():
    assert "probe_id" in _get_migration_content()


def test_migration_verdict_has_outcome():
    assert "outcome" in _get_migration_content()


def test_migration_verdict_has_notes():
    assert "notes" in _get_migration_content()


def test_migration_verdict_has_decided_at():
    assert "decided_at" in _get_migration_content()


# AC10: ON DELETE behaviour explicitly set
def test_migration_has_on_delete_for_fks():
    content = _get_migration_content()
    assert "ondelete" in content.lower() or "ON DELETE" in content


# AC11: Enum types enforced at DB level
def test_migration_uses_enum_types():
    content = _get_migration_content()
    assert "Enum(" in content or "postgresql.ENUM" in content


def test_migration_plan_label_values():
    content = _get_migration_content()
    has_a = "'A'" in content or '"A"' in content
    has_b = "'B'" in content or '"B"' in content
    has_c = "'C'" in content or '"C"' in content
    assert has_a and has_b and has_c, "plan label enum must include values A, B, C"


def test_migration_source_kind_values():
    content = _get_migration_content()
    assert "book" in content and "article" in content and "youtube" in content


def test_migration_probe_type_values():
    content = _get_migration_content()
    assert "measurement" in content and "prototype" in content


def test_migration_probe_status_values():
    content = _get_migration_content()
    assert "designed" in content and "running" in content


def test_migration_verdict_outcome_values():
    content = _get_migration_content()
    assert "confirmed" in content and "killed" in content and "inconclusive" in content


# AC12: Downgrade reverses the migration
def test_migration_has_downgrade_function():
    assert "def downgrade" in _get_migration_content()


def test_migration_downgrade_drops_tables():
    assert "drop_table" in _get_migration_content()


# Integration tests — require a real DATABASE_URL
@pytest.mark.skipif(not HAS_DATABASE_URL, reason="DATABASE_URL not set — skipping live DB tests")
def test_alembic_upgrade_head():
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"


@pytest.mark.skipif(not HAS_DATABASE_URL, reason="DATABASE_URL not set — skipping live DB tests")
def test_all_five_tables_created():
    import sqlalchemy as sa
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    engine.dispose()
    for table in ["case", "plan", "source", "probe", "verdict"]:
        assert table in tables, f"Table '{table}' not found after upgrade head"


@pytest.mark.skipif(not HAS_DATABASE_URL, reason="DATABASE_URL not set — skipping live DB tests")
def test_alembic_downgrade_base():
    result = subprocess.run(
        ["alembic", "downgrade", "base"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic downgrade base failed:\n{result.stderr}"


@pytest.mark.skipif(not HAS_DATABASE_URL, reason="DATABASE_URL not set — skipping live DB tests")
def test_all_tables_dropped_after_downgrade():
    import sqlalchemy as sa
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    engine.dispose()
    for table in ["case", "plan", "source", "probe", "verdict"]:
        assert table not in tables, f"Table '{table}' still exists after downgrade base"
