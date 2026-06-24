"""Add support_status and rationale columns to source table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-06-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUPPORT_STATUS = ("supports", "contradicts", "neutral", "inconclusive")


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column(
            "support_status",
            sa.Enum(*_SUPPORT_STATUS, name="support_status_enum"),
            nullable=True,
        ),
    )
    op.add_column("source", sa.Column("rationale", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source", "rationale")
    op.drop_column("source", "support_status")
    op.execute("DROP TYPE IF EXISTS support_status_enum")
