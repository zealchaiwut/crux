"""Add rationale column to plan table

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-06-26

Changes:
- Adds rationale (Text, nullable) column to plan.
- Existing rows get NULL; no backfill needed since rationale is written on next rerank call.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4o5p6q7r8s9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan",
        sa.Column("rationale", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan", "rationale")
