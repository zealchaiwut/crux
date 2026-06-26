"""Add case_embedding table for Claude embedding-based similarity (issue #68)

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-06-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_embedding",
        sa.Column("case_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("case.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("embedding", sa.Text, nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("case_embedding")
