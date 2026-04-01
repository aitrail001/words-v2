"""add last submission prompt id to entry review states

Revision ID: 042
Revises: 041
Create Date: 2026-04-02 09:18:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entry_review_states",
        sa.Column("last_submission_prompt_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entry_review_states", "last_submission_prompt_id")
