"""Add NotebookLM fields to case

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-07-02

Changes:
- Adds notebooklm_url (Text, nullable) — link to the generated NotebookLM
  notebook so the user can open it to listen/chat.
- Adds notebooklm_audio (Text, nullable) — server path to the downloaded
  debate-podcast mp3.
Both NULL until a debate podcast is generated for the case.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case", sa.Column("notebooklm_url", sa.Text(), nullable=True))
    op.add_column("case", sa.Column("notebooklm_audio", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("case", "notebooklm_audio")
    op.drop_column("case", "notebooklm_url")
