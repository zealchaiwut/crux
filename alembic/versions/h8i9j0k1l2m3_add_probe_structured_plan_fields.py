"""Add steps, duration, decision_rule to probe table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-06-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("probe", sa.Column("steps", sa.JSON(), nullable=True))
    op.add_column("probe", sa.Column("duration", sa.Text(), nullable=True))
    op.add_column("probe", sa.Column("decision_rule", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("probe", "decision_rule")
    op.drop_column("probe", "duration")
    op.drop_column("probe", "steps")
