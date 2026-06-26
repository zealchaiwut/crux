"""Add created_at column to verdict table

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-06-25

Changes:
- Adds created_at (TIMESTAMP WITH TIME ZONE, nullable) column to verdict.
- Backfills existing rows from decided_at so no row has a null created_at
  after migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n4o5p6q7r8s9"
down_revision: Union[str, None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "verdict",
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Backfill from decided_at for existing rows so no record produces a null
    # created_at in the API response after this migration.
    op.execute(sa.text(
        "UPDATE verdict SET created_at = decided_at WHERE created_at IS NULL AND decided_at IS NOT NULL"
    ))


def downgrade() -> None:
    op.drop_column("verdict", "created_at")
