"""Add support_status and support_rationale to source table

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


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql
        support_status_enum = postgresql.ENUM(
            "supports", "partial", "contradicts", "unverified",
            name="support_status_enum",
        )
        support_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "source",
        sa.Column(
            "support_status",
            sa.Enum(
                "supports", "partial", "contradicts", "unverified",
                name="support_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "source",
        sa.Column("support_rationale", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source", "support_rationale")
    op.drop_column("source", "support_status")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql
        postgresql.ENUM(name="support_status_enum").drop(bind, checkfirst=True)
