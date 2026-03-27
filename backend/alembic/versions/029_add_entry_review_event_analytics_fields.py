"""Add entry review event analytics fields

Revision ID: 029
Revises: 028
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entry_review_events",
        sa.Column("prompt_family", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "entry_review_events",
        sa.Column("response_input_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "entry_review_events",
        sa.Column("response_value", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "entry_review_events",
        sa.Column(
            "used_audio_placeholder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("entry_review_events", "used_audio_placeholder")
    op.drop_column("entry_review_events", "response_value")
    op.drop_column("entry_review_events", "response_input_mode")
    op.drop_column("entry_review_events", "prompt_family")
