"""Add content-post probe type and metric_value column to verdict

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-09-07

Changes:
- Adds 'content-post' as a valid value on probe_type_enum so probes can be
  classified as content experiments (post variant A vs B and measure engagement).
- Adds metric_value Float column to the verdict table so the numeric engagement
  figure that settled a content-post verdict is persisted alongside the outcome.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres: extend the probe_type_enum with 'content-post'
    op.execute("ALTER TYPE probe_type_enum ADD VALUE IF NOT EXISTS 'content-post'")

    # Add nullable metric_value column to verdict (nullable so existing rows are unaffected)
    op.add_column("verdict", sa.Column("metric_value", sa.Float(), nullable=True))


def downgrade() -> None:
    # Postgres cannot remove enum values; removing the column is safe
    op.drop_column("verdict", "metric_value")
