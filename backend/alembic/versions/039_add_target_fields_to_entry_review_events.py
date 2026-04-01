"""add target fields to entry review events

Revision ID: 039
Revises: 038
Create Date: 2026-04-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entry_review_events", sa.Column("target_type", sa.String(length=32), nullable=True))
    op.add_column("entry_review_events", sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        "ix_entry_review_events_target_id",
        "entry_review_events",
        ["target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entry_review_events_target_id", table_name="entry_review_events")
    op.drop_column("entry_review_events", "target_id")
    op.drop_column("entry_review_events", "target_type")
