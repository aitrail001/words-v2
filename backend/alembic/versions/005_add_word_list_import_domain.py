"""Add word list import domain tables

Revision ID: 005
Revises: 004
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_books_uploaded_by", "books", ["uploaded_by"])

    op.create_table(
        "word_lists",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("book_id", UUID(as_uuid=True), sa.ForeignKey("books.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_word_lists_user_id", "word_lists", ["user_id"])
    op.create_index("ix_word_lists_book_id", "word_lists", ["book_id"])

    op.create_table(
        "word_list_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word_list_id", UUID(as_uuid=True), sa.ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context_sentence", sa.Text(), nullable=True),
        sa.Column("frequency_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("variation_data", sa.JSON(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("word_list_id", "word_id", name="uq_word_list_item_word"),
    )
    op.create_index("ix_word_list_items_word_list_id", "word_list_items", ["word_list_id"])
    op.create_index("ix_word_list_items_word_id", "word_list_items", ["word_id"])

    op.create_table(
        "import_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("book_id", UUID(as_uuid=True), sa.ForeignKey("books.id", ondelete="SET NULL"), nullable=True),
        sa.Column("word_list_id", UUID(as_uuid=True), sa.ForeignKey("word_lists.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("list_name", sa.String(length=255), nullable=False),
        sa.Column("list_description", sa.Text(), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_found_words", sa.JSON(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_jobs_user_id", "import_jobs", ["user_id"])
    op.create_index("ix_import_jobs_book_id", "import_jobs", ["book_id"])
    op.create_index("ix_import_jobs_word_list_id", "import_jobs", ["word_list_id"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_word_list_id", table_name="import_jobs")
    op.drop_index("ix_import_jobs_book_id", table_name="import_jobs")
    op.drop_index("ix_import_jobs_user_id", table_name="import_jobs")
    op.drop_table("import_jobs")

    op.drop_index("ix_word_list_items_word_id", table_name="word_list_items")
    op.drop_index("ix_word_list_items_word_list_id", table_name="word_list_items")
    op.drop_table("word_list_items")

    op.drop_index("ix_word_lists_book_id", table_name="word_lists")
    op.drop_index("ix_word_lists_user_id", table_name="word_lists")
    op.drop_table("word_lists")

    op.drop_index("ix_books_uploaded_by", table_name="books")
    op.drop_table("books")
