"""add import job entry type counts

Revision ID: 049_job_entry_counts
Revises: 048_add_admin_import_cache_management_tables
Create Date: 2026-04-04 11:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "049_job_entry_counts"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("word_entry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("phrase_entry_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        """
        UPDATE import_jobs
        SET word_entry_count = COALESCE(type_counts.word_count, 0),
            phrase_entry_count = COALESCE(type_counts.phrase_count, 0)
        FROM (
            SELECT
                import_source_id,
                SUM(CASE WHEN entry_type = 'word' THEN 1 ELSE 0 END)::int AS word_count,
                SUM(CASE WHEN entry_type = 'phrase' THEN 1 ELSE 0 END)::int AS phrase_count
            FROM import_source_entries
            GROUP BY import_source_id
        ) AS type_counts
        WHERE import_jobs.import_source_id = type_counts.import_source_id
        """
    )
    op.alter_column("import_jobs", "word_entry_count", server_default=None)
    op.alter_column("import_jobs", "phrase_entry_count", server_default=None)


def downgrade() -> None:
    op.drop_column("import_jobs", "phrase_entry_count")
    op.drop_column("import_jobs", "word_entry_count")
