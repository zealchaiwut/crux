"""Update support_status enum values and add support_rationale to source

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-06-24

Changes:
- Replaces support_status enum values (supports/contradicts/neutral/inconclusive)
  with (supports/partial/contradicts/unverified), makes column non-nullable with
  server default 'unverified', and enables string validation.
- Adds support_rationale (Text, nullable) column.
- Data migration: existing 'neutral' rows become 'partial'; existing 'inconclusive'
  and NULL rows become 'unverified'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_VALUES = ("supports", "contradicts", "neutral", "inconclusive")
_NEW_VALUES = ("supports", "partial", "contradicts", "unverified")


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Detach the column from the enum first so we can migrate the data to
        # the new value set (the old enum has no 'partial'/'unverified', so the
        # UPDATEs must run while the column is plain text).
        op.execute(sa.text(
            "ALTER TABLE source ALTER COLUMN support_status TYPE text "
            "USING support_status::text"
        ))
        op.execute(sa.text(
            "UPDATE source SET support_status = 'partial' WHERE support_status = 'neutral'"
        ))
        op.execute(sa.text(
            "UPDATE source SET support_status = 'unverified' "
            "WHERE support_status = 'inconclusive' OR support_status IS NULL"
        ))
        op.execute(sa.text("DROP TYPE support_status_enum"))
        op.execute(sa.text(
            "CREATE TYPE support_status_enum AS ENUM "
            "('supports', 'partial', 'contradicts', 'unverified')"
        ))
        op.execute(sa.text(
            "ALTER TABLE source "
            "ALTER COLUMN support_status TYPE support_status_enum "
            "USING support_status::support_status_enum"
        ))
        op.execute(sa.text(
            "ALTER TABLE source ALTER COLUMN support_status SET DEFAULT 'unverified'"
        ))
        op.execute(sa.text(
            "ALTER TABLE source ALTER COLUMN support_status SET NOT NULL"
        ))
    else:
        # SQLite stores the enum as VARCHAR + CHECK; migrate the data first,
        # then batch alter recreates the table with the new CHECK constraint.
        op.execute(sa.text(
            "UPDATE source SET support_status = 'partial' WHERE support_status = 'neutral'"
        ))
        op.execute(sa.text(
            "UPDATE source SET support_status = 'unverified' "
            "WHERE support_status = 'inconclusive' OR support_status IS NULL"
        ))
        with op.batch_alter_table("source") as batch_op:
            batch_op.alter_column(
                "support_status",
                type_=sa.Enum(*_NEW_VALUES, name="support_status_enum"),
                nullable=False,
                server_default="unverified",
            )

    op.add_column(
        "source",
        sa.Column("support_rationale", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source", "support_rationale")

    bind = op.get_bind()

    # Reverse data migration: map new-only values back to old equivalents.
    op.execute(sa.text(
        "UPDATE source SET support_status = 'neutral' WHERE support_status = 'partial'"
    ))
    op.execute(sa.text(
        "UPDATE source SET support_status = 'inconclusive' WHERE support_status = 'unverified'"
    ))

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "ALTER TABLE source ALTER COLUMN support_status DROP DEFAULT"
        ))
        op.execute(sa.text(
            "ALTER TABLE source ALTER COLUMN support_status DROP NOT NULL"
        ))
        op.execute(sa.text(
            "ALTER TYPE support_status_enum RENAME TO support_status_enum_old"
        ))
        op.execute(sa.text(
            "CREATE TYPE support_status_enum AS ENUM "
            "('supports', 'contradicts', 'neutral', 'inconclusive')"
        ))
        op.execute(sa.text(
            "ALTER TABLE source "
            "ALTER COLUMN support_status TYPE support_status_enum "
            "USING support_status::text::support_status_enum"
        ))
        op.execute(sa.text("DROP TYPE support_status_enum_old"))
    else:
        with op.batch_alter_table("source") as batch_op:
            batch_op.alter_column(
                "support_status",
                type_=sa.Enum(*_OLD_VALUES, name="support_status_enum"),
                nullable=True,
                server_default=None,
            )
