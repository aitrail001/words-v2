from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
import json

from tools.lexicon.import_db import _ensure_backend_path

SCHEMA_VERSION = "1.1.0"


def _created_iso(value: object) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _sense_id_for_meaning(meaning: Any, row_source_reference: str | None, index: int) -> str:
    meaning_source_reference = getattr(meaning, "source_reference", None)
    if (
        row_source_reference
        and isinstance(meaning_source_reference, str)
        and meaning_source_reference.startswith(f"{row_source_reference}:")
    ):
        suffix = meaning_source_reference[len(row_source_reference) + 1 :].strip()
        if suffix:
            return suffix
    wn_synset_id = getattr(meaning, "wn_synset_id", None)
    if isinstance(wn_synset_id, str) and wn_synset_id.strip():
        return wn_synset_id.strip()
    return f"db-sense-{index:03d}-{getattr(meaning, 'id')}"


def _serialize_examples(examples: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for example in sorted(
        examples,
        key=lambda item: (
            getattr(item, "order_index", 0),
            str(getattr(item, "id", "")),
        ),
    ):
        sentence = str(getattr(example, "sentence", "") or "").strip()
        if not sentence:
            continue
        payload: dict[str, Any] = {"sentence": sentence}
        difficulty = getattr(example, "difficulty", None)
        if difficulty:
            payload["difficulty"] = difficulty
        rows.append(payload)
    return rows


def _normalize_translation_examples(translation: Any) -> list[str]:
    example_entries = getattr(translation, "example_entries", None)
    if not isinstance(example_entries, list):
        return []
    return [
        str(getattr(item, "text", "") or "").strip()
        for item in sorted(
            example_entries,
            key=lambda item: (
                getattr(item, "order_index", 0),
                str(getattr(item, "id", "")),
            ),
        )
        if str(getattr(item, "text", "") or "").strip()
    ]


def _serialize_translations(translations: Iterable[Any]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for translation in sorted(
        translations,
        key=lambda item: (
            str(getattr(item, "language", "")),
            str(getattr(item, "id", "")),
        ),
    ):
        locale = str(getattr(translation, "language", "") or "").strip()
        text = str(getattr(translation, "translation", "") or "").strip()
        if not locale or not text:
            continue
        payload[locale] = {"definition": text}
        usage_note = getattr(translation, "usage_note", None)
        if isinstance(usage_note, str) and usage_note.strip():
            payload[locale]["usage_note"] = usage_note.strip()
        examples = _normalize_translation_examples(translation)
        if examples:
            payload[locale]["examples"] = examples
    return payload


def _serialize_relations(relations: Iterable[Any]) -> dict[str, list[str]]:
    buckets = {
        "synonyms": [],
        "antonyms": [],
        "collocations": [],
    }
    field_map = {
        "synonym": "synonyms",
        "antonym": "antonyms",
        "collocation": "collocations",
    }
    for relation in sorted(
        relations,
        key=lambda item: (
            str(getattr(item, "relation_type", "")),
            str(getattr(item, "related_word", "")),
            str(getattr(item, "id", "")),
        ),
    ):
        relation_type = str(getattr(relation, "relation_type", "") or "").strip()
        related_word = str(getattr(relation, "related_word", "") or "").strip()
        field = field_map.get(relation_type)
        if not field or not related_word:
            continue
        if related_word not in buckets[field]:
            buckets[field].append(related_word)
    return buckets


def _normalize_word_part_of_speech(word: Any) -> list[str]:
    part_of_speech_entries = getattr(word, "part_of_speech_entries", None)
    if not isinstance(part_of_speech_entries, list):
        return []
    return [
        str(getattr(item, "value", "") or "").strip()
        for item in sorted(
            part_of_speech_entries,
            key=lambda item: (
                getattr(item, "order_index", 0),
                str(getattr(item, "id", "")),
            ),
        )
        if str(getattr(item, "value", "") or "").strip()
    ]


def _normalize_confusable_words(word: Any) -> list[dict[str, str | None]]:
    confusable_entries = getattr(word, "confusable_entries", None)
    if not isinstance(confusable_entries, list):
        return []
    rows: list[dict[str, str | None]] = []
    for item in sorted(
        confusable_entries,
        key=lambda entry: (
            getattr(entry, "order_index", 0),
            str(getattr(entry, "id", "")),
        ),
    ):
        confusable_word = str(getattr(item, "confusable_word", "") or "").strip()
        if not confusable_word:
            continue
        note = str(getattr(item, "note", "") or "").strip() or None
        rows.append({"word": confusable_word, "note": note})
    return rows


def _normalize_word_forms(word: Any) -> dict[str, Any]:
    form_entries = getattr(word, "form_entries", None)
    payload: dict[str, Any] = {
        "plural_forms": [],
        "verb_forms": {},
        "comparative": None,
        "superlative": None,
        "derivations": [],
    }
    if not isinstance(form_entries, list):
        return payload
    for item in sorted(
        form_entries,
        key=lambda entry: (
            getattr(entry, "form_kind", ""),
            getattr(entry, "order_index", 0),
            str(getattr(entry, "id", "")),
        ),
    ):
        form_kind = str(getattr(item, "form_kind", "") or "").strip()
        form_slot = str(getattr(item, "form_slot", "") or "").strip()
        value = str(getattr(item, "value", "") or "").strip()
        if not form_kind or not value:
            continue
        if form_kind == "verb" and form_slot:
            payload["verb_forms"][form_slot] = value
        elif form_kind == "plural":
            payload["plural_forms"].append(value)
        elif form_kind == "derivation":
            payload["derivations"].append(value)
        elif form_kind == "comparative":
            payload["comparative"] = value
        elif form_kind == "superlative":
            payload["superlative"] = value
    return payload


def _normalize_meaning_metadata(meaning: Any) -> dict[str, list[str]]:
    metadata_entries = getattr(meaning, "metadata_entries", None)
    secondary_domains: list[str] = []
    grammar_patterns: list[str] = []
    if not isinstance(metadata_entries, list):
        return {
            "secondary_domains": secondary_domains,
            "grammar_patterns": grammar_patterns,
        }
    for item in sorted(
        metadata_entries,
        key=lambda entry: (
            getattr(entry, "metadata_kind", ""),
            getattr(entry, "order_index", 0),
            str(getattr(entry, "id", "")),
        ),
    ):
        metadata_kind = str(getattr(item, "metadata_kind", "") or "").strip()
        value = str(getattr(item, "value", "") or "").strip()
        if not value:
            continue
        if metadata_kind == "secondary_domain":
            secondary_domains.append(value)
        elif metadata_kind == "grammar_pattern":
            grammar_patterns.append(value)
    return {
        "secondary_domains": secondary_domains,
        "grammar_patterns": grammar_patterns,
    }


def serialize_word_row(
    word: Any,
    *,
    examples_by_meaning_id: dict[Any, list[Any]] | None = None,
    relations_by_meaning_id: dict[Any, list[Any]] | None = None,
) -> dict[str, Any]:
    examples_by_meaning_id = examples_by_meaning_id or {}
    relations_by_meaning_id = relations_by_meaning_id or {}
    row_source_reference = getattr(word, "source_reference", None)
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "entry_type": "word",
        "word": word.word,
        "language": getattr(word, "language", "en") or "en",
        "cefr_level": getattr(word, "cefr_level", None),
        "frequency_rank": getattr(word, "frequency_rank", None),
        "part_of_speech": _normalize_word_part_of_speech(word),
        "forms": deepcopy(_normalize_word_forms(word)),
        "confusable_words": deepcopy(_normalize_confusable_words(word)),
        "phonetics": deepcopy(getattr(word, "phonetics", None) or {}),
        "phonetic": getattr(word, "phonetic", None),
        "phonetic_confidence": getattr(word, "phonetic_confidence", None),
        "generated_at": _created_iso(getattr(word, "learner_generated_at", None)),
        "source_type": getattr(word, "source_type", None),
        "source_reference": row_source_reference,
        "senses": [],
    }

    meanings = sorted(
        list(getattr(word, "meanings", []) or []),
        key=lambda item: (
            getattr(item, "order_index", 0),
            str(getattr(item, "id", "")),
        ),
    )
    for index, meaning in enumerate(meanings):
        relation_payload = _serialize_relations(relations_by_meaning_id.get(getattr(meaning, "id", None), []))
        meaning_metadata = _normalize_meaning_metadata(meaning)
        sense_payload: dict[str, Any] = {
            "sense_id": _sense_id_for_meaning(meaning, row_source_reference, index),
            "definition": getattr(meaning, "definition", ""),
            "pos": getattr(meaning, "part_of_speech", None),
            "wn_synset_id": getattr(meaning, "wn_synset_id", None),
            "primary_domain": getattr(meaning, "primary_domain", None),
            "secondary_domains": meaning_metadata["secondary_domains"],
            "register": getattr(meaning, "register_label", None),
            "grammar_patterns": meaning_metadata["grammar_patterns"],
            "usage_note": getattr(meaning, "usage_note", None),
            "generated_at": _created_iso(
                getattr(meaning, "learner_generated_at", None) or getattr(word, "learner_generated_at", None)
            ),
            "examples": _serialize_examples(examples_by_meaning_id.get(getattr(meaning, "id", None), [])),
            "translations": _serialize_translations(getattr(meaning, "translations", []) or []),
            **relation_payload,
        }
        row["senses"].append(sense_payload)
    return row


def serialize_phrase_row(phrase: Any) -> dict[str, Any]:
    compiled_payload = getattr(phrase, "compiled_payload", None)
    row = deepcopy(compiled_payload) if isinstance(compiled_payload, dict) else {}
    row.setdefault("schema_version", SCHEMA_VERSION)
    row["entry_type"] = "phrase"
    row["word"] = row.get("word") or getattr(phrase, "phrase_text", "")
    row["display_form"] = row.get("display_form") or getattr(phrase, "phrase_text", "")
    row["normalized_form"] = row.get("normalized_form") or getattr(phrase, "normalized_form", "")
    row["language"] = row.get("language") or getattr(phrase, "language", "en") or "en"
    row["phrase_kind"] = row.get("phrase_kind") or getattr(phrase, "phrase_kind", "multiword_expression")
    row["cefr_level"] = row.get("cefr_level") if row.get("cefr_level") is not None else getattr(phrase, "cefr_level", None)
    row["register"] = row.get("register") if row.get("register") is not None else getattr(phrase, "register_label", None)
    row["brief_usage_note"] = (
        row.get("brief_usage_note")
        if row.get("brief_usage_note") is not None
        else getattr(phrase, "brief_usage_note", None)
    )
    row["usage_note"] = row.get("usage_note") if row.get("usage_note") is not None else getattr(phrase, "brief_usage_note", None)
    row["confidence"] = row.get("confidence") if row.get("confidence") is not None else getattr(phrase, "confidence_score", None)
    row["generated_at"] = row.get("generated_at") or _created_iso(getattr(phrase, "generated_at", None))
    row["seed_metadata"] = row.get("seed_metadata") if row.get("seed_metadata") is not None else deepcopy(getattr(phrase, "seed_metadata", None) or {})
    row["source_type"] = row.get("source_type") or getattr(phrase, "source_type", None)
    row["source_reference"] = row.get("source_reference") or getattr(phrase, "source_reference", None)
    row.setdefault("senses", [])
    return row


def iter_export_rows(
    *,
    max_words: int | None = None,
    max_phrases: int | None = None,
    word_batch_size: int = 500,
    phrase_batch_size: int = 500,
) -> Iterable[dict[str, Any]]:
    _ensure_backend_path()
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session, selectinload

    from app.core.config import get_settings
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.phrase_entry import PhraseEntry
    from app.models.translation import Translation
    from app.models.word import Word
    from app.models.word_relation import WordRelation
    from sqlalchemy import create_engine

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as session:
            word_offset = 0
            remaining_words = max_words
            while remaining_words is None or remaining_words > 0:
                current_word_batch_size = word_batch_size if remaining_words is None else min(word_batch_size, remaining_words)
                words = list(
                    session.execute(
                        select(Word)
                        .options(
                            selectinload(Word.form_entries),
                            selectinload(Word.confusable_entries),
                            selectinload(Word.part_of_speech_entries),
                            selectinload(Word.meanings).selectinload(Meaning.metadata_entries),
                            selectinload(Word.meanings)
                            .selectinload(Meaning.translations)
                            .selectinload(Translation.example_entries),
                        )
                        .order_by(
                            Word.frequency_rank.is_(None),
                            Word.frequency_rank.asc(),
                            func.lower(Word.word).asc(),
                            Word.id.asc(),
                        )
                        .limit(current_word_batch_size)
                        .offset(word_offset)
                    ).scalars().all()
                )
                if not words:
                    break

                meaning_ids = [
                    meaning.id
                    for word in words
                    for meaning in list(getattr(word, "meanings", []) or [])
                ]
                examples_by_meaning_id: dict[Any, list[Any]] = defaultdict(list)
                relations_by_meaning_id: dict[Any, list[Any]] = defaultdict(list)
                if meaning_ids:
                    for example in session.execute(
                        select(MeaningExample).where(MeaningExample.meaning_id.in_(meaning_ids))
                    ).scalars().all():
                        examples_by_meaning_id[example.meaning_id].append(example)
                    for relation in session.execute(
                        select(WordRelation).where(WordRelation.meaning_id.in_(meaning_ids))
                    ).scalars().all():
                        relations_by_meaning_id[relation.meaning_id].append(relation)

                for word in words:
                    yield serialize_word_row(
                        word,
                        examples_by_meaning_id=examples_by_meaning_id,
                        relations_by_meaning_id=relations_by_meaning_id,
                    )

                word_offset += len(words)
                if remaining_words is not None:
                    remaining_words -= len(words)

            phrase_offset = 0
            remaining_phrases = max_phrases
            while remaining_phrases is None or remaining_phrases > 0:
                current_phrase_batch_size = phrase_batch_size if remaining_phrases is None else min(phrase_batch_size, remaining_phrases)
                phrases = list(
                    session.execute(
                        select(PhraseEntry)
                        .order_by(
                            func.lower(PhraseEntry.normalized_form).asc(),
                            func.lower(PhraseEntry.phrase_text).asc(),
                            PhraseEntry.id.asc(),
                        )
                        .limit(current_phrase_batch_size)
                        .offset(phrase_offset)
                    ).scalars().all()
                )
                if not phrases:
                    break
                for phrase in phrases:
                    yield serialize_phrase_row(phrase)
                phrase_offset += len(phrases)
                if remaining_phrases is not None:
                    remaining_phrases -= len(phrases)
    finally:
        engine.dispose()


def load_export_rows(
    *,
    max_words: int | None = None,
    max_phrases: int | None = None,
) -> list[dict[str, Any]]:
    return list(iter_export_rows(max_words=max_words, max_phrases=max_phrases))


def write_export_rows(output_path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    return path


def export_db_fixture(
    output_path: str | Path,
    *,
    max_words: int | None = None,
    max_phrases: int | None = None,
) -> dict[str, Any]:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "row_count": 0,
        "word_count": 0,
        "phrase_count": 0,
        "reference_count": 0,
    }
    with path.open("w", encoding="utf-8") as handle:
        for row in iter_export_rows(max_words=max_words, max_phrases=max_phrases):
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
            summary["row_count"] += 1
            entry_type = str(row.get("entry_type") or "word").strip() or "word"
            if entry_type == "word":
                summary["word_count"] += 1
            elif entry_type == "phrase":
                summary["phrase_count"] += 1
            elif entry_type == "reference":
                summary["reference_count"] += 1
    return {
        "output_path": str(path),
        **summary,
    }
