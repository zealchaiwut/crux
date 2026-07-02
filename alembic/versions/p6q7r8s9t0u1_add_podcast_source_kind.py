"""Add 'podcast' value to source_kind_enum

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-02

Changes:
- Adds 'podcast' as a valid value on the source_kind_enum Postgres enum so
  sources can be classified as podcasts alongside book/article/youtube.
- Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction. IF NOT
  EXISTS makes the migration idempotent. Enum values cannot be dropped, so
  downgrade is a no-op.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_kind_enum ADD VALUE IF NOT EXISTS 'podcast'")


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type; nothing to do.
    pass
