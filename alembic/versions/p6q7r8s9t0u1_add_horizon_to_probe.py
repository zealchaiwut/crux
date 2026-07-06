"""Add horizon column to probe table

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-07-04

Changes:
- Adds horizon (nullable enum: short/mid/long) to probe table.
- Existing rows get NULL; no backfill needed (NULL is explicitly valid per AC2).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "probe",
        sa.Column(
            "horizon",
            sa.Enum("short", "mid", "long", name="probe_horizon_enum"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("probe", "horizon")
    op.execute("DROP TYPE IF EXISTS probe_horizon_enum")
