"""Add User, Word, Meaning, Translation models

Revision ID: 001
Revises:
Create Date: 2026-02-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "words",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word", sa.String(255), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("phonetic", sa.String(255), nullable=True),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column("word_forms", JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("word", "language", name="uq_word_language"),
    )
    op.create_index("ix_words_frequency_rank", "words", ["frequency_rank"])

    op.create_table(
        "meanings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("part_of_speech", sa.String(50), nullable=True),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_meanings_word_id", "meanings", ["word_id"])

    op.create_table(
        "translations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("translation", sa.Text(), nullable=False),
        sa.UniqueConstraint("meaning_id", "language", name="uq_translation_meaning_language"),
    )
    op.create_index("ix_translations_meaning_id", "translations", ["meaning_id"])


def downgrade() -> None:
    op.drop_table("translations")
    op.drop_table("meanings")
    op.drop_table("words")
    op.drop_table("users")
