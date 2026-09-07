"""Add claim_verification table for hub claim-verification endpoint

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-09-07

Changes:
- Creates claim_verification table to persist hub claim-verification results,
  enabling cache lookups so the same claim is not re-researched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claim_verification",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("claim_hash", sa.String(64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_claim_verification_claim_hash",
        "claim_verification",
        ["claim_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_claim_verification_claim_hash", table_name="claim_verification")
    op.drop_table("claim_verification")
