"""Add lexicon voice assets

Revision ID: 030
Revises: 029
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_voice_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meaning_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meaning_example_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_scope", sa.String(length=16), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("voice_role", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("voice_id", sa.String(length=128), nullable=False),
        sa.Column("profile_key", sa.String(length=32), nullable=False),
        sa.Column("audio_format", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=True),
        sa.Column("speaking_rate", sa.Float(), nullable=True),
        sa.Column("pitch_semitones", sa.Float(), nullable=True),
        sa.Column("lead_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tail_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effects_profile_id", sa.String(length=64), nullable=True),
        sa.Column("storage_kind", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("storage_base", sa.String(length=1024), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="generated"),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["meaning_example_id"], ["lexicon.meaning_examples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meaning_id"], ["lexicon.meanings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["word_id"], ["lexicon.words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_kind", "storage_base", "relative_path", name="uq_lexicon_voice_assets_storage_path"),
        sa.CheckConstraint("content_scope IN ('word', 'definition', 'example')", name="ck_lexicon_voice_assets_content_scope"),
        sa.CheckConstraint("voice_role IN ('female', 'male')", name="ck_lexicon_voice_assets_voice_role"),
        sa.CheckConstraint(
            "((word_id IS NOT NULL)::int + (meaning_id IS NOT NULL)::int + (meaning_example_id IS NOT NULL)::int) = 1",
            name="ck_lexicon_voice_assets_single_parent",
        ),
        schema="lexicon",
    )
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_word_id"), "lexicon_voice_assets", ["word_id"], unique=False, schema="lexicon")
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_meaning_id"), "lexicon_voice_assets", ["meaning_id"], unique=False, schema="lexicon")
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_meaning_example_id"), "lexicon_voice_assets", ["meaning_example_id"], unique=False, schema="lexicon")


def downgrade() -> None:
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_meaning_example_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_meaning_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_word_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_table("lexicon_voice_assets", schema="lexicon")
