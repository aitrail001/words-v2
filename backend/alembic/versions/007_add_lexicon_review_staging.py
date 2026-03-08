"""Add lexicon review staging tables

Revision ID: 007
Revises: 006
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_review_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="importing"),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("snapshot_id", sa.String(length=255), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_required_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("import_metadata", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "source_hash", name="uq_lexicon_review_batch_user_hash"),
    )
    op.create_index("ix_lexicon_review_batches_user_id", "lexicon_review_batches", ["user_id"])
    op.create_index("ix_lexicon_review_batches_status", "lexicon_review_batches", ["status"])
    op.create_index("ix_lexicon_review_batches_created_at", "lexicon_review_batches", ["created_at"])

    op.create_table(
        "lexicon_review_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("lexicon_review_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lexeme_id", sa.String(length=255), nullable=False),
        sa.Column("lemma", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("wordfreq_rank", sa.Integer(), nullable=True),
        sa.Column("risk_band", sa.String(length=50), nullable=False),
        sa.Column("selection_risk_score", sa.Integer(), nullable=False),
        sa.Column("deterministic_selected_wn_synset_ids", sa.JSON(), nullable=False),
        sa.Column("reranked_selected_wn_synset_ids", sa.JSON(), nullable=True),
        sa.Column("candidate_metadata", sa.JSON(), nullable=False),
        sa.Column("auto_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("review_override_wn_synset_ids", sa.JSON(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "lexeme_id", name="uq_lexicon_review_item_batch_lexeme"),
    )
    op.create_index("ix_lexicon_review_items_batch_id", "lexicon_review_items", ["batch_id"])
    op.create_index("ix_lexicon_review_items_lemma", "lexicon_review_items", ["lemma"])
    op.create_index("ix_lexicon_review_items_wordfreq_rank", "lexicon_review_items", ["wordfreq_rank"])
    op.create_index("ix_lexicon_review_items_risk_band", "lexicon_review_items", ["risk_band"])
    op.create_index("ix_lexicon_review_items_auto_accepted", "lexicon_review_items", ["auto_accepted"])
    op.create_index("ix_lexicon_review_items_review_required", "lexicon_review_items", ["review_required"])
    op.create_index("ix_lexicon_review_items_review_status", "lexicon_review_items", ["review_status"])
    op.create_index("ix_lexicon_review_items_reviewed_by", "lexicon_review_items", ["reviewed_by"])


def downgrade() -> None:
    op.drop_index("ix_lexicon_review_items_reviewed_by", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_review_status", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_review_required", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_auto_accepted", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_risk_band", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_wordfreq_rank", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_lemma", table_name="lexicon_review_items")
    op.drop_index("ix_lexicon_review_items_batch_id", table_name="lexicon_review_items")
    op.drop_table("lexicon_review_items")

    op.drop_index("ix_lexicon_review_batches_created_at", table_name="lexicon_review_batches")
    op.drop_index("ix_lexicon_review_batches_status", table_name="lexicon_review_batches")
    op.drop_index("ix_lexicon_review_batches_user_id", table_name="lexicon_review_batches")
    op.drop_table("lexicon_review_batches")
