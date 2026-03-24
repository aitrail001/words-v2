"""Add translation usage note and examples.

Revision ID: 018
Revises: 017
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "translations",
        sa.Column("usage_note", sa.Text(), nullable=True),
        schema="lexicon",
    )
    op.add_column(
        "translations",
        sa.Column("examples", sa.JSON(), nullable=True),
        schema="lexicon",
    )


def downgrade() -> None:
    op.drop_column("translations", "examples", schema="lexicon")
    op.drop_column("translations", "usage_note", schema="lexicon")
