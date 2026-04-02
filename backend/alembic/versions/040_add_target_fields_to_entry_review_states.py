"""add target fields to entry review states

Revision ID: 040
Revises: 039
Create Date: 2026-04-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entry_review_states", sa.Column("target_type", sa.String(length=32), nullable=True))
    op.add_column("entry_review_states", sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        "ix_entry_review_states_target_id",
        "entry_review_states",
        ["target_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_entry_review_state_user_entry",
        "entry_review_states",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_entry_review_state_user_target",
        "entry_review_states",
        ["user_id", "target_type", "target_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_entry_review_state_user_target",
        "entry_review_states",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_entry_review_state_user_entry",
        "entry_review_states",
        ["user_id", "entry_type", "entry_id"],
    )
    op.drop_index("ix_entry_review_states_target_id", table_name="entry_review_states")
    op.drop_column("entry_review_states", "target_id")
    op.drop_column("entry_review_states", "target_type")
