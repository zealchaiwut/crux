"""Add 'inconclusive' to probe_status_enum

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Only ALTER TYPE for PostgreSQL; SQLite has no native ENUM type
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE probe_status_enum ADD VALUE IF NOT EXISTS 'inconclusive'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
