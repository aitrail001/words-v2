"""Add normalized word form rows

Revision ID: 021
Revises: 020
Create Date: 2026-03-26
"""

from collections.abc import Mapping, Sequence
from typing import Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def upgrade() -> None:
    op.create_table(
        "word_forms",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("form_kind", sa.String(length=50), nullable=False),
        sa.Column("form_slot", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["word_id"], ["lexicon.words.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word_id", "form_kind", "form_slot", "order_index", name="uq_word_forms_word_kind_slot_order"),
        schema="lexicon",
    )
    op.create_index(
        "ix_lexicon_word_forms_word_id",
        "word_forms",
        ["word_id"],
        unique=False,
        schema="lexicon",
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, word_forms
            FROM lexicon.words
            WHERE word_forms IS NOT NULL
            """
        )
    ).mappings()

    insert_table = sa.table(
        "word_forms",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("word_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("form_kind", sa.String(length=50), nullable=False),
        sa.Column("form_slot", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        schema="lexicon",
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        forms = row.get("word_forms")
        if not isinstance(forms, Mapping):
            continue

        verb_forms = forms.get("verb_forms")
        if isinstance(verb_forms, Mapping):
            for index, slot in enumerate(("base", "past", "gerund", "past_participle", "third_person_singular")):
                value = _clean_text(verb_forms.get(slot))
                if value is None:
                    continue
                insert_rows.append(
                    {
                        "id": uuid4(),
                        "word_id": row["id"],
                        "form_kind": "verb",
                        "form_slot": slot,
                        "value": value,
                        "order_index": index,
                    }
                )

        plural_forms = forms.get("plural_forms")
        if isinstance(plural_forms, list):
            for index, item in enumerate(plural_forms):
                value = _clean_text(item)
                if value is None:
                    continue
                insert_rows.append(
                    {
                        "id": uuid4(),
                        "word_id": row["id"],
                        "form_kind": "plural",
                        "form_slot": "",
                        "value": value,
                        "order_index": index,
                    }
                )

        derivations = forms.get("derivations")
        if isinstance(derivations, list):
            for index, item in enumerate(derivations):
                value = _clean_text(item)
                if value is None:
                    continue
                insert_rows.append(
                    {
                        "id": uuid4(),
                        "word_id": row["id"],
                        "form_kind": "derivation",
                        "form_slot": "",
                        "value": value,
                        "order_index": index,
                    }
                )

        comparative = _clean_text(forms.get("comparative"))
        if comparative is not None:
            insert_rows.append(
                {
                    "id": uuid4(),
                    "word_id": row["id"],
                    "form_kind": "comparative",
                    "form_slot": "",
                    "value": comparative,
                    "order_index": 0,
                }
            )

        superlative = _clean_text(forms.get("superlative"))
        if superlative is not None:
            insert_rows.append(
                {
                    "id": uuid4(),
                    "word_id": row["id"],
                    "form_kind": "superlative",
                    "form_slot": "",
                    "value": superlative,
                    "order_index": 0,
                }
            )

    if insert_rows:
        op.bulk_insert(insert_table, insert_rows)


def downgrade() -> None:
    op.drop_index("ix_lexicon_word_forms_word_id", table_name="word_forms", schema="lexicon")
    op.drop_table("word_forms", schema="lexicon")
