"""Add grouped word phonetics JSON field

Revision ID: 013
Revises: 012
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("words", sa.Column("phonetics", sa.JSON(), nullable=True), schema="lexicon")


def downgrade() -> None:
    op.drop_column("words", "phonetics", schema="lexicon")
