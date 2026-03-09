"""Add learner-facing lexicon fields

Revision ID: 009
Revises: 008
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("words", sa.Column("cefr_level", sa.String(length=10), nullable=True))
    op.add_column("words", sa.Column("learner_part_of_speech", sa.JSON(), nullable=True))
    op.add_column("words", sa.Column("confusable_words", sa.JSON(), nullable=True))
    op.add_column("words", sa.Column("learner_generated_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("meanings", sa.Column("wn_synset_id", sa.String(length=255), nullable=True))
    op.add_column("meanings", sa.Column("primary_domain", sa.String(length=64), nullable=True))
    op.add_column("meanings", sa.Column("secondary_domains", sa.JSON(), nullable=True))
    op.add_column("meanings", sa.Column("register_label", sa.String(length=32), nullable=True))
    op.add_column("meanings", sa.Column("grammar_patterns", sa.JSON(), nullable=True))
    op.add_column("meanings", sa.Column("usage_note", sa.Text(), nullable=True))
    op.add_column("meanings", sa.Column("learner_generated_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("meaning_examples", sa.Column("difficulty", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("meaning_examples", "difficulty")

    op.drop_column("meanings", "learner_generated_at")
    op.drop_column("meanings", "usage_note")
    op.drop_column("meanings", "grammar_patterns")
    op.drop_column("meanings", "register_label")
    op.drop_column("meanings", "secondary_domains")
    op.drop_column("meanings", "primary_domain")
    op.drop_column("meanings", "wn_synset_id")

    op.drop_column("words", "learner_generated_at")
    op.drop_column("words", "confusable_words")
    op.drop_column("words", "learner_part_of_speech")
    op.drop_column("words", "cefr_level")
