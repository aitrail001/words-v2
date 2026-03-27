"""Add entry review state and event tables

Revision ID: 028
Revises: 027
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_review_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("difficulty", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("success_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapse_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_remembered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_prompt_type", sa.String(length=32), nullable=True),
        sa.Column("last_outcome", sa.String(length=32), nullable=True),
        sa.Column("is_fragile", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("relearning", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("relearning_trigger", sa.String(length=32), nullable=True),
        sa.Column("recheck_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "entry_type", "entry_id", name="uq_entry_review_state_user_entry"),
    )
    op.create_index("ix_entry_review_states_user_id", "entry_review_states", ["user_id"])
    op.create_index("ix_entry_review_states_entry_id", "entry_review_states", ["entry_id"])

    op.create_table(
        "entry_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_state_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_type", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("selected_option_id", sa.String(length=8), nullable=True),
        sa.Column("scheduled_interval_days", sa.Integer(), nullable=True),
        sa.Column("scheduled_by", sa.String(length=32), nullable=True),
        sa.Column("time_spent_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["review_state_id"], ["entry_review_states.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entry_review_events_user_id", "entry_review_events", ["user_id"])
    op.create_index("ix_entry_review_events_review_state_id", "entry_review_events", ["review_state_id"])
    op.create_index("ix_entry_review_events_entry_id", "entry_review_events", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_entry_review_events_entry_id", table_name="entry_review_events")
    op.drop_index("ix_entry_review_events_review_state_id", table_name="entry_review_events")
    op.drop_index("ix_entry_review_events_user_id", table_name="entry_review_events")
    op.drop_table("entry_review_events")

    op.drop_index("ix_entry_review_states_entry_id", table_name="entry_review_states")
    op.drop_index("ix_entry_review_states_user_id", table_name="entry_review_states")
    op.drop_table("entry_review_states")
