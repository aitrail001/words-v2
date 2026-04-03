"""add import job progress fields

Revision ID: 047
Revises: 046
Create Date: 2026-04-03 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("progress_stage", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "import_jobs",
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_jobs",
        sa.Column("progress_completed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_jobs",
        sa.Column("progress_current_label", sa.Text(), nullable=True),
    )
    op.alter_column("import_jobs", "progress_total", server_default=None)
    op.alter_column("import_jobs", "progress_completed", server_default=None)


def downgrade() -> None:
    op.drop_column("import_jobs", "progress_current_label")
    op.drop_column("import_jobs", "progress_completed")
    op.drop_column("import_jobs", "progress_total")
    op.drop_column("import_jobs", "progress_stage")
