"""Add learner catalog projection table

Revision ID: 027
Revises: 026
Create Date: 2026-03-27
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learner_catalog_entries",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("entry_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("display_text", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=False),
        sa.Column("browse_rank", sa.Integer(), nullable=False),
        sa.Column("bucket_start", sa.Integer(), nullable=False),
        sa.Column("cefr_level", sa.String(length=50), nullable=True),
        sa.Column("primary_part_of_speech", sa.String(length=50), nullable=True),
        sa.Column("phrase_kind", sa.String(length=50), nullable=True),
        sa.Column("is_ranked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_type", "entry_id", name="uq_learner_catalog_entries_entry"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_learner_catalog_entries_entry_id",
        "learner_catalog_entries",
        ["entry_id"],
        unique=False,
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_learner_catalog_entries_normalized_form",
        "learner_catalog_entries",
        ["normalized_form"],
        unique=False,
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_learner_catalog_entries_browse_rank",
        "learner_catalog_entries",
        ["browse_rank"],
        unique=False,
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_learner_catalog_entries_bucket_start",
        "learner_catalog_entries",
        ["bucket_start"],
        unique=False,
        schema="lexicon",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lexicon_learner_catalog_entries_bucket_start",
        table_name="learner_catalog_entries",
        schema="lexicon",
    )
    op.drop_index(
        "ix_lexicon_learner_catalog_entries_browse_rank",
        table_name="learner_catalog_entries",
        schema="lexicon",
    )
    op.drop_index(
        "ix_lexicon_learner_catalog_entries_normalized_form",
        table_name="learner_catalog_entries",
        schema="lexicon",
    )
    op.drop_index(
        "ix_lexicon_learner_catalog_entries_entry_id",
        table_name="learner_catalog_entries",
        schema="lexicon",
    )
    op.drop_table("learner_catalog_entries", schema="lexicon")
