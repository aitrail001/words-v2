"""Add learner knowledge map tables

Revision ID: 016
Revises: 015
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learner_entry_statuses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'undecided'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("entry_type IN ('word', 'phrase')", name="ck_learner_entry_status_entry_type"),
        sa.CheckConstraint(
            "status IN ('undecided', 'to_learn', 'learning', 'known')",
            name="ck_learner_entry_status_value",
        ),
        sa.UniqueConstraint("user_id", "entry_type", "entry_id", name="uq_learner_entry_status_user_entry"),
    )
    op.create_index("ix_learner_entry_statuses_user_id", "learner_entry_statuses", ["user_id"])
    op.create_index("ix_learner_entry_statuses_entry_id", "learner_entry_statuses", ["entry_id"])

    op.create_table(
        "user_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accent_preference", sa.String(length=10), nullable=False, server_default=sa.text("'us'")),
        sa.Column("translation_locale", sa.String(length=16), nullable=False, server_default=sa.text("'zh-Hans'")),
        sa.Column("knowledge_view_preference", sa.String(length=16), nullable=False, server_default=sa.text("'cards'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("accent_preference IN ('us', 'uk', 'au')", name="ck_user_preferences_accent"),
        sa.CheckConstraint("knowledge_view_preference IN ('cards', 'tags', 'list')", name="ck_user_preferences_view"),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user"),
    )

    op.create_table(
        "search_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=True),
        sa.Column("entry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("last_searched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "entry_type IS NULL OR entry_type IN ('word', 'phrase')",
            name="ck_search_history_entry_type",
        ),
        sa.UniqueConstraint("user_id", "query", name="uq_search_history_user_query"),
    )
    op.create_index("ix_search_history_user_id", "search_history", ["user_id"])
    op.create_index("ix_search_history_last_searched_at", "search_history", ["last_searched_at"])


def downgrade() -> None:
    op.drop_index("ix_search_history_last_searched_at", table_name="search_history")
    op.drop_index("ix_search_history_user_id", table_name="search_history")
    op.drop_table("search_history")

    op.drop_table("user_preferences")

    op.drop_index("ix_learner_entry_statuses_entry_id", table_name="learner_entry_statuses")
    op.drop_index("ix_learner_entry_statuses_user_id", table_name="learner_entry_statuses")
    op.drop_table("learner_entry_statuses")
