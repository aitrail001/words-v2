"""drop legacy next_due_at from entry review states

Revision ID: 053_drop_legacy_next_due_at
Revises: 052_merge_review_schedule_heads
Create Date: 2026-04-15 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "053_drop_legacy_next_due_at"
down_revision = "052_merge_review_schedule_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_entry_review_states_user_next_due", table_name="entry_review_states")
    op.drop_column("entry_review_states", "next_due_at")


def downgrade() -> None:
    op.add_column(
        "entry_review_states",
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_entry_review_states_user_next_due",
        "entry_review_states",
        ["user_id", "is_suspended", "next_due_at"],
        unique=False,
    )
