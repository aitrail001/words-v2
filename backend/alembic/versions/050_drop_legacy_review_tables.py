"""drop legacy review tables

Revision ID: 050_drop_legacy_review_tables
Revises: 049_job_entry_counts
Create Date: 2026-04-04 18:20:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "050_drop_legacy_review_tables"
down_revision = "049_job_entry_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("review_history")
    op.drop_table("learning_queue_items")
    op.drop_table("review_cards")
    op.drop_table("review_sessions")


def downgrade() -> None:
    raise NotImplementedError("Legacy review tables are intentionally not restored.")
