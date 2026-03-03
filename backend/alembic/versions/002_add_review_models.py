"""Add ReviewSession and ReviewCard models

Revision ID: 002
Revises: 001
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cards_reviewed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_review_sessions_user_id", "review_sessions", ["user_id"])

    op.create_table(
        "review_cards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("card_type", sa.String(20), nullable=False),
        sa.Column("quality_rating", sa.Integer(), nullable=True),
        sa.Column("time_spent_ms", sa.Integer(), nullable=True),
        sa.Column("ease_factor", sa.Float(), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_review_cards_session_id", "review_cards", ["session_id"])


def downgrade() -> None:
    op.drop_table("review_cards")
    op.drop_table("review_sessions")
