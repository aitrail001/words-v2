"""Add trigram indexes for learner search

Revision ID: 024
Revises: 023
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union

from alembic import op


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lexicon_words_word_trgm
        ON lexicon.words
        USING gin (word gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lexicon_phrase_entries_normalized_form_trgm
        ON lexicon.phrase_entries
        USING gin (normalized_form gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lexicon_phrase_entries_phrase_text_trgm
        ON lexicon.phrase_entries
        USING gin (phrase_text gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS lexicon.ix_lexicon_phrase_entries_phrase_text_trgm")
    op.execute("DROP INDEX IF EXISTS lexicon.ix_lexicon_phrase_entries_normalized_form_trgm")
    op.execute("DROP INDEX IF EXISTS lexicon.ix_lexicon_words_word_trgm")
