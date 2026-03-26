"""Add normalized translation example rows

Revision ID: 022
Revises: 021
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def upgrade() -> None:
    op.create_table(
        "translation_examples",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["translation_id"], ["lexicon.translations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("translation_id", "order_index", name="uq_translation_examples_translation_order"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_translation_examples_translation_id",
        "translation_examples",
        ["translation_id"],
        unique=False,
        schema="lexicon",
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, examples
            FROM lexicon.translations
            WHERE examples IS NOT NULL
            """
        )
    ).mappings()

    insert_table = sa.table(
        "translation_examples",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("translation_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        schema="lexicon",
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        raw_examples = row.get("examples")
        if not isinstance(raw_examples, list):
            continue
        for index, item in enumerate(raw_examples):
            text = _clean_text(item)
            if text is None:
                continue
            insert_rows.append(
                {
                    "id": uuid4(),
                    "translation_id": row["id"],
                    "text": text,
                    "order_index": index,
                }
            )

    if insert_rows:
        op.bulk_insert(insert_table, insert_rows)


def downgrade() -> None:
    op.drop_index("ix_lexicon_translation_examples_translation_id", table_name="translation_examples", schema="lexicon")
    op.drop_table("translation_examples", schema="lexicon")
