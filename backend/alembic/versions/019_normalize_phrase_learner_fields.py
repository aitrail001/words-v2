"""Normalize phrase learner fields into structured tables

Revision ID: 019
Revises: 018
Create Date: 2026-03-26
"""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_TRANSLATION_LOCALES = ("ar", "es", "ja", "pt-BR", "zh-Hans")
SUPPORTED_LOCALE_ORDER = {locale: index for index, locale in enumerate(BACKFILL_TRANSLATION_LOCALES)}


def _clean_text(value):
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    return None


def _normalize_string_list(values):
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if isinstance(item, str) and str(item).strip()]


def _coerce_timestamp(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if text:
            return datetime.fromisoformat(text)
    return datetime.now(timezone.utc)


def _locale_sort_key(locale: str) -> tuple[int, str]:
    return (SUPPORTED_LOCALE_ORDER.get(locale, len(SUPPORTED_LOCALE_ORDER)), locale)


def _locale_payload_items(translations: Mapping[str, object]) -> list[tuple[str, dict[str, object]]]:
    items: list[tuple[str, dict[str, object]]] = []
    for locale, payload in translations.items():
        if isinstance(locale, str) and isinstance(payload, dict):
            items.append((locale, payload))
    return sorted(items, key=lambda item: _locale_sort_key(item[0]))


def _example_candidate_score(candidate: Mapping[str, object]) -> tuple[int, int, int]:
    locale_translations = candidate.get("locale_translations") if isinstance(candidate.get("locale_translations"), dict) else {}
    non_blank_locale_count = sum(1 for value in locale_translations.values() if value is not None)
    difficulty_score = 1 if _clean_text(candidate.get("difficulty")) else 0
    order_index = int(candidate.get("order_index", 0))
    return (non_blank_locale_count, difficulty_score, -order_index)


def _locale_translation_score(candidate: Mapping[str, object], locale: str) -> tuple[int, int, int, int]:
    locale_translations = candidate.get("locale_translations") if isinstance(candidate.get("locale_translations"), dict) else {}
    translation = locale_translations.get(locale)
    translation_score = 1 if translation is not None else 0
    non_blank_locale_count = sum(1 for value in locale_translations.values() if value is not None)
    difficulty_score = 1 if _clean_text(candidate.get("difficulty")) else 0
    order_index = int(candidate.get("order_index", 0))
    return (translation_score, non_blank_locale_count, difficulty_score, -order_index)


def _build_phrase_backfill_rows(
    phrase_row: Mapping[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    payload = phrase_row.get("compiled_payload") if isinstance(phrase_row.get("compiled_payload"), dict) else {}
    senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    source_timestamp = _coerce_timestamp(phrase_row.get("generated_at") or phrase_row.get("created_at"))
    phrase_sense_rows: list[dict[str, object]] = []
    phrase_sense_localization_rows: list[dict[str, object]] = []
    phrase_sense_example_rows: list[dict[str, object]] = []
    phrase_sense_example_localization_rows: list[dict[str, object]] = []

    for sense_order, raw_sense in enumerate(senses):
        sense = raw_sense if isinstance(raw_sense, dict) else {}
        definition = _clean_text(sense.get("definition"))
        if definition is None:
            continue

        usage_note = _clean_text(sense.get("usage_note"))
        translations = sense.get("translations") if isinstance(sense.get("translations"), dict) else {}
        phrase_sense_id = uuid4()
        phrase_sense_rows.append(
            {
                "id": phrase_sense_id,
                "phrase_entry_id": phrase_row["id"],
                "definition": definition,
                "usage_note": usage_note,
                "part_of_speech": _clean_text(sense.get("pos") if isinstance(sense.get("pos"), str) else sense.get("part_of_speech")),
                "register": _clean_text(sense.get("register") if isinstance(sense.get("register"), str) else None),
                "primary_domain": _clean_text(sense.get("primary_domain") if isinstance(sense.get("primary_domain"), str) else None),
                "secondary_domains": _normalize_string_list(sense.get("secondary_domains")),
                "grammar_patterns": _normalize_string_list(sense.get("grammar_patterns")),
                "synonyms": _normalize_string_list(sense.get("synonyms")),
                "antonyms": _normalize_string_list(sense.get("antonyms")),
                "collocations": _normalize_string_list(sense.get("collocations")),
                "order_index": sense_order,
                "created_at": source_timestamp,
            }
        )

        for locale, locale_payload in _locale_payload_items(translations):
            localized_definition = _clean_text(locale_payload.get("definition"))
            localized_usage_note = _clean_text(locale_payload.get("usage_note"))
            phrase_sense_localization_rows.append(
                {
                    "id": uuid4(),
                    "phrase_sense_id": phrase_sense_id,
                    "locale": locale,
                    "localized_definition": localized_definition,
                    "localized_usage_note": localized_usage_note,
                    "created_at": source_timestamp,
                }
            )

        examples = sense.get("examples") if isinstance(sense.get("examples"), list) else []
        example_groups: dict[str, list[dict[str, object]]] = {}
        for example_order, raw_example in enumerate(examples):
            example = raw_example if isinstance(raw_example, dict) else {}
            sentence = _clean_text(example.get("sentence"))
            if sentence is None:
                continue
            normalized_sentence = sentence.lower()
            candidate = {
                "sentence": sentence,
                "difficulty": _clean_text(example.get("difficulty")),
                "order_index": example_order,
                "locale_translations": {},
            }
            for locale, locale_payload in _locale_payload_items(translations):
                localized_examples = locale_payload.get("examples") if isinstance(locale_payload.get("examples"), list) else []
                translation = None
                if example_order < len(localized_examples):
                    translation = _clean_text(localized_examples[example_order])
                candidate["locale_translations"][locale] = translation
            example_groups.setdefault(normalized_sentence, []).append(candidate)

        grouped_examples = sorted(
            example_groups.items(),
            key=lambda item: min(candidate["order_index"] for candidate in item[1]),
        )
        for output_order, (_normalized_sentence, candidates) in enumerate(grouped_examples):
            best_candidate = max(candidates, key=_example_candidate_score)
            phrase_sense_example_id = uuid4()
            phrase_sense_example_rows.append(
                {
                    "id": phrase_sense_example_id,
                    "phrase_sense_id": phrase_sense_id,
                    "sentence": best_candidate["sentence"],
                    "difficulty": best_candidate["difficulty"],
                    "order_index": output_order,
                    "source": _clean_text(phrase_row.get("source_type")),
                    "created_at": source_timestamp,
                }
            )

            locale_names = set()
            for candidate in candidates:
                locale_translations = candidate.get("locale_translations") if isinstance(candidate.get("locale_translations"), dict) else {}
                locale_names.update(locale_translations.keys())
            for locale in sorted(locale_names, key=_locale_sort_key):
                best_locale_candidate = max(candidates, key=lambda candidate: _locale_translation_score(candidate, locale))
                locale_translations = best_locale_candidate.get("locale_translations") if isinstance(best_locale_candidate.get("locale_translations"), dict) else {}
                phrase_sense_example_localization_rows.append(
                    {
                        "id": uuid4(),
                        "phrase_sense_example_id": phrase_sense_example_id,
                        "locale": locale,
                        "translation": locale_translations.get(locale),
                        "created_at": source_timestamp,
                    }
                )

    return (
        phrase_sense_rows,
        phrase_sense_localization_rows,
        phrase_sense_example_rows,
        phrase_sense_example_localization_rows,
    )


def phrase_senses_insert_table() -> sa.Table:
    return sa.table(
        "phrase_senses",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_entry_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("usage_note", sa.Text(), nullable=True),
        sa.Column("part_of_speech", sa.String(length=50), nullable=True),
        sa.Column("register", sa.String(length=32), nullable=True),
        sa.Column("primary_domain", sa.String(length=64), nullable=True),
        sa.Column("secondary_domains", sa.JSON(), nullable=True),
        sa.Column("grammar_patterns", sa.JSON(), nullable=True),
        sa.Column("synonyms", sa.JSON(), nullable=True),
        sa.Column("antonyms", sa.JSON(), nullable=True),
        sa.Column("collocations", sa.JSON(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="lexicon",
    )


def phrase_sense_localizations_insert_table() -> sa.Table:
    return sa.table(
        "phrase_sense_localizations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_sense_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("localized_definition", sa.Text(), nullable=True),
        sa.Column("localized_usage_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="lexicon",
    )


def phrase_sense_examples_insert_table() -> sa.Table:
    return sa.table(
        "phrase_sense_examples",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_sense_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=10), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="lexicon",
    )


def phrase_sense_example_localizations_insert_table() -> sa.Table:
    return sa.table(
        "phrase_sense_example_localizations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("phrase_sense_example_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="lexicon",
    )


def backfill_phrase_rows(
    connection,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    phrase_entries = sa.table(
        "phrase_entries",
        sa.Column("id", sa.UUID(as_uuid=True)),
        sa.Column("compiled_payload", sa.JSON()),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("source_type", sa.String(length=50)),
        schema="lexicon",
    )
    phrase_rows = connection.execute(
        sa.select(
            phrase_entries.c.id,
            phrase_entries.c.compiled_payload,
            phrase_entries.c.generated_at,
            phrase_entries.c.created_at,
            phrase_entries.c.source_type,
        )
    ).mappings().all()

    phrase_sense_rows: list[dict[str, object]] = []
    phrase_sense_localization_rows: list[dict[str, object]] = []
    phrase_sense_example_rows: list[dict[str, object]] = []
    phrase_sense_example_localization_rows: list[dict[str, object]] = []
    for phrase_row in phrase_rows:
        sense_rows, sense_localization_rows, example_rows, example_localization_rows = _build_phrase_backfill_rows(phrase_row)
        phrase_sense_rows.extend(sense_rows)
        phrase_sense_localization_rows.extend(sense_localization_rows)
        phrase_sense_example_rows.extend(example_rows)
        phrase_sense_example_localization_rows.extend(example_localization_rows)
    return (
        phrase_sense_rows,
        phrase_sense_localization_rows,
        phrase_sense_example_rows,
        phrase_sense_example_localization_rows,
    )


def upgrade() -> None:
    phrase_senses_insert = phrase_senses_insert_table()
    phrase_sense_localizations_insert = phrase_sense_localizations_insert_table()
    phrase_sense_examples_insert = phrase_sense_examples_insert_table()
    phrase_sense_example_localizations_insert = phrase_sense_example_localizations_insert_table()

    op.create_table(
        "phrase_senses",
        *phrase_senses_insert.columns,
        sa.ForeignKeyConstraint(["phrase_entry_id"], ["lexicon.phrase_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phrase_entry_id", "order_index", name="uq_phrase_sense_entry_order"),
        schema="lexicon",
    )
    op.create_index("ix_phrase_senses_phrase_entry_id", "phrase_senses", ["phrase_entry_id"], schema="lexicon")

    op.create_table(
        "phrase_sense_localizations",
        *phrase_sense_localizations_insert.columns,
        sa.ForeignKeyConstraint(["phrase_sense_id"], ["lexicon.phrase_senses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phrase_sense_id", "locale", name="uq_phrase_sense_localization_sense_locale"),
        schema="lexicon",
    )
    op.create_index(
        "ix_phrase_sense_localizations_phrase_sense_id",
        "phrase_sense_localizations",
        ["phrase_sense_id"],
        schema="lexicon",
    )

    op.create_table(
        "phrase_sense_examples",
        *phrase_sense_examples_insert.columns,
        sa.ForeignKeyConstraint(["phrase_sense_id"], ["lexicon.phrase_senses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phrase_sense_id", "sentence", name="uq_phrase_sense_example_sense_sentence"),
        schema="lexicon",
    )
    op.create_index(
        "ix_phrase_sense_examples_phrase_sense_id",
        "phrase_sense_examples",
        ["phrase_sense_id"],
        schema="lexicon",
    )

    op.create_table(
        "phrase_sense_example_localizations",
        *phrase_sense_example_localizations_insert.columns,
        sa.ForeignKeyConstraint(["phrase_sense_example_id"], ["lexicon.phrase_sense_examples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "phrase_sense_example_id",
            "locale",
            name="uq_phrase_sense_example_localization_example_locale",
        ),
        schema="lexicon",
    )
    op.create_index(
        "ix_phrase_sense_example_localizations_phrase_sense_example_id",
        "phrase_sense_example_localizations",
        ["phrase_sense_example_id"],
        schema="lexicon",
    )

    connection = op.get_bind()
    (
        phrase_sense_rows,
        phrase_sense_localization_rows,
        phrase_sense_example_rows,
        phrase_sense_example_localization_rows,
    ) = backfill_phrase_rows(connection)

    if phrase_sense_rows:
        op.bulk_insert(phrase_senses_insert, phrase_sense_rows)
    if phrase_sense_localization_rows:
        op.bulk_insert(phrase_sense_localizations_insert, phrase_sense_localization_rows)
    if phrase_sense_example_rows:
        op.bulk_insert(phrase_sense_examples_insert, phrase_sense_example_rows)
    if phrase_sense_example_localization_rows:
        op.bulk_insert(phrase_sense_example_localizations_insert, phrase_sense_example_localization_rows)


def downgrade() -> None:
    op.drop_index(
        "ix_phrase_sense_example_localizations_phrase_sense_example_id",
        table_name="phrase_sense_example_localizations",
        schema="lexicon",
    )
    op.drop_table("phrase_sense_example_localizations", schema="lexicon")
    op.drop_index("ix_phrase_sense_examples_phrase_sense_id", table_name="phrase_sense_examples", schema="lexicon")
    op.drop_table("phrase_sense_examples", schema="lexicon")
    op.drop_index(
        "ix_phrase_sense_localizations_phrase_sense_id",
        table_name="phrase_sense_localizations",
        schema="lexicon",
    )
    op.drop_table("phrase_sense_localizations", schema="lexicon")
    op.drop_index("ix_phrase_senses_phrase_entry_id", table_name="phrase_senses", schema="lexicon")
    op.drop_table("phrase_senses", schema="lexicon")
