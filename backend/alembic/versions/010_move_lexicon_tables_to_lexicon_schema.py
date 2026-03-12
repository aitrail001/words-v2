"""Move lexicon tables into dedicated schema

Revision ID: 010
Revises: 009
Create Date: 2026-03-12
"""
from typing import Sequence, Union

from alembic import op


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEXICON_TABLES = [
    "words",
    "meanings",
    "translations",
    "meaning_examples",
    "word_relations",
    "lexicon_enrichment_jobs",
    "lexicon_enrichment_runs",
    "lexicon_review_batches",
    "lexicon_review_items",
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS lexicon")
    for table_name in LEXICON_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS public.{table_name} SET SCHEMA lexicon')


def downgrade() -> None:
    for table_name in reversed(LEXICON_TABLES):
        op.execute(f'ALTER TABLE IF EXISTS lexicon.{table_name} SET SCHEMA public')
    op.execute("DROP SCHEMA IF EXISTS lexicon")
