"""Add normalized word part-of-speech rows

Revision ID: 025
Revises: 024
Create Date: 2026-03-27
"""

from collections.abc import Sequence
from typing import Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def upgrade() -> None:
    op.create_table(
        "word_part_of_speech",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.String(length=50), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["word_id"], ["lexicon.words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "order_index", name="uq_word_part_of_speech_word_order"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_word_part_of_speech_word_id",
        "word_part_of_speech",
        ["word_id"],
        unique=False,
        schema="lexicon",
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, learner_part_of_speech
            FROM lexicon.words
            WHERE learner_part_of_speech IS NOT NULL
            """
        )
    ).mappings()

    insert_table = sa.table(
        "word_part_of_speech",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.String(length=50), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        schema="lexicon",
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        raw_values = row.get("learner_part_of_speech")
        if not isinstance(raw_values, list):
            continue
        for index, item in enumerate(raw_values):
            value = _clean_text(item)
            if value is None:
                continue
            insert_rows.append(
                {
                    "id": uuid4(),
                    "word_id": row["id"],
                    "value": value,
                    "order_index": index,
                }
            )

    if insert_rows:
        op.bulk_insert(insert_table, insert_rows)


def downgrade() -> None:
    op.drop_index("ix_lexicon_word_part_of_speech_word_id", table_name="word_part_of_speech", schema="lexicon")
    op.drop_table("word_part_of_speech", schema="lexicon")
