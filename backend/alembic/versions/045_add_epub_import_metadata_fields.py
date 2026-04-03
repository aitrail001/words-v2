"""add epub import metadata fields

Revision ID: 045
Revises: 044
Create Date: 2026-04-03 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_sources", sa.Column("published_year", sa.Integer(), nullable=True))
    op.add_column("import_sources", sa.Column("isbn", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("import_sources", "isbn")
    op.drop_column("import_sources", "published_year")
