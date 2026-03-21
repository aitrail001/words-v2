"""Add phrase and reference lexicon tables

Revision ID: 011
Revises: 010
Create Date: 2026-03-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phrase_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phrase_text", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=False),
        sa.Column("phrase_kind", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("cefr_level", sa.String(length=10), nullable=True),
        sa.Column("register_label", sa.String(length=32), nullable=True),
        sa.Column("brief_usage_note", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("normalized_form", "language", name="uq_phrase_entry_normalized_language"),
        schema="lexicon",
    )
    op.create_index("ix_phrase_entries_normalized_form", "phrase_entries", ["normalized_form"], schema="lexicon")

    op.create_table(
        "reference_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("display_form", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=False),
        sa.Column("translation_mode", sa.String(length=32), nullable=False),
        sa.Column("brief_description", sa.Text(), nullable=False),
        sa.Column("pronunciation", sa.String(length=255), nullable=False),
        sa.Column("learner_tip", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("normalized_form", "language", name="uq_reference_entry_normalized_language"),
        schema="lexicon",
    )
    op.create_index("ix_reference_entries_reference_type", "reference_entries", ["reference_type"], schema="lexicon")
    op.create_index("ix_reference_entries_normalized_form", "reference_entries", ["normalized_form"], schema="lexicon")

    op.create_table(
        "reference_localizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reference_entry_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lexicon.reference_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("display_form", sa.String(length=255), nullable=False),
        sa.Column("brief_description", sa.Text(), nullable=True),
        sa.Column("translation_mode", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("reference_entry_id", "locale", name="uq_reference_localization_entry_locale"),
        schema="lexicon",
    )
    op.create_index("ix_reference_localizations_reference_entry_id", "reference_localizations", ["reference_entry_id"], schema="lexicon")


def downgrade() -> None:
    op.drop_index("ix_reference_localizations_reference_entry_id", table_name="reference_localizations", schema="lexicon")
    op.drop_table("reference_localizations", schema="lexicon")

    op.drop_index("ix_reference_entries_normalized_form", table_name="reference_entries", schema="lexicon")
    op.drop_index("ix_reference_entries_reference_type", table_name="reference_entries", schema="lexicon")
    op.drop_table("reference_entries", schema="lexicon")

    op.drop_index("ix_phrase_entries_normalized_form", table_name="phrase_entries", schema="lexicon")
    op.drop_table("phrase_entries", schema="lexicon")
