"""Add weigh_context to case and standing to plan

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case", sa.Column("weigh_context", sa.Text(), nullable=True))
    op.add_column("plan", sa.Column("standing", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan", "standing")
    op.drop_column("case", "weigh_context")
