from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Type
import hashlib
import json
import sys
import uuid
from collections import Counter
from contextlib import nullcontext

from tools.lexicon.validate import validate_compiled_record


SUPPORTED_RELATION_FIELDS = (
    ("synonym", "synonyms"),
    ("antonym", "antonyms"),
    ("collocation", "collocations"),
)


def _ensure_backend_path() -> None:
    backend_path = Path(__file__).resolve().parents[2] / "backend"
    backend_str = str(backend_path)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def _default_models() -> tuple[type, type, type, type, type, type, type, type, type, type, type, type]:
    _ensure_backend_path()
    from app.models.learner_catalog_entry import LearnerCatalogEntry
    from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.meaning import Meaning
    from app.models.meaning_metadata import MeaningMetadata
    from app.models.meaning_example import MeaningExample
    from app.models.translation import Translation
    from app.models.translation_example import TranslationExample
    from app.models.word import Word
    from app.models.word_confusable import WordConfusable
    from app.models.word_form import WordForm
    from app.models.word_part_of_speech import WordPartOfSpeech
    from app.models.word_relation import WordRelation

    return Word, Meaning, MeaningMetadata, MeaningExample, WordRelation, LexiconEnrichmentJob, LexiconEnrichmentRun, Translation, TranslationExample, WordConfusable, WordForm, WordPartOfSpeech, LearnerCatalogEntry


def _bucket_start_for_rank(rank: int, bucket_size: int = 100) -> int:
    return ((rank - 1) // bucket_size) * bucket_size + 1


def _rebuild_learner_catalog_projection(
    session: Any,
    *,
    learner_catalog_entry_model: Type[Any],
    word_model: Type[Any] | None = None,
    phrase_model: Type[Any] | None = None,
) -> None:
    if hasattr(session, "query"):
        session.query(learner_catalog_entry_model).delete(synchronize_session=False)

    if word_model is not None and _is_sqlalchemy_model(word_model):
        from sqlalchemy import select

        word_rows = list(
            session.execute(select(word_model))
            .scalars()
            .all()
        )
    else:
        word_rows = list(getattr(session, "words", []))

    if phrase_model is not None and _is_sqlalchemy_model(phrase_model):
        from sqlalchemy import select

        phrase_rows = list(
            session.execute(select(phrase_model))
            .scalars()
            .all()
        )
    else:
        phrase_rows = list(getattr(session, "phrases", []))

    ranked_words = sorted(
        [word for word in word_rows if getattr(word, "frequency_rank", None) is not None],
        key=lambda word: (int(getattr(word, "frequency_rank")), str(getattr(word, "word", "")).lower(), str(getattr(word, "id"))),
    )
    unranked_words = sorted(
        [word for word in word_rows if getattr(word, "frequency_rank", None) is None],
        key=lambda word: (str(getattr(word, "word", "")).lower(), str(getattr(word, "id"))),
    )
    phrases = sorted(
        phrase_rows,
        key=lambda phrase: (str(getattr(phrase, "normalized_form", "")).lower(), str(getattr(phrase, "id"))),
    )

    rows: list[Any] = []
    next_rank = 1

    for word in ranked_words:
        rank = int(getattr(word, "frequency_rank"))
        next_rank = max(next_rank, rank + 1)
        part_of_speech_entries = sorted(
            list(getattr(word, "part_of_speech_entries", [])),
            key=lambda entry: int(getattr(entry, "order_index", 0)),
        )
        primary_part_of_speech = (
            str(getattr(part_of_speech_entries[0], "value")).strip()
            if part_of_speech_entries and str(getattr(part_of_speech_entries[0], "value", "")).strip()
            else None
        )
        rows.append(
            learner_catalog_entry_model(
                entry_type="word",
                entry_id=getattr(word, "id"),
                display_text=str(getattr(word, "word", "")),
                normalized_form=str(getattr(word, "word", "")).strip().lower(),
                browse_rank=rank,
                bucket_start=_bucket_start_for_rank(rank),
                cefr_level=getattr(word, "cefr_level", None),
                primary_part_of_speech=primary_part_of_speech,
                phrase_kind=None,
                is_ranked=True,
            )
        )

    for word in unranked_words:
        rank = next_rank
        next_rank += 1
        part_of_speech_entries = sorted(
            list(getattr(word, "part_of_speech_entries", [])),
            key=lambda entry: int(getattr(entry, "order_index", 0)),
        )
        primary_part_of_speech = (
            str(getattr(part_of_speech_entries[0], "value")).strip()
            if part_of_speech_entries and str(getattr(part_of_speech_entries[0], "value", "")).strip()
            else None
        )
        rows.append(
            learner_catalog_entry_model(
                entry_type="word",
                entry_id=getattr(word, "id"),
                display_text=str(getattr(word, "word", "")),
                normalized_form=str(getattr(word, "word", "")).strip().lower(),
                browse_rank=rank,
                bucket_start=_bucket_start_for_rank(rank),
                cefr_level=getattr(word, "cefr_level", None),
                primary_part_of_speech=primary_part_of_speech,
                phrase_kind=None,
                is_ranked=False,
            )
        )

    for phrase in phrases:
        rank = next_rank
        next_rank += 1
        rows.append(
            learner_catalog_entry_model(
                entry_type="phrase",
                entry_id=getattr(phrase, "id"),
                display_text=str(getattr(phrase, "phrase_text", "")),
                normalized_form=str(getattr(phrase, "normalized_form", "")).strip().lower(),
                browse_rank=rank,
                bucket_start=_bucket_start_for_rank(rank),
                cefr_level=getattr(phrase, "cefr_level", None),
                primary_part_of_speech=None,
                phrase_kind=getattr(phrase, "phrase_kind", None),
                is_ranked=False,
            )
        )

    if rows:
        session.add_all(rows)


def _default_phrase_models() -> tuple[type, type, type, type, type]:
    _ensure_backend_path()
    from app.models.phrase_entry import PhraseEntry
    from app.models.phrase_sense import PhraseSense
    from app.models.phrase_sense_example import PhraseSenseExample
    from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization
    from app.models.phrase_sense_localization import PhraseSenseLocalization

    return PhraseEntry, PhraseSense, PhraseSenseLocalization, PhraseSenseExample, PhraseSenseExampleLocalization


def _default_reference_models() -> tuple[type, type]:
    _ensure_backend_path()
    from app.models.reference_entry import ReferenceEntry
    from app.models.reference_localization import ReferenceLocalization

    return ReferenceEntry, ReferenceLocalization


@dataclass(frozen=True)
class ImportSummary:
    created_words: int = 0
    updated_words: int = 0
    skipped_words: int = 0
    created_meanings: int = 0
    updated_meanings: int = 0
    created_examples: int = 0
    deleted_examples: int = 0
    created_relations: int = 0
    deleted_relations: int = 0
    created_translations: int = 0
    updated_translations: int = 0
    created_enrichment_jobs: int = 0
    reused_enrichment_jobs: int = 0
    created_enrichment_runs: int = 0
    reused_enrichment_runs: int = 0
    created_phrases: int = 0
    updated_phrases: int = 0
    skipped_phrases: int = 0
    created_reference_entries: int = 0
    updated_reference_entries: int = 0
    skipped_reference_entries: int = 0
    created_reference_localizations: int = 0
    updated_reference_localizations: int = 0


def _increment(summary: ImportSummary, **changes: int) -> ImportSummary:
    values = summary.__dict__.copy()
    for key, delta in changes.items():
        values[key] = values.get(key, 0) + delta
    return replace(summary, **values)


def _summary_has_material_changes(summary: ImportSummary) -> bool:
    return any(
        value
        for key, value in summary.__dict__.items()
        if not key.startswith("skipped_")
    )


def _replace_collection(parent: Any, attribute: str, items: list[Any]) -> None:
    collection = getattr(parent, attribute, None)
    if isinstance(collection, list):
        collection.clear()
        collection.extend(items)
    else:
        setattr(parent, attribute, list(items))


def _replace_normalized_child_collection(session: Any, parent: Any, attribute: str, items: list[Any]) -> None:
    collection = getattr(parent, attribute, None)
    if not isinstance(collection, list):
        setattr(parent, attribute, list(items))
        return

    existing_items = list(collection)
    if existing_items:
        for existing_item in existing_items:
            if hasattr(session, "delete"):
                session.delete(existing_item)
        collection.clear()
        if hasattr(session, "flush"):
            session.flush()
    collection.extend(items)


def _session_no_autoflush(session: Any) -> Any:
    context = getattr(session, "no_autoflush", None)
    if context is None:
        return nullcontext()
    return context


def _validate_on_conflict_mode(on_conflict: str) -> str:
    normalized = str(on_conflict or "fail").strip().lower()
    if normalized not in {"fail", "upsert", "skip"}:
        raise ValueError(f"unsupported on_conflict mode: {on_conflict}")
    return normalized


def _raise_existing_entry_conflict(*, entry_type: str, identifier: str, language: str) -> None:
    raise ValueError(f"{entry_type} '{identifier}' for language '{language}' already exists")


def _phrase_example_translation_score(translations: dict[str, Any], example_index: int) -> tuple[int, int]:
    translated_count = 0
    translated_length = 0
    for locale in sorted(translations.keys()):
        locale_payload = translations.get(locale) or {}
        translated_examples = locale_payload.get("examples") or []
        if not isinstance(translated_examples, list) or example_index >= len(translated_examples):
            continue
        translated_example = str(translated_examples[example_index] or "").strip()
        if not translated_example:
            continue
        translated_count += 1
        translated_length += len(translated_example)
    return translated_count, translated_length


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _first_example_sentence(sense: dict[str, Any]) -> str | None:
    examples = sense.get("examples") or []
    if not examples:
        return None
    example = examples[0] or {}
    return example.get("sentence")


def _is_sqlalchemy_model(model: Type[Any]) -> bool:
    return hasattr(model, "__table__")


def _is_real_mapped_model(model: Type[Any]) -> bool:
    return _is_sqlalchemy_model(model) and hasattr(model, "__mapper__")


def _ensure_object_id(instance: Any) -> None:
    if getattr(instance, "id", None) is None:
        setattr(instance, "id", uuid.uuid4())


def _preload_existing_words(
    session: Any,
    word_model: Type[Any],
    rows: Iterable[dict[str, Any]],
    default_language: str,
) -> dict[tuple[str, str], Any]:
    if not _is_real_mapped_model(word_model):
        return {}

    from sqlalchemy import select

    lemmas_by_language: dict[str, set[str]] = {}
    for row in rows:
        if str(row.get("entry_type") or "word").strip().lower() not in {"", "word"}:
            continue
        lemma = str(row.get("word") or "").strip()
        if not lemma:
            continue
        row_language = _effective_row_language(row, default_language)
        lemmas_by_language.setdefault(row_language, set()).add(lemma)

    existing: dict[tuple[str, str], Any] = {}
    for row_language, lemmas in lemmas_by_language.items():
        if not lemmas:
            continue
        result = session.execute(
            select(word_model).where(
                word_model.language == row_language,
                word_model.word.in_(sorted(lemmas)),
            )
        )
        for item in result.scalars().all():
            existing[(str(getattr(item, "word", "")), str(getattr(item, "language", default_language)))] = item
    return existing


def _preload_existing_by_normalized_form(
    session: Any,
    model: Type[Any],
    rows: Iterable[dict[str, Any]],
    default_language: str,
    *,
    entry_type: str,
) -> dict[tuple[str, str], Any]:
    if not _is_real_mapped_model(model):
        return {}

    from sqlalchemy import select

    normalized_by_language: dict[str, set[str]] = {}
    for row in rows:
        if str(row.get("entry_type") or "word").strip().lower() != entry_type:
            continue
        normalized_form = str(row.get("normalized_form") or "").strip()
        if not normalized_form:
            continue
        row_language = _effective_row_language(row, default_language)
        normalized_by_language.setdefault(row_language, set()).add(normalized_form)

    existing: dict[tuple[str, str], Any] = {}
    for row_language, normalized_forms in normalized_by_language.items():
        if not normalized_forms:
            continue
        result = session.execute(
            select(model).where(
                model.language == row_language,
                model.normalized_form.in_(sorted(normalized_forms)),
            )
        )
        for item in result.scalars().all():
            existing[(str(getattr(item, "normalized_form", "")), str(getattr(item, "language", default_language)))] = item
    return existing


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _normalize_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise ValueError(f"confidence must be between 0 and 1; got {value}")
    return confidence


def _find_existing_word(session: Any, word_model: Type[Any], lemma: str, language: str) -> Any | None:
    if _is_sqlalchemy_model(word_model):
        from sqlalchemy import select

        result = session.execute(
            select(word_model).where(
                word_model.word == lemma,
                word_model.language == language,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _find_existing_by_normalized_form(session: Any, model: Type[Any], normalized_form: str, language: str) -> Any | None:
    if _is_sqlalchemy_model(model):
        from sqlalchemy import select

        result = session.execute(
            select(model).where(
                model.normalized_form == normalized_form,
                model.language == language,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _load_existing_meanings(session: Any, meaning_model: Type[Any], word_id: Any) -> list[Any]:
    if _is_sqlalchemy_model(meaning_model):
        from sqlalchemy import select

        result = session.execute(
            select(meaning_model)
            .where(meaning_model.word_id == word_id)
            .order_by(meaning_model.order_index.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _find_existing_enrichment_job(session: Any, job_model: Type[Any], word_id: Any, phase: str) -> Any | None:
    if _is_sqlalchemy_model(job_model):
        from sqlalchemy import select

        result = session.execute(
            select(job_model).where(
                job_model.word_id == word_id,
                job_model.phase == phase,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _find_existing_enrichment_run(
    session: Any,
    run_model: Type[Any],
    enrichment_job_id: Any,
    prompt_version: str | None,
    prompt_hash: str,
) -> Any | None:
    if _is_sqlalchemy_model(run_model):
        from sqlalchemy import select

        result = session.execute(
            select(run_model).where(
                run_model.enrichment_job_id == enrichment_job_id,
                run_model.prompt_version == prompt_version,
                run_model.prompt_hash == prompt_hash,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _load_existing_examples(session: Any, example_model: Type[Any], meaning_id: Any, source: str) -> list[Any]:
    if _is_sqlalchemy_model(example_model):
        from sqlalchemy import select

        result = session.execute(
            select(example_model)
            .where(
                example_model.meaning_id == meaning_id,
            )
            .order_by(example_model.order_index.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _load_existing_translations(session: Any, translation_model: Type[Any], meaning_id: Any) -> list[Any]:
    if _is_sqlalchemy_model(translation_model):
        from sqlalchemy import select

        result = session.execute(
            select(translation_model)
            .where(translation_model.meaning_id == meaning_id)
            .order_by(translation_model.language.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _load_existing_relations(session: Any, relation_model: Type[Any], meaning_id: Any, source: str) -> list[Any]:
    if _is_sqlalchemy_model(relation_model):
        from sqlalchemy import select

        relation_types = [relation_type for relation_type, _ in SUPPORTED_RELATION_FIELDS]
        result = session.execute(
            select(relation_model)
            .where(
                relation_model.meaning_id == meaning_id,
                relation_model.relation_type.in_(relation_types),
            )
            .order_by(relation_model.relation_type.asc(), relation_model.related_word.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _load_existing_reference_localizations(session: Any, localization_model: Type[Any], reference_entry_id: Any) -> list[Any]:
    if _is_sqlalchemy_model(localization_model):
        from sqlalchemy import select

        result = session.execute(
            select(localization_model)
            .where(localization_model.reference_entry_id == reference_entry_id)
            .order_by(localization_model.locale.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _make_word_prompt_hash(
    source_type: str,
    source_reference: str,
    word: str,
    generation_run_id: str | None,
    model_name: str | None,
    prompt_version: str | None,
) -> str:
    payload = "|".join(
        [
            source_type,
            source_reference,
            word,
            str(generation_run_id or ""),
            str(model_name or ""),
            str(prompt_version or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sense_run_group_key(sense: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        str(sense.get("generation_run_id") or "") or None,
        str(sense.get("model_name") or "") or None,
        str(sense.get("prompt_version") or "") or None,
    )


def _sync_word_level_enrichment_fields(
    word: Any,
    row: dict[str, Any],
    run: Any | None,
    source_type: str,
) -> None:
    if row.get("cefr_level") is not None and hasattr(word, "cefr_level"):
        word.cefr_level = row.get("cefr_level")
    if row.get("part_of_speech") is not None and hasattr(word, "part_of_speech"):
        word.part_of_speech = list(row.get("part_of_speech") or [])
    if row.get("generated_at") is not None and hasattr(word, "learner_generated_at"):
        word.learner_generated_at = _parse_timestamp(row.get("generated_at"))
    if row.get("generated_at") is not None and hasattr(word, "generated_at"):
        word.generated_at = _parse_timestamp(row.get("generated_at"))
    phonetic = row.get("phonetic")
    phonetic_confidence = row.get("phonetic_confidence")
    phonetics = row.get("phonetics")
    if isinstance(phonetics, dict) and hasattr(word, "phonetics"):
        word.phonetics = {
            accent: dict(payload)
            for accent, payload in phonetics.items()
            if isinstance(accent, str) and isinstance(payload, dict)
        }
    if phonetic is None and isinstance(phonetics, dict):
        for accent in ("us", "uk", "au"):
            accent_payload = phonetics.get(accent)
            if not isinstance(accent_payload, dict):
                continue
            ipa = accent_payload.get("ipa")
            if isinstance(ipa, str) and ipa.strip():
                phonetic = ipa.strip()
                phonetic_confidence = accent_payload.get("confidence")
                break
    if phonetic is not None and hasattr(word, "phonetic"):
        word.phonetic = phonetic
    if phonetic is not None and hasattr(word, "phonetic_source"):
        word.phonetic_source = source_type
    if phonetic_confidence is not None and hasattr(word, "phonetic_confidence"):
        word.phonetic_confidence = _normalize_confidence(phonetic_confidence)


def _sync_word_confusable_rows(session: Any, word: Any, row: dict[str, Any], word_confusable_model: Type[Any] | None) -> None:
    if word_confusable_model is None or not hasattr(word, "confusable_entries"):
        return

    confusable_rows: list[Any] = []
    for index, item in enumerate(list(row.get("confusable_words") or [])):
        if not isinstance(item, dict):
            continue
        confusable_word = str(item.get("word") or "").strip()
        if not confusable_word:
            continue
        note = item.get("note")
        confusable_rows.append(
            word_confusable_model(
                word_id=word.id,
                confusable_word=confusable_word,
                note=str(note).strip() if isinstance(note, str) and str(note).strip() else None,
                order_index=index,
            )
        )
    _replace_normalized_child_collection(session, word, "confusable_entries", confusable_rows)


def _sync_word_form_rows(session: Any, word: Any, row: dict[str, Any], word_form_model: Type[Any] | None) -> None:
    if word_form_model is None or not hasattr(word, "form_entries"):
        return

    forms = row.get("forms") if isinstance(row.get("forms"), dict) else {}
    normalized_rows: list[Any] = []

    verb_forms = forms.get("verb_forms") if isinstance(forms.get("verb_forms"), dict) else {}
    for index, slot in enumerate(("base", "past", "gerund", "past_participle", "third_person_singular")):
        value = str(verb_forms.get(slot) or "").strip()
        if not value:
            continue
        normalized_rows.append(
            word_form_model(
                word_id=word.id,
                form_kind="verb",
                form_slot=slot,
                value=value,
                order_index=index,
            )
        )

    for index, value in enumerate(_normalize_string_list(forms.get("plural_forms"))):
        normalized_rows.append(
            word_form_model(
                word_id=word.id,
                form_kind="plural",
                form_slot="",
                value=value,
                order_index=index,
            )
        )

    for index, value in enumerate(_normalize_string_list(forms.get("derivations"))):
        normalized_rows.append(
            word_form_model(
                word_id=word.id,
                form_kind="derivation",
                form_slot="",
                value=value,
                order_index=index,
            )
        )

    comparative = str(forms.get("comparative") or "").strip()
    if comparative:
        normalized_rows.append(
            word_form_model(
                word_id=word.id,
                form_kind="comparative",
                form_slot="",
                value=comparative,
                order_index=0,
            )
        )

    superlative = str(forms.get("superlative") or "").strip()
    if superlative:
        normalized_rows.append(
            word_form_model(
                word_id=word.id,
                form_kind="superlative",
                form_slot="",
                value=superlative,
                order_index=0,
            )
        )

    _replace_normalized_child_collection(session, word, "form_entries", normalized_rows)


def _sync_word_part_of_speech_rows(session: Any, word: Any, row: dict[str, Any], word_part_of_speech_model: Type[Any] | None) -> None:
    if word_part_of_speech_model is None or not hasattr(word, "part_of_speech_entries"):
        return

    normalized_rows: list[Any] = []
    for index, item in enumerate(list(row.get("part_of_speech") or [])):
        value = str(item or "").strip()
        if not value:
            continue
        normalized_rows.append(
            word_part_of_speech_model(
                word_id=word.id,
                value=value,
                order_index=index,
            )
        )
    _replace_normalized_child_collection(session, word, "part_of_speech_entries", normalized_rows)


def _sync_translation_example_rows(
    translation: Any,
    translated_examples: list[str],
    translation_example_model: Type[Any] | None,
) -> None:
    if translation_example_model is None or not hasattr(translation, "example_entries"):
        return

    example_rows = []
    for index, text in enumerate(translated_examples):
        example_row = translation_example_model(
            translation_id=translation.id,
            text=text,
            order_index=index,
        )
        _ensure_object_id(example_row)
        if _is_real_mapped_model(translation_example_model):
            example_row.translation = translation
        example_rows.append(example_row)
    _replace_collection(translation, "example_entries", example_rows)


def _sync_meaning_metadata_rows(session: Any, meaning: Any, sense: dict[str, Any], meaning_metadata_model: Type[Any] | None) -> None:
    if meaning_metadata_model is None or not hasattr(meaning, "metadata_entries"):
        return

    metadata_rows: list[Any] = []
    for index, value in enumerate(_normalize_string_list(sense.get("secondary_domains"))):
        metadata_rows.append(
            meaning_metadata_model(
                meaning_id=meaning.id,
                metadata_kind="secondary_domain",
                value=value,
                order_index=index,
            )
        )
    for index, value in enumerate(_normalize_string_list(sense.get("grammar_patterns"))):
        metadata_rows.append(
            meaning_metadata_model(
                meaning_id=meaning.id,
                metadata_kind="grammar_pattern",
                value=value,
                order_index=index,
            )
        )
    _replace_normalized_child_collection(session, meaning, "metadata_entries", metadata_rows)


def _sync_meaning_level_learner_fields(meaning: Any, sense: dict[str, Any], row: dict[str, Any]) -> None:
    if sense.get("wn_synset_id") is not None and hasattr(meaning, "wn_synset_id"):
        meaning.wn_synset_id = sense.get("wn_synset_id")
    if sense.get("primary_domain") is not None and hasattr(meaning, "primary_domain"):
        meaning.primary_domain = sense.get("primary_domain")
    if sense.get("register") is not None and hasattr(meaning, "register_label"):
        meaning.register_label = sense.get("register")
    if sense.get("register") is not None and hasattr(meaning, "register"):
        meaning.register = sense.get("register")
    if sense.get("usage_note") is not None and hasattr(meaning, "usage_note"):
        meaning.usage_note = sense.get("usage_note")
    meaning_generated_at = sense.get("generated_at") or row.get("generated_at")
    if meaning_generated_at is not None and hasattr(meaning, "learner_generated_at"):
        meaning.learner_generated_at = _parse_timestamp(meaning_generated_at)
    if meaning_generated_at is not None and hasattr(meaning, "generated_at"):
        meaning.generated_at = _parse_timestamp(meaning_generated_at)


def _effective_row_language(row: dict[str, Any], default_language: str) -> str:
    return str(row.get("language") or default_language or "en").strip() or "en"


def _effective_row_source_type(row: dict[str, Any], default_source_type: str) -> str:
    return str(row.get("source_type") or default_source_type).strip() or default_source_type


def _effective_row_source_reference(row: dict[str, Any], default_source_reference: str) -> str:
    return str(row.get("source_reference") or default_source_reference).strip() or default_source_reference


def _effective_normalized_form(row: dict[str, Any]) -> str:
    return str(row.get("normalized_form") or row.get("display_form") or row.get("word") or "").strip().lower()


def _supports_cascaded_phrase_import(
    phrase_model: Type[Any] | None,
    phrase_sense_model: Type[Any] | None,
    phrase_sense_localization_model: Type[Any] | None,
    phrase_sense_example_model: Type[Any] | None,
    phrase_sense_example_localization_model: Type[Any] | None,
) -> bool:
    models = (
        phrase_model,
        phrase_sense_model,
        phrase_sense_localization_model,
        phrase_sense_example_model,
        phrase_sense_example_localization_model,
    )
    return all(model is not None and _is_real_mapped_model(model) for model in models)


def _supports_cascaded_word_import(
    word_model: Type[Any] | None,
    meaning_model: Type[Any] | None,
    translation_model: Type[Any] | None,
    word_relation_model: Type[Any] | None,
    lexicon_enrichment_job_model: Type[Any] | None,
    lexicon_enrichment_run_model: Type[Any] | None,
) -> bool:
    models = (
        word_model,
        meaning_model,
        translation_model,
        word_relation_model,
        lexicon_enrichment_job_model,
        lexicon_enrichment_run_model,
    )
    return all(model is not None and _is_real_mapped_model(model) for model in models)


def _append_collection_item(parent: Any, attribute: str, item: Any) -> None:
    collection = getattr(parent, attribute, None)
    append = getattr(collection, "append", None)
    if callable(append) and item not in collection:
        append(item)


def _attach_child(parent: Any, collection_attribute: str, child: Any, child_attribute: str) -> None:
    _append_collection_item(parent, collection_attribute, child)
    if getattr(child, child_attribute, None) is None:
        setattr(child, child_attribute, parent)


def _supports_bulk_insert_model(session: Any, model: Type[Any] | None) -> bool:
    return (
        model is not None
        and _is_sqlalchemy_model(model)
        and _is_real_mapped_model(model)
        and hasattr(session, "execute")
    )


def _bulk_insert_mapped_rows(session: Any, model: Type[Any], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    from sqlalchemy import insert

    session.execute(insert(model), rows)


def _delete_rows_for_foreign_keys(
    session: Any,
    model: Type[Any] | None,
    foreign_key_column: str,
    ids: set[Any],
) -> None:
    if (
        not ids
        or model is None
        or not _is_sqlalchemy_model(model)
        or not _supports_bulk_insert_model(session, model)
    ):
        return
    from sqlalchemy import delete

    session.execute(delete(model).where(getattr(model, foreign_key_column).in_(sorted(ids))))


def import_compiled_rows(
    session: Any,
    rows: Iterable[dict[str, Any]],
    *,
    source_type: str,
    source_reference: str,
    language: str = "en",
    word_model: Optional[Type[Any]] = None,
    meaning_model: Optional[Type[Any]] = None,
    meaning_metadata_model: Optional[Type[Any]] = None,
    meaning_example_model: Optional[Type[Any]] = None,
    word_relation_model: Optional[Type[Any]] = None,
    lexicon_enrichment_job_model: Optional[Type[Any]] = None,
    lexicon_enrichment_run_model: Optional[Type[Any]] = None,
    translation_model: Optional[Type[Any]] = None,
    translation_example_model: Optional[Type[Any]] = None,
    phrase_model: Optional[Type[Any]] = None,
    phrase_sense_model: Optional[Type[Any]] = None,
    phrase_sense_localization_model: Optional[Type[Any]] = None,
    phrase_sense_example_model: Optional[Type[Any]] = None,
    phrase_sense_example_localization_model: Optional[Type[Any]] = None,
    reference_model: Optional[Type[Any]] = None,
    reference_localization_model: Optional[Type[Any]] = None,
    word_confusable_model: Optional[Type[Any]] = None,
    word_form_model: Optional[Type[Any]] = None,
    word_part_of_speech_model: Optional[Type[Any]] = None,
    learner_catalog_entry_model: Optional[Type[Any]] = None,
    rebuild_learner_catalog: bool = True,
    progress_callback: Optional[Callable[[dict[str, Any], int, int], None]] = None,
    on_conflict: str = "upsert",
) -> ImportSummary:
    on_conflict = _validate_on_conflict_mode(on_conflict)
    if word_model is None or meaning_model is None:
        (
            word_model,
            meaning_model,
            default_meaning_metadata_model,
            default_meaning_example_model,
            default_word_relation_model,
            default_job_model,
            default_run_model,
            default_translation_model,
            default_translation_example_model,
            default_word_confusable_model,
            default_word_form_model,
            default_word_part_of_speech_model,
            default_learner_catalog_entry_model,
        ) = _default_models()
        if meaning_example_model is None:
            meaning_example_model = default_meaning_example_model
        if meaning_metadata_model is None:
            meaning_metadata_model = default_meaning_metadata_model
        if word_relation_model is None:
            word_relation_model = default_word_relation_model
        if lexicon_enrichment_job_model is None:
            lexicon_enrichment_job_model = default_job_model
        if lexicon_enrichment_run_model is None:
            lexicon_enrichment_run_model = default_run_model
        if translation_model is None:
            translation_model = default_translation_model
        if translation_example_model is None:
            translation_example_model = default_translation_example_model
        if word_confusable_model is None:
            word_confusable_model = default_word_confusable_model
        if word_form_model is None:
            word_form_model = default_word_form_model
        if word_part_of_speech_model is None:
            word_part_of_speech_model = default_word_part_of_speech_model
        if learner_catalog_entry_model is None:
            learner_catalog_entry_model = default_learner_catalog_entry_model
    resolved_phrase_model = phrase_model
    resolved_phrase_sense_model = phrase_sense_model
    resolved_phrase_sense_localization_model = phrase_sense_localization_model
    resolved_phrase_sense_example_model = phrase_sense_example_model
    resolved_phrase_sense_example_localization_model = phrase_sense_example_localization_model
    resolved_reference_model = reference_model
    resolved_reference_localization_model = reference_localization_model

    summary = ImportSummary()
    row_list = list(rows)
    total_rows = len(row_list)
    preloaded_words = _preload_existing_words(session, word_model, row_list, language)
    preloaded_phrases = (
        _preload_existing_by_normalized_form(
            session,
            phrase_model,
            row_list,
            language,
            entry_type="phrase",
        )
        if phrase_model is not None
        else {}
    )
    preloaded_references = (
        _preload_existing_by_normalized_form(
            session,
            reference_model,
            row_list,
            language,
            entry_type="reference",
        )
        if reference_model is not None
        else {}
    )
    bulk_insert_meaning_examples = _supports_bulk_insert_model(session, meaning_example_model)
    bulk_insert_translation_examples = _supports_bulk_insert_model(session, translation_example_model)
    bulk_insert_word_relations = _supports_bulk_insert_model(session, word_relation_model)
    pending_meaning_example_rows: list[dict[str, Any]] = []
    pending_translation_example_rows: list[dict[str, Any]] = []
    pending_word_relation_rows: list[dict[str, Any]] = []
    translation_example_delete_ids: set[Any] = set()

    for row_index, row in enumerate(row_list, start=1):
        entry_type = str(row.get("entry_type") or "word").strip().lower() or "word"
        row_language = _effective_row_language(row, language)
        row_source_type = _effective_row_source_type(row, source_type)
        row_source_reference = _effective_row_source_reference(row, source_reference)
        if entry_type == "phrase":
            senses = row.get("senses")
            if isinstance(senses, list) and senses:
                validation_errors = validate_compiled_record(row)
                if validation_errors:
                    raise RuntimeError("; ".join(validation_errors))
            if (
                resolved_phrase_model is None
                or resolved_phrase_sense_model is None
                or resolved_phrase_sense_localization_model is None
                or resolved_phrase_sense_example_model is None
                or resolved_phrase_sense_example_localization_model is None
            ) and isinstance(senses, list) and senses:
                (
                    default_phrase_model,
                    default_phrase_sense_model,
                    default_phrase_sense_localization_model,
                    default_phrase_sense_example_model,
                    default_phrase_sense_example_localization_model,
                ) = _default_phrase_models()
                if resolved_phrase_model is None:
                    resolved_phrase_model = default_phrase_model
                if resolved_phrase_sense_model is None:
                    resolved_phrase_sense_model = default_phrase_sense_model
                if resolved_phrase_sense_localization_model is None:
                    resolved_phrase_sense_localization_model = default_phrase_sense_localization_model
                if resolved_phrase_sense_example_model is None:
                    resolved_phrase_sense_example_model = default_phrase_sense_example_model
                if resolved_phrase_sense_example_localization_model is None:
                    resolved_phrase_sense_example_localization_model = default_phrase_sense_example_localization_model
            if resolved_phrase_model is None:
                resolved_phrase_model = _default_phrase_models()[0]
            phrase_normalized_form = _effective_normalized_form(row)
            phrase_key = (phrase_normalized_form, row_language)
            existing_phrase = preloaded_phrases.get(phrase_key)
            if existing_phrase is None:
                existing_phrase = _find_existing_by_normalized_form(
                    session,
                    resolved_phrase_model,
                    phrase_key[0],
                    row_language,
                )
            if existing_phrase is not None:
                preloaded_phrases[phrase_key] = existing_phrase
            if existing_phrase is None:
                phrase = resolved_phrase_model(
                    phrase_text=row.get("display_form") or row.get("word"),
                    normalized_form=phrase_normalized_form,
                    phrase_kind=row.get("phrase_kind") or "multiword_expression",
                    language=row_language,
                    cefr_level=row.get("cefr_level"),
                    register_label=row.get("register") or row.get("register_label"),
                    brief_usage_note=row.get("brief_usage_note") or row.get("usage_note"),
                    compiled_payload=row if hasattr(resolved_phrase_model, "compiled_payload") else None,
                    seed_metadata=row.get("seed_metadata") if hasattr(resolved_phrase_model, "seed_metadata") else None,
                    confidence_score=_normalize_confidence(row.get("confidence")) if hasattr(resolved_phrase_model, "confidence_score") else None,
                    generated_at=_parse_timestamp(row.get("generated_at")) if hasattr(resolved_phrase_model, "generated_at") else None,
                    source_type=row_source_type,
                    source_reference=row_source_reference,
                )
                _ensure_object_id(phrase)
                session.add(phrase)
                preloaded_phrases[phrase_key] = phrase
                summary = _increment(summary, created_phrases=1)
                current_phrase = phrase
                is_new_phrase = True
            else:
                if on_conflict == "fail":
                    _raise_existing_entry_conflict(entry_type="phrase", identifier=phrase_key[0], language=row_language)
                if on_conflict == "skip":
                    summary = _increment(summary, skipped_phrases=1)
                    continue
                existing_phrase.phrase_text = row.get("display_form") or row.get("word")
                existing_phrase.normalized_form = phrase_normalized_form or existing_phrase.normalized_form
                existing_phrase.phrase_kind = row.get("phrase_kind") or existing_phrase.phrase_kind
                existing_phrase.cefr_level = row.get("cefr_level")
                existing_phrase.register_label = row.get("register") or row.get("register_label")
                existing_phrase.brief_usage_note = row.get("brief_usage_note") or row.get("usage_note")
                if hasattr(existing_phrase, "compiled_payload"):
                    existing_phrase.compiled_payload = row
                if hasattr(existing_phrase, "seed_metadata"):
                    existing_phrase.seed_metadata = row.get("seed_metadata")
                if hasattr(existing_phrase, "confidence_score"):
                    existing_phrase.confidence_score = _normalize_confidence(row.get("confidence"))
                if hasattr(existing_phrase, "generated_at"):
                    existing_phrase.generated_at = _parse_timestamp(row.get("generated_at"))
                if hasattr(existing_phrase, "source_type"):
                    existing_phrase.source_type = row_source_type
                if hasattr(existing_phrase, "source_reference"):
                    existing_phrase.source_reference = row_source_reference
                summary = _increment(summary, updated_phrases=1)
                current_phrase = existing_phrase
                is_new_phrase = False
            if isinstance(senses, list) and senses and resolved_phrase_sense_model is not None:
                use_cascaded_phrase_graph = is_new_phrase and _supports_cascaded_phrase_import(
                    resolved_phrase_model,
                    resolved_phrase_sense_model,
                    resolved_phrase_sense_localization_model,
                    resolved_phrase_sense_example_model,
                    resolved_phrase_sense_example_localization_model,
                )
                phrase_senses: list[Any] = []
                for sense_index, sense in enumerate(senses):
                    phrase_sense = resolved_phrase_sense_model(
                        phrase_entry_id=current_phrase.id,
                        definition=str((sense or {}).get("definition") or "").strip(),
                        usage_note=str((sense or {}).get("usage_note") or "").strip() or None,
                        part_of_speech=str((sense or {}).get("part_of_speech") or (sense or {}).get("pos") or "").strip() or None,
                        register=str((sense or {}).get("register") or "").strip() or None,
                        primary_domain=str((sense or {}).get("primary_domain") or "").strip() or None,
                        secondary_domains=_normalize_string_list((sense or {}).get("secondary_domains")),
                        grammar_patterns=_normalize_string_list((sense or {}).get("grammar_patterns")),
                        synonyms=_normalize_string_list((sense or {}).get("synonyms")),
                        antonyms=_normalize_string_list((sense or {}).get("antonyms")),
                        collocations=_normalize_string_list((sense or {}).get("collocations")),
                        order_index=sense_index,
                    )
                    _ensure_object_id(phrase_sense)
                    if use_cascaded_phrase_graph or _is_real_mapped_model(resolved_phrase_sense_model):
                        phrase_sense.phrase_entry = current_phrase
                    if not use_cascaded_phrase_graph:
                        session.add(phrase_sense)
                    sense_localizations: list[Any] = []
                    translations = (sense or {}).get("translations") or {}
                    for locale in sorted(translations.keys()):
                        locale_payload = translations.get(locale) or {}
                        localized_definition = str(locale_payload.get("definition") or "").strip() or None
                        localized_usage_note = str(locale_payload.get("usage_note") or "").strip() or None
                        if localized_definition is None and localized_usage_note is None:
                            continue
                        localization = resolved_phrase_sense_localization_model(
                            phrase_sense_id=phrase_sense.id,
                            locale=locale,
                            localized_definition=localized_definition,
                            localized_usage_note=localized_usage_note,
                        )
                        _ensure_object_id(localization)
                        if use_cascaded_phrase_graph or _is_real_mapped_model(resolved_phrase_sense_localization_model):
                            localization.phrase_sense = phrase_sense
                        if not use_cascaded_phrase_graph:
                            session.add(localization)
                        sense_localizations.append(localization)
                    _replace_collection(phrase_sense, "localizations", sense_localizations)

                    phrase_examples: list[Any] = []
                    selected_examples_by_sentence: dict[str, dict[str, Any]] = {}
                    selected_sentence_order: list[str] = []
                    for example_index, example in enumerate((sense or {}).get("examples") or []):
                        sentence = str((example or {}).get("sentence") or "").strip()
                        if not sentence:
                            continue
                        example_score = _phrase_example_translation_score(translations, example_index)
                        current_best = selected_examples_by_sentence.get(sentence)
                        if current_best is None:
                            selected_examples_by_sentence[sentence] = {
                                "sentence": sentence,
                                "difficulty": (example or {}).get("difficulty"),
                                "example_index": example_index,
                                "score": example_score,
                            }
                            selected_sentence_order.append(sentence)
                            continue
                        if example_score > current_best["score"]:
                            current_best.update(
                                {
                                    "difficulty": (example or {}).get("difficulty"),
                                    "example_index": example_index,
                                    "score": example_score,
                                }
                            )
                    for selected_sentence in selected_sentence_order:
                        selected_example = selected_examples_by_sentence[selected_sentence]
                        selected_example_index = int(selected_example["example_index"])
                        phrase_example = resolved_phrase_sense_example_model(
                            phrase_sense_id=phrase_sense.id,
                            sentence=selected_example["sentence"],
                            difficulty=selected_example["difficulty"],
                            order_index=len(phrase_examples),
                            source=row_source_type,
                        )
                        _ensure_object_id(phrase_example)
                        if use_cascaded_phrase_graph or _is_real_mapped_model(resolved_phrase_sense_example_model):
                            phrase_example.phrase_sense = phrase_sense
                        if not use_cascaded_phrase_graph:
                            session.add(phrase_example)
                        example_localizations: list[Any] = []
                        for locale in sorted(translations.keys()):
                            locale_payload = translations.get(locale) or {}
                            translated_examples = locale_payload.get("examples") or []
                            translated_example = None
                            if isinstance(translated_examples, list) and selected_example_index < len(translated_examples):
                                translated_example = str(translated_examples[selected_example_index] or "").strip() or None
                            if translated_example is None:
                                continue
                            example_localization = resolved_phrase_sense_example_localization_model(
                                phrase_sense_example_id=phrase_example.id,
                                locale=locale,
                                translation=translated_example,
                            )
                            _ensure_object_id(example_localization)
                            if use_cascaded_phrase_graph or _is_real_mapped_model(resolved_phrase_sense_example_localization_model):
                                example_localization.phrase_sense_example = phrase_example
                            if not use_cascaded_phrase_graph:
                                session.add(example_localization)
                            example_localizations.append(example_localization)
                        _replace_collection(phrase_example, "localizations", example_localizations)
                        phrase_examples.append(phrase_example)
                    _replace_collection(phrase_sense, "examples", phrase_examples)
                    phrase_senses.append(phrase_sense)
                _replace_collection(current_phrase, "phrase_senses", phrase_senses)
            elif isinstance(senses, list):
                _replace_collection(current_phrase, "phrase_senses", [])
            continue
        if entry_type == "reference":
            if resolved_reference_model is None or resolved_reference_localization_model is None:
                default_reference_model, default_reference_localization_model = _default_reference_models()
                if resolved_reference_model is None:
                    resolved_reference_model = default_reference_model
                if resolved_reference_localization_model is None:
                    resolved_reference_localization_model = default_reference_localization_model
            reference_normalized_form = _effective_normalized_form(row)
            reference_key = (reference_normalized_form, row_language)
            existing_reference = preloaded_references.get(reference_key)
            if existing_reference is None:
                existing_reference = _find_existing_by_normalized_form(
                    session,
                    resolved_reference_model,
                    reference_key[0],
                    row_language,
                )
                if existing_reference is not None:
                    preloaded_references[reference_key] = existing_reference
            if existing_reference is None:
                reference_entry = resolved_reference_model(
                    reference_type=row.get("reference_type") or "name",
                    display_form=row.get("display_form") or row.get("word"),
                    normalized_form=reference_normalized_form,
                    translation_mode=row.get("translation_mode") or "unchanged",
                    brief_description=row.get("brief_description") or "",
                    pronunciation=row.get("pronunciation") or "",
                    learner_tip=row.get("learner_tip"),
                    language=row_language,
                    source_type=row_source_type,
                    source_reference=row_source_reference,
                )
                _ensure_object_id(reference_entry)
                session.add(reference_entry)
                preloaded_references[reference_key] = reference_entry
                current_reference = reference_entry
                summary = _increment(summary, created_reference_entries=1)
                is_new_reference = True
            else:
                if on_conflict == "fail":
                    _raise_existing_entry_conflict(entry_type="reference", identifier=reference_key[0], language=row_language)
                if on_conflict == "skip":
                    summary = _increment(summary, skipped_reference_entries=1)
                    continue
                current_reference = existing_reference
                current_reference.reference_type = row.get("reference_type") or current_reference.reference_type
                current_reference.display_form = row.get("display_form") or current_reference.display_form
                current_reference.normalized_form = reference_normalized_form or current_reference.normalized_form
                current_reference.translation_mode = row.get("translation_mode") or current_reference.translation_mode
                current_reference.brief_description = row.get("brief_description") or current_reference.brief_description
                current_reference.pronunciation = row.get("pronunciation") or current_reference.pronunciation
                current_reference.learner_tip = row.get("learner_tip")
                if hasattr(current_reference, "source_type"):
                    current_reference.source_type = row_source_type
                if hasattr(current_reference, "source_reference"):
                    current_reference.source_reference = row_source_reference
                summary = _increment(summary, updated_reference_entries=1)
                is_new_reference = False
            localization_rows = list(row.get("localizations") or [])
            if localization_rows:
                existing_localizations = [] if is_new_reference else _load_existing_reference_localizations(session, resolved_reference_localization_model, current_reference.id)
                existing_by_locale = {getattr(item, "locale", None): item for item in existing_localizations}
                for localization in localization_rows:
                    locale = str((localization or {}).get("locale") or "").strip()
                    display_form = str((localization or {}).get("display_form") or "").strip()
                    if not locale or not display_form:
                        continue
                    locale_row = existing_by_locale.get(locale)
                    if locale_row is None:
                        locale_row = resolved_reference_localization_model(
                            reference_entry_id=current_reference.id,
                            locale=locale,
                            display_form=display_form,
                            brief_description=(localization or {}).get("brief_description"),
                            translation_mode=(localization or {}).get("translation_mode"),
                        )
                        _ensure_object_id(locale_row)
                        if _is_real_mapped_model(resolved_reference_localization_model):
                            locale_row.reference_entry = current_reference
                        session.add(locale_row)
                        summary = _increment(summary, created_reference_localizations=1)
                    else:
                        locale_row.display_form = display_form
                        locale_row.brief_description = (localization or {}).get("brief_description")
                        locale_row.translation_mode = (localization or {}).get("translation_mode")
                        summary = _increment(summary, updated_reference_localizations=1)
            continue

        word_key = (str(row["word"]), row_language)
        word = preloaded_words.get(word_key)
        if word is None:
            word = _find_existing_word(session, word_model, row["word"], row_language)
            if word is not None:
                preloaded_words[word_key] = word
        if word is None:
            word = word_model(
                word=row["word"],
                language=row_language,
                frequency_rank=row.get("frequency_rank"),
                source_type=row_source_type,
                source_reference=row_source_reference,
            )
            _ensure_object_id(word)
            session.add(word)
            preloaded_words[word_key] = word
            summary = _increment(summary, created_words=1)
            is_new_word = True
        else:
            if on_conflict == "fail":
                _raise_existing_entry_conflict(entry_type="word", identifier=row["word"], language=row_language)
            if on_conflict == "skip":
                summary = _increment(summary, skipped_words=1)
                continue
            word.frequency_rank = row.get("frequency_rank")
            if hasattr(word, "source_type"):
                word.source_type = row_source_type
            if hasattr(word, "source_reference"):
                word.source_reference = row_source_reference
            summary = _increment(summary, updated_words=1)
            is_new_word = False
        use_cascaded_word_graph = is_new_word and _supports_cascaded_word_import(
            word_model,
            meaning_model,
            translation_model,
            word_relation_model,
            lexicon_enrichment_job_model,
            lexicon_enrichment_run_model,
        )

        with _session_no_autoflush(session):
            _sync_word_level_enrichment_fields(
                word,
                row,
                None,
                row_source_type,
            )
            _sync_word_confusable_rows(session, word, row, word_confusable_model)
            _sync_word_form_rows(session, word, row, word_form_model)
            _sync_word_part_of_speech_rows(session, word, row, word_part_of_speech_model)

            existing_meanings = [] if is_new_word else _load_existing_meanings(session, meaning_model, word.id)
            matched_meaning_ids: set[Any] = set()
            enrichment_job = None
            phonetic_enrichment_run = None
            is_new_enrichment_job = False

            enrichment_run_by_group: dict[tuple[str | None, str | None, str | None], Any] = {}

            if lexicon_enrichment_job_model is not None and lexicon_enrichment_run_model is not None:
                enrichment_job = None if is_new_word else _find_existing_enrichment_job(
                    session,
                    lexicon_enrichment_job_model,
                    word.id,
                    "phase1",
                )
                if enrichment_job is None:
                    enrichment_job = lexicon_enrichment_job_model(
                        word_id=word.id,
                        phase="phase1",
                        status="completed",
                        started_at=_parse_timestamp(row.get("generated_at")),
                        completed_at=_parse_timestamp(row.get("generated_at")),
                    )
                    _ensure_object_id(enrichment_job)
                    if use_cascaded_word_graph or _is_real_mapped_model(lexicon_enrichment_job_model):
                        _attach_child(word, "enrichment_jobs", enrichment_job, "word")
                    if not use_cascaded_word_graph:
                        session.add(enrichment_job)
                    summary = _increment(summary, created_enrichment_jobs=1)
                    is_new_enrichment_job = True
                else:
                    if hasattr(enrichment_job, "status"):
                        enrichment_job.status = "completed"
                    summary = _increment(summary, reused_enrichment_jobs=1)
                if hasattr(enrichment_job, "completed_at"):
                    enrichment_job.completed_at = _parse_timestamp(row.get("generated_at"))

            if enrichment_job is not None and lexicon_enrichment_run_model is not None:
                for sense in row.get("senses") or []:
                    group_key = _sense_run_group_key(sense)
                    if group_key in enrichment_run_by_group:
                        continue
                    generation_run_id, model_name, prompt_version = group_key
                    prompt_hash = _make_word_prompt_hash(
                        row_source_type,
                        row_source_reference,
                        row["word"],
                        generation_run_id,
                        model_name,
                        prompt_version,
                    )
                    enrichment_run = None if is_new_enrichment_job else _find_existing_enrichment_run(
                        session,
                        lexicon_enrichment_run_model,
                        enrichment_job.id,
                        prompt_version,
                        prompt_hash,
                    )
                    if enrichment_run is None:
                        enrichment_run = lexicon_enrichment_run_model(
                            enrichment_job_id=enrichment_job.id,
                            generator_provider=row_source_type,
                            generator_model=model_name,
                            prompt_version=prompt_version,
                            prompt_hash=prompt_hash,
                            verdict="imported",
                            confidence=_normalize_confidence(sense.get("confidence")),
                            created_at=_parse_timestamp(sense.get("generated_at") or row.get("generated_at")),
                        )
                        _ensure_object_id(enrichment_run)
                        if use_cascaded_word_graph or _is_real_mapped_model(lexicon_enrichment_run_model):
                            _attach_child(enrichment_job, "runs", enrichment_run, "enrichment_job")
                        if not use_cascaded_word_graph:
                            session.add(enrichment_run)
                        summary = _increment(summary, created_enrichment_runs=1)
                    else:
                        if hasattr(enrichment_run, "generator_provider"):
                            enrichment_run.generator_provider = row_source_type
                        if hasattr(enrichment_run, "generator_model"):
                            enrichment_run.generator_model = model_name
                        if hasattr(enrichment_run, "verdict"):
                            enrichment_run.verdict = "imported"
                        if hasattr(enrichment_run, "confidence"):
                            enrichment_run.confidence = _normalize_confidence(sense.get("confidence"))
                        summary = _increment(summary, reused_enrichment_runs=1)
                    enrichment_run_by_group[group_key] = enrichment_run

        for index, sense in enumerate(row.get("senses") or []):
            sense_source_reference = f"{row_source_reference}:{sense['sense_id']}"
            example_sentence = _first_example_sentence(sense)
            meaning = next(
                (
                    item
                    for item in existing_meanings
                    if getattr(item, "source_reference", None) == sense_source_reference
                    or getattr(item, "order_index", None) == index
                ),
                None,
            )
            if meaning is None:
                meaning = meaning_model(
                    word_id=word.id,
                    definition=sense["definition"],
                    part_of_speech=sense.get("pos"),
                    example_sentence=example_sentence,
                    order_index=index,
                    source=row_source_type,
                    source_reference=sense_source_reference,
                )
                _ensure_object_id(meaning)
                if use_cascaded_word_graph or _is_real_mapped_model(meaning_model):
                    _attach_child(word, "meanings", meaning, "word")
                if not use_cascaded_word_graph:
                    session.add(meaning)
                summary = _increment(summary, created_meanings=1)
                existing_meanings.append(meaning)
                is_new_meaning = True
            else:
                meaning.definition = sense["definition"]
                meaning.part_of_speech = sense.get("pos")
                meaning.example_sentence = example_sentence
                meaning.order_index = index
                if hasattr(meaning, "source"):
                    meaning.source = row_source_type
                if hasattr(meaning, "source_reference"):
                    meaning.source_reference = sense_source_reference
                summary = _increment(summary, updated_meanings=1)
                is_new_meaning = False
            _sync_meaning_level_learner_fields(meaning, sense, row)
            _sync_meaning_metadata_rows(session, meaning, sense, meaning_metadata_model)
            matched_meaning_ids.add(meaning.id)

            enrichment_run = None
            if enrichment_job is not None and lexicon_enrichment_run_model is not None:
                enrichment_run = enrichment_run_by_group.get(_sense_run_group_key(sense))
                if enrichment_run is not None and phonetic_enrichment_run is None:
                    phonetic_enrichment_run = enrichment_run

            _sync_word_level_enrichment_fields(
                word,
                row,
                enrichment_run,
                row_source_type,
            )

            if meaning_example_model is not None:
                existing_examples = [] if is_new_meaning else _load_existing_examples(session, meaning_example_model, meaning.id, row_source_type)
                deleted_any_examples = False
                for existing_example in existing_examples:
                    session.delete(existing_example)
                    deleted_any_examples = True
                    summary = _increment(summary, deleted_examples=1)
                if deleted_any_examples:
                    session.flush()
                seen_example_sentences: set[str] = set()
                for example_index, example in enumerate(sense.get("examples") or []):
                    sentence = str((example or {}).get("sentence") or "").strip()
                    if not sentence or sentence in seen_example_sentences:
                        continue
                    seen_example_sentences.add(sentence)
                    if bulk_insert_meaning_examples:
                        pending_meaning_example_rows.append(
                            {
                                "id": uuid.uuid4(),
                                "meaning_id": meaning.id,
                                "sentence": sentence,
                                "difficulty": (example or {}).get("difficulty"),
                                "order_index": example_index,
                                "source": row_source_type,
                                "confidence": _normalize_confidence(sense.get("confidence")),
                                "enrichment_run_id": getattr(enrichment_run, "id", None),
                            }
                        )
                    else:
                        meaning_example = meaning_example_model(
                            meaning_id=meaning.id,
                            sentence=sentence,
                            difficulty=(example or {}).get("difficulty"),
                            order_index=example_index,
                            source=row_source_type,
                            confidence=_normalize_confidence(sense.get("confidence")),
                            enrichment_run_id=getattr(enrichment_run, "id", None),
                        )
                        _ensure_object_id(meaning_example)
                        meaning_example.meaning = meaning
                        meaning_example.enrichment_run = enrichment_run
                        session.add(meaning_example)
                    summary = _increment(summary, created_examples=1)

            if translation_model is not None:
                existing_translations = {} if is_new_meaning else {
                    getattr(item, 'language', None): item
                    for item in _load_existing_translations(session, translation_model, meaning.id)
                }
                for locale, locale_payload in (sense.get('translations') or {}).items():
                    translated_definition = str((locale_payload or {}).get('definition') or '').strip()
                    if not translated_definition:
                        continue
                    translated_usage_note = str((locale_payload or {}).get('usage_note') or '').strip() or None
                    translated_examples = [
                        str(example).strip()
                        for example in ((locale_payload or {}).get('examples') or [])
                        if str(example).strip()
                    ]
                    translation = existing_translations.get(locale)
                    if translation is None:
                        translation = translation_model(
                            meaning_id=meaning.id,
                            language=locale,
                            translation=translated_definition,
                        )
                        _ensure_object_id(translation)
                        if use_cascaded_word_graph or _is_real_mapped_model(translation_model):
                            _attach_child(meaning, "translations", translation, "meaning")
                        if not use_cascaded_word_graph:
                            session.add(translation)
                        summary = _increment(summary, created_translations=1)
                    else:
                        translation.translation = translated_definition
                        summary = _increment(summary, updated_translations=1)
                    if hasattr(translation, "usage_note"):
                        translation.usage_note = translated_usage_note
                    if bulk_insert_translation_examples:
                        translation_example_delete_ids.add(translation.id)
                        for index, text in enumerate(translated_examples):
                            pending_translation_example_rows.append(
                                {
                                    "id": uuid.uuid4(),
                                    "translation_id": translation.id,
                                    "text": text,
                                    "order_index": index,
                                }
                            )
                    else:
                        _sync_translation_example_rows(translation, translated_examples, translation_example_model)

            if word_relation_model is not None:
                existing_relations = [] if is_new_meaning else _load_existing_relations(session, word_relation_model, meaning.id, row_source_type)
                deleted_any_relations = False
                for existing_relation in existing_relations:
                    session.delete(existing_relation)
                    deleted_any_relations = True
                    summary = _increment(summary, deleted_relations=1)
                if deleted_any_relations:
                    session.flush()
                seen_relations: set[tuple[str, str]] = set()
                for relation_type, source_field in SUPPORTED_RELATION_FIELDS:
                    for related_word in sense.get(source_field) or []:
                        related_text = str(related_word or "").strip()
                        relation_key = (relation_type, related_text)
                        if not related_text or relation_key in seen_relations:
                            continue
                        seen_relations.add(relation_key)
                        if bulk_insert_word_relations:
                            pending_word_relation_rows.append(
                                {
                                    "id": uuid.uuid4(),
                                    "word_id": word.id,
                                    "meaning_id": meaning.id,
                                    "relation_type": relation_type,
                                    "related_word": related_text,
                                    "related_word_id": None,
                                    "source": row_source_type,
                                    "confidence": _normalize_confidence(sense.get("confidence")),
                                    "enrichment_run_id": getattr(enrichment_run, "id", None),
                                }
                            )
                        else:
                            relation = word_relation_model(
                                word_id=word.id,
                                meaning_id=meaning.id,
                                relation_type=relation_type,
                                related_word=related_text,
                                related_word_id=None,
                                source=row_source_type,
                                confidence=_normalize_confidence(sense.get("confidence")),
                                enrichment_run_id=getattr(enrichment_run, "id", None),
                            )
                            _ensure_object_id(relation)
                            if use_cascaded_word_graph or _is_real_mapped_model(word_relation_model):
                                _attach_child(word, "relations", relation, "word")
                                if getattr(relation, "meaning", None) is None:
                                    relation.meaning = meaning
                                if enrichment_run is not None and getattr(relation, "enrichment_run", None) is None:
                                    _attach_child(enrichment_run, "word_relations", relation, "enrichment_run")
                            if not use_cascaded_word_graph:
                                session.add(relation)
                        summary = _increment(summary, created_relations=1)

        if phonetic_enrichment_run is not None and getattr(word, "phonetic", None) is not None and hasattr(word, "phonetic_enrichment_run_id"):
            session.flush()
            word.phonetic_enrichment_run_id = phonetic_enrichment_run.id

        for existing_meaning in list(existing_meanings):
            if existing_meaning.id in matched_meaning_ids:
                continue
            if getattr(existing_meaning, "source", None) != row_source_type:
                continue
            session.delete(existing_meaning)

        if progress_callback is not None:
            progress_callback(row, row_index, total_rows)

    _delete_rows_for_foreign_keys(
        session,
        translation_example_model,
        "translation_id",
        translation_example_delete_ids,
    )
    _bulk_insert_mapped_rows(session, meaning_example_model, pending_meaning_example_rows)
    _bulk_insert_mapped_rows(session, translation_example_model, pending_translation_example_rows)
    _bulk_insert_mapped_rows(session, word_relation_model, pending_word_relation_rows)

    if learner_catalog_entry_model is not None and rebuild_learner_catalog:
        resolved_phrase_model_for_projection = resolved_phrase_model
        if resolved_phrase_model_for_projection is None:
            resolved_phrase_model_for_projection = _default_phrase_models()[0]
        _rebuild_learner_catalog_projection(
            session,
            learner_catalog_entry_model=learner_catalog_entry_model,
            word_model=word_model,
            phrase_model=resolved_phrase_model_for_projection,
        )

    return summary


def load_compiled_rows(path: str | Path) -> list[dict[str, Any]]:
    return list(iter_compiled_rows(path))


def iter_compiled_rows(path: str | Path) -> Iterable[dict[str, Any]]:
    source_path = Path(path)
    if source_path.is_dir():
        compiled_paths = sorted(source_path.glob("*.enriched.jsonl"))
        if not compiled_paths:
            compiled_paths = sorted(source_path.glob("*.jsonl"))
        for compiled_path in compiled_paths:
            yield from iter_compiled_rows(compiled_path)
        return
    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def count_compiled_rows(path: str | Path) -> int:
    source_path = Path(path)
    if source_path.is_dir():
        compiled_paths = sorted(source_path.glob("*.enriched.jsonl"))
        if not compiled_paths:
            compiled_paths = sorted(source_path.glob("*.jsonl"))
        return sum(count_compiled_rows(compiled_path) for compiled_path in compiled_paths)
    count = 0
    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _iter_row_batches(rows: Iterable[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _default_source_reference(path: str | Path) -> str:
    source_path = Path(path)
    return source_path.stem or "compiled-lexicon"


def run_import_file(
    path: str | Path,
    *,
    source_type: str,
    source_reference: str | None = None,
    language: str = "en",
    rows: list[dict[str, Any]] | None = None,
    import_mode: str = "orm",
    commit_every_rows: int | None = 250,
    progress_callback: Optional[Callable[..., None]] = None,
    on_conflict: str = "upsert",
) -> dict[str, int]:
    on_conflict = _validate_on_conflict_mode(on_conflict)
    if import_mode == "staging":
        from tools.lexicon.staging_import import run_staging_import_file

        return run_staging_import_file(
            path,
            source_type=source_type,
            source_reference=source_reference,
            language=language,
            rows=rows,
            commit_every_rows=commit_every_rows,
            progress_callback=progress_callback,
            on_conflict=on_conflict,
        )

    _ensure_backend_path()
    try:
        from sqlalchemy import create_engine
    except ImportError:
        from sqlalchemy.engine.create import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    effective_source_reference = source_reference or _default_source_reference(path)
    resolved_row_total = len(rows) if rows is not None else count_compiled_rows(path)
    row_source = iter(rows) if rows is not None else iter_compiled_rows(path)
    batch_size = commit_every_rows if commit_every_rows is not None and commit_every_rows > 0 else resolved_row_total or 1
    aggregate_summary = ImportSummary()
    completed_rows = 0
    with Session(engine) as session:
        for batch in _iter_row_batches(row_source, batch_size):
            batch_summary = import_compiled_rows(
                session,
                batch,
                source_type=source_type,
                source_reference=effective_source_reference,
                language=language,
                rebuild_learner_catalog=False,
                progress_callback=(
                    (lambda row, batch_completed_rows, _batch_total_rows, base_completed_rows=completed_rows: progress_callback(
                        row=row,
                        completed_rows=base_completed_rows + batch_completed_rows,
                        total_rows=resolved_row_total,
                    ))
                    if progress_callback is not None
                    else None
                ),
                on_conflict=on_conflict,
            )
            aggregate_summary = _increment(aggregate_summary, **batch_summary.__dict__)
            completed_rows += len(batch)
            session.commit()
        if _summary_has_material_changes(aggregate_summary):
            (
                word_model,
                _meaning_model,
                _meaning_metadata_model,
                _meaning_example_model,
                _word_relation_model,
                _lexicon_enrichment_job_model,
                _lexicon_enrichment_run_model,
                _translation_model,
                _translation_example_model,
                _word_confusable_model,
                _word_form_model,
                _word_part_of_speech_model,
                learner_catalog_entry_model,
            ) = _default_models()
            phrase_model = _default_phrase_models()[0]
            _rebuild_learner_catalog_projection(
                session,
                learner_catalog_entry_model=learner_catalog_entry_model,
                word_model=word_model,
                phrase_model=phrase_model,
            )
            session.commit()
    return {
        "created_words": aggregate_summary.created_words,
        "updated_words": aggregate_summary.updated_words,
        "skipped_words": aggregate_summary.skipped_words,
        "created_meanings": aggregate_summary.created_meanings,
        "updated_meanings": aggregate_summary.updated_meanings,
        "created_examples": aggregate_summary.created_examples,
        "deleted_examples": aggregate_summary.deleted_examples,
        "created_relations": aggregate_summary.created_relations,
        "deleted_relations": aggregate_summary.deleted_relations,
        "created_translations": aggregate_summary.created_translations,
        "updated_translations": aggregate_summary.updated_translations,
        "created_enrichment_jobs": aggregate_summary.created_enrichment_jobs,
        "reused_enrichment_jobs": aggregate_summary.reused_enrichment_jobs,
        "created_enrichment_runs": aggregate_summary.created_enrichment_runs,
        "reused_enrichment_runs": aggregate_summary.reused_enrichment_runs,
        "created_phrases": aggregate_summary.created_phrases,
        "updated_phrases": aggregate_summary.updated_phrases,
        "skipped_phrases": aggregate_summary.skipped_phrases,
        "created_reference_entries": aggregate_summary.created_reference_entries,
        "updated_reference_entries": aggregate_summary.updated_reference_entries,
        "skipped_reference_entries": aggregate_summary.skipped_reference_entries,
        "created_reference_localizations": aggregate_summary.created_reference_localizations,
        "updated_reference_localizations": aggregate_summary.updated_reference_localizations,
    }


def summarize_compiled_rows(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("entry_type") or "word").strip() or "word" for row in rows)
    return {
        "row_count": sum(counts.values()),
        "word_count": counts.get("word", 0),
        "phrase_count": counts.get("phrase", 0),
        "reference_count": counts.get("reference", 0),
    }
