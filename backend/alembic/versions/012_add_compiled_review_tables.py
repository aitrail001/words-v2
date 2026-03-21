"""Add compiled lexicon review tables

Revision ID: 012
Revises: 011
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_artifact_review_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_family", sa.String(length=32), nullable=False),
        sa.Column("artifact_filename", sa.String(length=255), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_row_count", sa.Integer(), nullable=False),
        sa.Column("compiled_schema_version", sa.String(length=32), nullable=False),
        sa.Column("snapshot_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("generator_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("artifact_sha256", name="uq_lexicon_artifact_review_batch_sha256"),
        schema="lexicon",
    )
    op.create_index("ix_lexicon_artifact_review_batches_artifact_family", "lexicon_artifact_review_batches", ["artifact_family"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_batches_created_by", "lexicon_artifact_review_batches", ["created_by"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_batches_snapshot_id", "lexicon_artifact_review_batches", ["snapshot_id"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_batches_status", "lexicon_artifact_review_batches", ["status"], schema="lexicon")

    op.create_table(
        "lexicon_artifact_review_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("lexicon.lexicon_artifact_review_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.String(length=255), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=True),
        sa.Column("display_text", sa.String(length=255), nullable=False),
        sa.Column("entity_category", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column("cefr_level", sa.String(length=8), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("review_priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("validator_status", sa.String(length=16), nullable=True),
        sa.Column("validator_issues", JSONB(), nullable=True),
        sa.Column("qc_status", sa.String(length=16), nullable=True),
        sa.Column("qc_score", sa.Float(), nullable=True),
        sa.Column("qc_issues", JSONB(), nullable=True),
        sa.Column("regen_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("import_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compiled_payload", JSONB(), nullable=False),
        sa.Column("compiled_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "entry_id", name="uq_lexicon_artifact_review_item_batch_entry"),
        schema="lexicon",
    )
    op.create_index("ix_lexicon_artifact_review_items_batch_id", "lexicon_artifact_review_items", ["batch_id"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_entry_type", "lexicon_artifact_review_items", ["entry_type"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_entity_category", "lexicon_artifact_review_items", ["entity_category"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_frequency_rank", "lexicon_artifact_review_items", ["frequency_rank"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_review_priority", "lexicon_artifact_review_items", ["review_priority"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_review_status", "lexicon_artifact_review_items", ["review_status"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_items_reviewed_by", "lexicon_artifact_review_items", ["reviewed_by"], schema="lexicon")

    op.create_table(
        "lexicon_artifact_review_item_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("lexicon.lexicon_artifact_review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="lexicon",
    )
    op.create_index("ix_lexicon_artifact_review_item_events_actor_user_id", "lexicon_artifact_review_item_events", ["actor_user_id"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_item_events_event_type", "lexicon_artifact_review_item_events", ["event_type"], schema="lexicon")
    op.create_index("ix_lexicon_artifact_review_item_events_item_id", "lexicon_artifact_review_item_events", ["item_id"], schema="lexicon")

    op.create_table(
        "lexicon_regeneration_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("lexicon.lexicon_artifact_review_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("lexicon.lexicon_artifact_review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.String(length=255), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("request_reason", sa.Text(), nullable=True),
        sa.Column("request_payload", JSONB(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "item_id", name="uq_lexicon_regeneration_request_batch_item"),
        schema="lexicon",
    )
    op.create_index("ix_lexicon_regeneration_requests_batch_id", "lexicon_regeneration_requests", ["batch_id"], schema="lexicon")
    op.create_index("ix_lexicon_regeneration_requests_created_by", "lexicon_regeneration_requests", ["created_by"], schema="lexicon")
    op.create_index("ix_lexicon_regeneration_requests_item_id", "lexicon_regeneration_requests", ["item_id"], schema="lexicon")


def downgrade() -> None:
    op.drop_index("ix_lexicon_regeneration_requests_item_id", table_name="lexicon_regeneration_requests", schema="lexicon")
    op.drop_index("ix_lexicon_regeneration_requests_created_by", table_name="lexicon_regeneration_requests", schema="lexicon")
    op.drop_index("ix_lexicon_regeneration_requests_batch_id", table_name="lexicon_regeneration_requests", schema="lexicon")
    op.drop_table("lexicon_regeneration_requests", schema="lexicon")

    op.drop_index("ix_lexicon_artifact_review_item_events_item_id", table_name="lexicon_artifact_review_item_events", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_item_events_event_type", table_name="lexicon_artifact_review_item_events", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_item_events_actor_user_id", table_name="lexicon_artifact_review_item_events", schema="lexicon")
    op.drop_table("lexicon_artifact_review_item_events", schema="lexicon")

    op.drop_index("ix_lexicon_artifact_review_items_reviewed_by", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_review_status", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_review_priority", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_frequency_rank", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_entity_category", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_entry_type", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_items_batch_id", table_name="lexicon_artifact_review_items", schema="lexicon")
    op.drop_table("lexicon_artifact_review_items", schema="lexicon")

    op.drop_index("ix_lexicon_artifact_review_batches_status", table_name="lexicon_artifact_review_batches", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_batches_snapshot_id", table_name="lexicon_artifact_review_batches", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_batches_created_by", table_name="lexicon_artifact_review_batches", schema="lexicon")
    op.drop_index("ix_lexicon_artifact_review_batches_artifact_family", table_name="lexicon_artifact_review_batches", schema="lexicon")
    op.drop_table("lexicon_artifact_review_batches", schema="lexicon")
