"""Add lexicon import provenance fields

Revision ID: 006
Revises: 005
Create Date: 2026-03-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("words", sa.Column("source_type", sa.String(length=50), nullable=True))
    op.add_column("words", sa.Column("source_reference", sa.String(length=255), nullable=True))
    op.add_column("meanings", sa.Column("source_reference", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("meanings", "source_reference")
    op.drop_column("words", "source_reference")
    op.drop_column("words", "source_type")
