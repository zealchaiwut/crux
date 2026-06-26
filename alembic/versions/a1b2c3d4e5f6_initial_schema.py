"""Initial schema: case, plan, source, probe, verdict tables

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres ENUM types — enforced at DB level
    stage_enum = postgresql.ENUM(
        "sharpened", "bake_off", "gather", "weigh", "probe", "verdict",
        name="stage_enum",
    )
    plan_label_enum = postgresql.ENUM("A", "B", "C", name="plan_label_enum")
    source_kind_enum = postgresql.ENUM(
        "book", "article", "youtube",
        name="source_kind_enum",
    )
    probe_type_enum = postgresql.ENUM(
        "measurement", "lab-test", "behaviour-experiment", "prototype",
        name="probe_type_enum",
    )
    probe_status_enum = postgresql.ENUM(
        "designed", "running", "confirmed", "killed",
        name="probe_status_enum",
    )
    verdict_outcome_enum = postgresql.ENUM(
        "confirmed", "killed", "inconclusive",
        name="verdict_outcome_enum",
    )

    stage_enum.create(op.get_bind(), checkfirst=True)
    plan_label_enum.create(op.get_bind(), checkfirst=True)
    source_kind_enum.create(op.get_bind(), checkfirst=True)
    probe_type_enum.create(op.get_bind(), checkfirst=True)
    probe_status_enum.create(op.get_bind(), checkfirst=True)
    verdict_outcome_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "case",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("raw_problem", sa.Text(), nullable=False),
        sa.Column("sharpened", sa.Text()),
        sa.Column("not_investigating", sa.Text()),
        sa.Column("stage", postgresql.ENUM(name="stage_enum", create_type=False), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "plan",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # ON DELETE CASCADE: removing a Case cascades to its Plans
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", postgresql.ENUM(name="plan_label_enum", create_type=False), nullable=False),
        sa.Column("mechanism", sa.Text()),
        sa.Column("prior", sa.Text()),
        sa.Column("current_rank", sa.Integer()),
    )

    op.create_table(
        "source",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # ON DELETE CASCADE: removing a Plan cascades to its Sources
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", postgresql.ENUM(name="source_kind_enum", create_type=False), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("claim", sa.Text()),
        sa.Column("citation", sa.Text()),
    )

    op.create_table(
        "probe",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # ON DELETE CASCADE: removing a Case cascades to its Probes
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", postgresql.ENUM(name="probe_type_enum", create_type=False), nullable=False),
        sa.Column("target_metric", sa.Text()),
        sa.Column(
            "status",
            postgresql.ENUM(name="probe_status_enum", create_type=False),
            nullable=False,
            server_default="designed",
        ),
        sa.Column("due_date", sa.Date()),
        sa.Column("commander_spec", sa.Text()),
    )

    op.create_table(
        "verdict",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # ON DELETE RESTRICT: a Probe with a Verdict cannot be deleted (preserves audit trail)
        sa.Column(
            "probe_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("probe.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("outcome", postgresql.ENUM(name="verdict_outcome_enum", create_type=False), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "decided_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("verdict")
    op.drop_table("probe")
    op.drop_table("source")
    op.drop_table("plan")
    op.drop_table("case")

    # Drop Postgres ENUM types created in upgrade
    postgresql.ENUM(name="verdict_outcome_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="probe_status_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="probe_type_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="source_kind_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="plan_label_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="stage_enum").drop(op.get_bind(), checkfirst=True)
