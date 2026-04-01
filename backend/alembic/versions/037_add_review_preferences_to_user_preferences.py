"""Add review preferences to user_preferences

Revision ID: 037
Revises: 036
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("review_depth_preset", sa.String(length=16), nullable=False, server_default="balanced"),
    )
    op.add_column(
        "user_preferences",
        sa.Column("enable_confidence_check", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "user_preferences",
        sa.Column("enable_word_spelling", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "user_preferences",
        sa.Column("enable_audio_spelling", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "user_preferences",
        sa.Column("show_pictures_in_questions", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_user_preferences_review_depth",
        "user_preferences",
        "review_depth_preset IN ('gentle', 'balanced', 'deep')",
    )
    op.alter_column("user_preferences", "review_depth_preset", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_user_preferences_review_depth", "user_preferences", type_="check")
    op.drop_column("user_preferences", "show_pictures_in_questions")
    op.drop_column("user_preferences", "enable_audio_spelling")
    op.drop_column("user_preferences", "enable_word_spelling")
    op.drop_column("user_preferences", "enable_confidence_check")
    op.drop_column("user_preferences", "review_depth_preset")

