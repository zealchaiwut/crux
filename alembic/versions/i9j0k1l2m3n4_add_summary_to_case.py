"""Add summary column to case table

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-06-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("case", "summary")
