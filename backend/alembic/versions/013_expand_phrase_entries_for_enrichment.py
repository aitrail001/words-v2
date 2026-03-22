"""Expand phrase entries for rich enrichment payloads

Revision ID: 013
Revises: 012
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("phrase_entries", sa.Column("compiled_payload", JSONB(), nullable=True), schema="lexicon")
    op.add_column("phrase_entries", sa.Column("seed_metadata", JSONB(), nullable=True), schema="lexicon")
    op.add_column("phrase_entries", sa.Column("confidence_score", sa.Float(), nullable=True), schema="lexicon")
    op.add_column("phrase_entries", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True), schema="lexicon")


def downgrade() -> None:
    op.drop_column("phrase_entries", "generated_at", schema="lexicon")
    op.drop_column("phrase_entries", "confidence_score", schema="lexicon")
    op.drop_column("phrase_entries", "seed_metadata", schema="lexicon")
    op.drop_column("phrase_entries", "compiled_payload", schema="lexicon")
