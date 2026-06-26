"""Add cost, time, note columns to probe table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("probe", sa.Column("cost", sa.Text(), nullable=True))
    op.add_column("probe", sa.Column("time", sa.Text(), nullable=True))
    op.add_column("probe", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("probe", "note")
    op.drop_column("probe", "time")
    op.drop_column("probe", "cost")
