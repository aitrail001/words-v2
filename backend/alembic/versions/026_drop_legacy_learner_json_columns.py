"""drop legacy learner json columns

Revision ID: 026
Revises: 025_add_word_part_of_speech
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("translations", "examples", schema="lexicon")
    op.drop_column("meanings", "grammar_patterns", schema="lexicon")
    op.drop_column("meanings", "secondary_domains", schema="lexicon")
    op.drop_column("words", "word_forms", schema="lexicon")
    op.drop_column("words", "confusable_words", schema="lexicon")
    op.drop_column("words", "learner_part_of_speech", schema="lexicon")


def downgrade() -> None:
    op.add_column("words", sa.Column("learner_part_of_speech", sa.JSON(), nullable=True), schema="lexicon")
    op.add_column("words", sa.Column("confusable_words", sa.JSON(), nullable=True), schema="lexicon")
    op.add_column("words", sa.Column("word_forms", sa.JSON(), nullable=True), schema="lexicon")
    op.add_column("meanings", sa.Column("secondary_domains", sa.JSON(), nullable=True), schema="lexicon")
    op.add_column("meanings", sa.Column("grammar_patterns", sa.JSON(), nullable=True), schema="lexicon")
    op.add_column("translations", sa.Column("examples", sa.JSON(), nullable=True), schema="lexicon")
