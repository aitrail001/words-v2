"""add epub import publisher field

Revision ID: 046
Revises: 045
Create Date: 2026-04-03 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_sources", sa.Column("publisher", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("import_sources", "publisher")
