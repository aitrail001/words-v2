"""Add normalized meaning metadata rows

Revision ID: 023
Revises: 022
Create Date: 2026-03-26
"""

from collections.abc import Sequence
from typing import Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def upgrade() -> None:
    op.create_table(
        "meaning_metadata",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("meaning_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata_kind", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["meaning_id"], ["lexicon.meanings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meaning_id", "metadata_kind", "order_index", name="uq_meaning_metadata_kind_order"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_meaning_metadata_meaning_id",
        "meaning_metadata",
        ["meaning_id"],
        unique=False,
        schema="lexicon",
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, secondary_domains, grammar_patterns
            FROM lexicon.meanings
            WHERE secondary_domains IS NOT NULL OR grammar_patterns IS NOT NULL
            """
        )
    ).mappings()

    insert_table = sa.table(
        "meaning_metadata",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("meaning_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata_kind", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        schema="lexicon",
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        secondary_domains = row.get("secondary_domains")
        if isinstance(secondary_domains, list):
            for index, item in enumerate(secondary_domains):
                value = _clean_text(item)
                if value is None:
                    continue
                insert_rows.append(
                    {
                        "id": uuid4(),
                        "meaning_id": row["id"],
                        "metadata_kind": "secondary_domain",
                        "value": value,
                        "order_index": index,
                    }
                )

        grammar_patterns = row.get("grammar_patterns")
        if isinstance(grammar_patterns, list):
            for index, item in enumerate(grammar_patterns):
                value = _clean_text(item)
                if value is None:
                    continue
                insert_rows.append(
                    {
                        "id": uuid4(),
                        "meaning_id": row["id"],
                        "metadata_kind": "grammar_pattern",
                        "value": value,
                        "order_index": index,
                    }
                )

    if insert_rows:
        op.bulk_insert(insert_table, insert_rows)


def downgrade() -> None:
    op.drop_index("ix_lexicon_meaning_metadata_meaning_id", table_name="meaning_metadata", schema="lexicon")
    op.drop_table("meaning_metadata", schema="lexicon")
