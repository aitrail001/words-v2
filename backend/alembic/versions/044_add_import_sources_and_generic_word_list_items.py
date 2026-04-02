"""add import sources and generic word list items

Revision ID: 044
Revises: 043
Create Date: 2026-04-02 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("lexicon_version", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("source_identifier", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("matched_entry_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_hash_sha256",
            "pipeline_version",
            "lexicon_version",
            name="uq_import_sources_exact_version",
        ),
    )
    op.create_index(op.f("ix_import_sources_status"), "import_sources", ["status"], unique=False)

    op.create_table(
        "import_source_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frequency_count", sa.Integer(), nullable=False),
        sa.Column("browse_rank_snapshot", sa.Integer(), nullable=True),
        sa.Column("phrase_kind_snapshot", sa.String(length=50), nullable=True),
        sa.Column("cefr_level_snapshot", sa.String(length=16), nullable=True),
        sa.Column("normalization_method", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["import_source_id"], ["import_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_source_id",
            "entry_type",
            "entry_id",
            name="uq_import_source_entries_entry",
        ),
    )
    op.create_index(op.f("ix_import_source_entries_entry_id"), "import_source_entries", ["entry_id"], unique=False)
    op.create_index(
        op.f("ix_import_source_entries_import_source_id"),
        "import_source_entries",
        ["import_source_id"],
        unique=False,
    )

    op.add_column("import_jobs", sa.Column("import_source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("import_jobs", sa.Column("matched_entry_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_index(op.f("ix_import_jobs_import_source_id"), "import_jobs", ["import_source_id"], unique=False)
    op.create_foreign_key(
        "fk_import_jobs_import_source_id_import_sources",
        "import_jobs",
        "import_sources",
        ["import_source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("word_list_items", sa.Column("entry_type", sa.String(length=20), nullable=True))
    op.add_column("word_list_items", sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE word_list_items SET entry_type = 'word', entry_id = word_id")
    op.alter_column("word_list_items", "entry_type", nullable=False)
    op.alter_column("word_list_items", "entry_id", nullable=False)
    op.create_index(op.f("ix_word_list_items_entry_id"), "word_list_items", ["entry_id"], unique=False)
    op.create_check_constraint(
        "ck_word_list_items_entry_type",
        "word_list_items",
        "entry_type IN ('word', 'phrase')",
    )
    op.create_unique_constraint(
        "uq_word_list_item_entry",
        "word_list_items",
        ["word_list_id", "entry_type", "entry_id"],
    )
    op.drop_constraint("uq_word_list_item_word", "word_list_items", type_="unique")
    op.drop_constraint("word_list_items_word_id_fkey", "word_list_items", type_="foreignkey")
    op.drop_column("word_list_items", "word_id")


def downgrade() -> None:
    op.add_column(
        "word_list_items",
        sa.Column("word_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE word_list_items SET word_id = entry_id WHERE entry_type = 'word'")
    op.alter_column("word_list_items", "word_id", nullable=False)
    op.create_foreign_key(
        "word_list_items_word_id_fkey",
        "word_list_items",
        "lexicon.words",
        ["word_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_word_list_item_word",
        "word_list_items",
        ["word_list_id", "word_id"],
    )
    op.drop_constraint("uq_word_list_item_entry", "word_list_items", type_="unique")
    op.drop_constraint("ck_word_list_items_entry_type", "word_list_items", type_="check")
    op.drop_index(op.f("ix_word_list_items_entry_id"), table_name="word_list_items")
    op.drop_column("word_list_items", "entry_id")
    op.drop_column("word_list_items", "entry_type")

    op.drop_constraint("fk_import_jobs_import_source_id_import_sources", "import_jobs", type_="foreignkey")
    op.drop_index(op.f("ix_import_jobs_import_source_id"), table_name="import_jobs")
    op.drop_column("import_jobs", "matched_entry_count")
    op.drop_column("import_jobs", "import_source_id")

    op.drop_index(op.f("ix_import_source_entries_import_source_id"), table_name="import_source_entries")
    op.drop_index(op.f("ix_import_source_entries_entry_id"), table_name="import_source_entries")
    op.drop_table("import_source_entries")

    op.drop_index(op.f("ix_import_sources_status"), table_name="import_sources")
    op.drop_table("import_sources")
