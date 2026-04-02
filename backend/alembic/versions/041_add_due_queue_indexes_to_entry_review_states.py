"""add due queue indexes to entry review states

Revision ID: 041
Revises: 040
Create Date: 2026-04-02 00:30:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_entry_review_states_user_recheck_due",
        "entry_review_states",
        ["user_id", "is_suspended", "recheck_due_at"],
        unique=False,
    )
    op.create_index(
        "ix_entry_review_states_user_next_due",
        "entry_review_states",
        ["user_id", "is_suspended", "next_due_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_entry_review_states_user_next_due", table_name="entry_review_states")
    op.drop_index("ix_entry_review_states_user_recheck_due", table_name="entry_review_states")
