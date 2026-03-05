"""Add learning queue and review history models

Revision ID: 004
Revises: 003
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_queue_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "meaning_id", name="uq_learning_queue_user_meaning"),
    )
    op.create_index("ix_learning_queue_items_user_id", "learning_queue_items", ["user_id"])
    op.create_index("ix_learning_queue_items_meaning_id", "learning_queue_items", ["meaning_id"])

    op.create_table(
        "review_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_type", sa.String(20), nullable=False),
        sa.Column("quality_rating", sa.Integer(), nullable=False),
        sa.Column("time_spent_ms", sa.Integer(), nullable=True),
        sa.Column("ease_factor", sa.Float(), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("repetitions", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_review_history_user_id", "review_history", ["user_id"])
    op.create_index("ix_review_history_meaning_id", "review_history", ["meaning_id"])


def downgrade() -> None:
    op.drop_index("ix_review_history_meaning_id", table_name="review_history")
    op.drop_index("ix_review_history_user_id", table_name="review_history")
    op.drop_table("review_history")

    op.drop_index("ix_learning_queue_items_meaning_id", table_name="learning_queue_items")
    op.drop_index("ix_learning_queue_items_user_id", table_name="learning_queue_items")
    op.drop_table("learning_queue_items")
