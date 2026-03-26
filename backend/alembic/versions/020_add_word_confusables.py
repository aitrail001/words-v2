"""Add normalized word confusable rows

Revision ID: 020
Revises: 019
Create Date: 2026-03-26
"""

from collections.abc import Mapping, Sequence
from typing import Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def upgrade() -> None:
    op.create_table(
        "word_confusables",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("confusable_word", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["word_id"], ["lexicon.words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "order_index", name="uq_word_confusables_word_order"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_word_confusables_word_id",
        "word_confusables",
        ["word_id"],
        unique=False,
        schema="lexicon",
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, confusable_words
            FROM lexicon.words
            WHERE confusable_words IS NOT NULL
            """
        )
    ).mappings()

    insert_table = sa.table(
        "word_confusables",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("confusable_word", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        schema="lexicon",
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        raw_items = row.get("confusable_words")
        if not isinstance(raw_items, list):
            continue
        output_index = 0
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            confusable_word = _clean_text(item.get("word"))
            if confusable_word is None:
                continue
            insert_rows.append(
                {
                    "id": uuid4(),
                    "word_id": row["id"],
                    "confusable_word": confusable_word,
                    "note": _clean_text(item.get("note")),
                    "order_index": output_index,
                }
            )
            output_index += 1

    if insert_rows:
        op.bulk_insert(insert_table, insert_rows)


def downgrade() -> None:
    op.drop_index("ix_lexicon_word_confusables_word_id", table_name="word_confusables", schema="lexicon")
    op.drop_table("word_confusables", schema="lexicon")
