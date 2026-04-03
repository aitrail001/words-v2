"""add admin import cache management tables

Revision ID: 048
Revises: 047
Create Date: 2026-04-04 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_batches_created_by_user_id"), "import_batches", ["created_by_user_id"], unique=False)

    op.add_column("import_sources", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("import_sources", sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("import_sources", sa.Column("deletion_reason", sa.Text(), nullable=True))
    op.create_index(op.f("ix_import_sources_deleted_at"), "import_sources", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_import_sources_deleted_by_user_id"), "import_sources", ["deleted_by_user_id"], unique=False)
    op.create_foreign_key(
        "fk_import_sources_deleted_by_user_id_users",
        "import_sources",
        "users",
        ["deleted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_import_sources_status_processed_at_desc",
        "import_sources",
        ["status", "processed_at"],
        unique=False,
    )

    op.add_column("import_jobs", sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("import_jobs", sa.Column("job_origin", sa.String(length=32), nullable=False, server_default="user_import"))
    op.add_column("import_jobs", sa.Column("source_title_snapshot", sa.String(length=500), nullable=True))
    op.add_column("import_jobs", sa.Column("source_author_snapshot", sa.String(length=500), nullable=True))
    op.add_column("import_jobs", sa.Column("source_isbn_snapshot", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_import_jobs_import_batch_id"), "import_jobs", ["import_batch_id"], unique=False)
    op.create_index(op.f("ix_import_jobs_job_origin"), "import_jobs", ["job_origin"], unique=False)
    op.create_index(
        "ix_import_jobs_import_source_created_at_desc",
        "import_jobs",
        ["import_source_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_import_jobs_import_source_started_created",
        "import_jobs",
        ["import_source_id", "started_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_import_jobs_import_batch_created_at_desc",
        "import_jobs",
        ["import_batch_id", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_import_jobs_import_batch_id_import_batches",
        "import_jobs",
        "import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("import_jobs", "job_origin", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_import_jobs_import_batch_id_import_batches", "import_jobs", type_="foreignkey")
    op.drop_index("ix_import_jobs_import_batch_created_at_desc", table_name="import_jobs")
    op.drop_index("ix_import_jobs_import_source_started_created", table_name="import_jobs")
    op.drop_index("ix_import_jobs_import_source_created_at_desc", table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_job_origin"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_import_batch_id"), table_name="import_jobs")
    op.drop_column("import_jobs", "source_isbn_snapshot")
    op.drop_column("import_jobs", "source_author_snapshot")
    op.drop_column("import_jobs", "source_title_snapshot")
    op.drop_column("import_jobs", "job_origin")
    op.drop_column("import_jobs", "import_batch_id")

    op.drop_index("ix_import_sources_status_processed_at_desc", table_name="import_sources")
    op.drop_constraint("fk_import_sources_deleted_by_user_id_users", "import_sources", type_="foreignkey")
    op.drop_index(op.f("ix_import_sources_deleted_by_user_id"), table_name="import_sources")
    op.drop_index(op.f("ix_import_sources_deleted_at"), table_name="import_sources")
    op.drop_column("import_sources", "deletion_reason")
    op.drop_column("import_sources", "deleted_by_user_id")
    op.drop_column("import_sources", "deleted_at")

    op.drop_index(op.f("ix_import_batches_created_by_user_id"), table_name="import_batches")
    op.drop_table("import_batches")
