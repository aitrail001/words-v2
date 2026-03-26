import uuid
from collections import defaultdict
from collections.abc import Mapping
from collections.abc import Sequence
import re

from sqlalchemy import and_, cast, func, literal, or_, select, union_all
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import DetachedInstanceError

from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization
from app.models.phrase_sense_localization import PhraseSenseLocalization
from app.models.search_history import SearchHistory
from app.models.translation import Translation
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.models.word_relation import WordRelation

DEFAULT_ACCENT = "us"
DEFAULT_TRANSLATION_LOCALE = "zh-Hans"
DEFAULT_VIEW = "cards"
SUPPORTED_TRANSLATION_LOCALES = ("ar", "es", "ja", "pt-BR", "zh-Hans")
STATUS_VALUES = ("undecided", "to_learn", "learning", "known")
ENTRY_TYPES = ("word", "phrase")
BUCKET_SIZE = 100
UNRANKED_BASE = 1_000_000
LIST_STATUS_VALUES = ("new", "to_learn", "learning", "known")
LIST_SORT_VALUES = ("rank", "rank_desc", "alpha")


def _mapping_value(row: object, key: str) -> object:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key)


def _word_id(row: object) -> uuid.UUID:
    return _mapping_value(row, "id")  # type: ignore[return-value]


def _word_text(row: object) -> str:
    return str(_mapping_value(row, "word") or "")


def _word_frequency_rank(row: object) -> int | None:
    value = _mapping_value(row, "frequency_rank")
    return value if isinstance(value, int) else None


def _word_cefr_level(row: object) -> str | None:
    value = _mapping_value(row, "cefr_level")
    return value if isinstance(value, str) else None


def _word_part_of_speech(row: object) -> str | None:
    value = _mapping_value(row, "learner_part_of_speech")
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None


def _phrase_id(row: object) -> uuid.UUID:
    return _mapping_value(row, "id")  # type: ignore[return-value]


def _phrase_text(row: object) -> str:
    return str(_mapping_value(row, "phrase_text") or "")


def _phrase_normalized_form(row: object) -> str:
    return str(_mapping_value(row, "normalized_form") or "")


def _phrase_cefr_level(row: object) -> str | None:
    value = _mapping_value(row, "cefr_level")
    return value if isinstance(value, str) else None


def _phrase_kind(row: object) -> str | None:
    value = _mapping_value(row, "phrase_kind")
    return value if isinstance(value, str) else None


def _catalog_word_row(row: object) -> Mapping[str, object]:
    return {
        "id": _word_id(row),
        "word": _word_text(row),
        "frequency_rank": _word_frequency_rank(row),
        "cefr_level": _word_cefr_level(row),
        "learner_part_of_speech": _mapping_value(row, "learner_part_of_speech"),
    }


def _catalog_phrase_row(row: object) -> Mapping[str, object]:
    return {
        "id": _phrase_id(row),
        "phrase_text": _phrase_text(row),
        "normalized_form": _phrase_normalized_form(row),
        "cefr_level": _phrase_cefr_level(row),
        "phrase_kind": _phrase_kind(row),
    }


def _result_rows(result: object, serializer) -> list[Mapping[str, object]]:
    mappings = getattr(result, "mappings", None)
    if callable(mappings):
        rows = mappings().all()
        if isinstance(rows, list):
            return rows

    scalars = getattr(result, "scalars", None)
    if callable(scalars):
        rows = scalars().all()
        if isinstance(rows, list):
            return [serializer(row) for row in rows]

    return []


def default_preferences() -> UserPreference:
    return UserPreference(
        user_id=uuid.uuid4(),
        accent_preference=DEFAULT_ACCENT,
        translation_locale=DEFAULT_TRANSLATION_LOCALE,
        knowledge_view_preference=DEFAULT_VIEW,
        show_translations_by_default=True,
    )


async def get_preferences(db: AsyncSession, user_id: uuid.UUID) -> UserPreference:
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    return result.scalar_one_or_none() or default_preferences()


async def load_status_map(db: AsyncSession, user_id: uuid.UUID) -> dict[tuple[str, uuid.UUID], str]:
    result = await db.execute(select(LearnerEntryStatus).where(LearnerEntryStatus.user_id == user_id))
    rows = result.scalars().all()
    return {(row.entry_type, row.entry_id): row.status for row in rows}


async def load_status_map_for_entries(
    db: AsyncSession,
    user_id: uuid.UUID,
    items: Sequence[dict[str, object]],
) -> dict[tuple[str, uuid.UUID], str]:
    word_ids = [item["entry_id"] for item in items if item["entry_type"] == "word"]
    phrase_ids = [item["entry_id"] for item in items if item["entry_type"] == "phrase"]
    filters = []
    if word_ids:
        filters.append(
            and_(
                LearnerEntryStatus.entry_type == "word",
                LearnerEntryStatus.entry_id.in_(word_ids),
            )
        )
    if phrase_ids:
        filters.append(
            and_(
                LearnerEntryStatus.entry_type == "phrase",
                LearnerEntryStatus.entry_id.in_(phrase_ids),
            )
        )
    if not filters:
        return {}

    result = await db.execute(
        select(LearnerEntryStatus).where(
            LearnerEntryStatus.user_id == user_id,
            or_(*filters),
        )
    )
    rows = result.scalars().all()
    return {(row.entry_type, row.entry_id): row.status for row in rows}


def bucket_start_for_rank(rank: int) -> int:
    return ((rank - 1) // BUCKET_SIZE) * BUCKET_SIZE + 1


def normalize_word_rank(word: Word, fallback_rank: int) -> int:
    return word.frequency_rank if word.frequency_rank is not None else fallback_rank


def extract_phrase_primary_definition(entry: PhraseEntry) -> str | None:
    payload = entry.compiled_payload if isinstance(entry.compiled_payload, dict) else {}
    senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    if not senses:
        return None
    first = senses[0] if isinstance(senses[0], dict) else {}
    value = first.get("definition")
    return value.strip() if isinstance(value, str) and value.strip() else None


def extract_phrase_translation(entry: PhraseEntry, locale: str) -> str | None:
    payload = entry.compiled_payload if isinstance(entry.compiled_payload, dict) else {}
    senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    for raw_sense in senses:
        sense = raw_sense if isinstance(raw_sense, dict) else {}
        translations = sense.get("translations") if isinstance(sense.get("translations"), dict) else {}
        locale_payload = translations.get(locale) if isinstance(translations.get(locale), dict) else {}
        definition = locale_payload.get("definition")
        if isinstance(definition, str) and definition.strip():
            return definition.strip()
    return None


def select_pronunciation(word: Word, accent: str) -> str | None:
    phonetics = word.phonetics if isinstance(word.phonetics, dict) else {}
    candidates = [accent, DEFAULT_ACCENT, "uk", "au"]
    seen: set[str] = set()
    for key in candidates:
        if key in seen:
            continue
        seen.add(key)
        value = phonetics.get(key) if isinstance(phonetics.get(key), dict) else {}
        ipa = value.get("ipa")
        if isinstance(ipa, str) and ipa.strip():
            return ipa.strip()
    if isinstance(word.phonetic, str) and word.phonetic.strip():
        return word.phonetic.strip()
    return None


def build_word_translation_map(translations: Sequence[Translation], locale: str) -> dict[uuid.UUID, str]:
    translation_map: dict[uuid.UUID, str] = {}
    for translation in translations:
        if translation.language == locale and translation.meaning_id not in translation_map:
            translation_map[translation.meaning_id] = translation.translation
    return translation_map


def normalize_confusable_words(word: Word) -> list[dict[str, str | None]]:
    try:
        confusable_entries = getattr(word, "confusable_entries", None)
    except (MissingGreenlet, DetachedInstanceError):
        confusable_entries = None
    if isinstance(confusable_entries, list) and confusable_entries:
        return [
            {
                "word": str(item.confusable_word).strip(),
                "note": item.note.strip() if isinstance(item.note, str) and item.note.strip() else None,
            }
            for item in confusable_entries
            if isinstance(getattr(item, "confusable_word", None), str) and str(item.confusable_word).strip()
        ]

    raw_confusables = word.confusable_words if isinstance(word.confusable_words, list) else []
    items: list[dict[str, str | None]] = []
    for raw_item in raw_confusables:
        if not isinstance(raw_item, dict):
            continue
        raw_word = raw_item.get("word")
        if not isinstance(raw_word, str) or not raw_word.strip():
            continue
        raw_note = raw_item.get("note")
        note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None
        items.append({"word": raw_word.strip(), "note": note})
    return items


def normalize_word_forms(word: Word) -> dict[str, object]:
    try:
        form_entries = getattr(word, "form_entries", None)
    except (MissingGreenlet, DetachedInstanceError):
        form_entries = None
    if isinstance(form_entries, list) and form_entries:
        verb_forms = {
            "base": "",
            "past": "",
            "gerund": "",
            "past_participle": "",
            "third_person_singular": "",
        }
        plural_forms: list[str] = []
        derivations: list[str] = []
        comparative: str | None = None
        superlative: str | None = None
        for item in sorted(
            form_entries,
            key=lambda entry: (
                str(getattr(entry, "form_kind", "")),
                int(getattr(entry, "order_index", 0) or 0),
                str(getattr(entry, "form_slot", "")),
            ),
        ):
            form_kind = str(getattr(item, "form_kind", "") or "").strip()
            form_slot = str(getattr(item, "form_slot", "") or "").strip()
            value = str(getattr(item, "value", "") or "").strip()
            if not form_kind or not value:
                continue
            if form_kind == "verb" and form_slot in verb_forms:
                verb_forms[form_slot] = value
            elif form_kind == "plural":
                plural_forms.append(value)
            elif form_kind == "derivation":
                derivations.append(value)
            elif form_kind == "comparative" and comparative is None:
                comparative = value
            elif form_kind == "superlative" and superlative is None:
                superlative = value
        return {
            "verb_forms": verb_forms,
            "plural_forms": plural_forms,
            "derivations": derivations,
            "comparative": comparative,
            "superlative": superlative,
        }

    forms = word.word_forms if isinstance(word.word_forms, dict) else {}
    verb_forms = forms.get("verb_forms") if isinstance(forms.get("verb_forms"), dict) else {}
    plural_forms = [str(item).strip() for item in forms.get("plural_forms", []) if str(item).strip()]
    derivations = [str(item).strip() for item in forms.get("derivations", []) if str(item).strip()]
    comparative = forms.get("comparative")
    superlative = forms.get("superlative")
    return {
        "verb_forms": {
            "base": str(verb_forms.get("base") or "").strip(),
            "past": str(verb_forms.get("past") or "").strip(),
            "gerund": str(verb_forms.get("gerund") or "").strip(),
            "past_participle": str(verb_forms.get("past_participle") or "").strip(),
            "third_person_singular": str(verb_forms.get("third_person_singular") or "").strip(),
        },
        "plural_forms": plural_forms,
        "derivations": derivations,
        "comparative": comparative.strip() if isinstance(comparative, str) and comparative.strip() else None,
        "superlative": superlative.strip() if isinstance(superlative, str) and superlative.strip() else None,
    }


def normalize_translation_examples(translation: Translation) -> list[str]:
    try:
        example_entries = getattr(translation, "example_entries", None)
    except (MissingGreenlet, DetachedInstanceError):
        example_entries = None
    if isinstance(example_entries, list) and example_entries:
        return [
            str(getattr(item, "text", "") or "").strip()
            for item in example_entries
            if str(getattr(item, "text", "") or "").strip()
        ]

    raw_examples = getattr(translation, "examples", None)
    if not isinstance(raw_examples, list):
        return []
    return [str(item).strip() for item in raw_examples if str(item).strip()]


def normalize_meaning_metadata(meaning: Meaning) -> dict[str, list[str]]:
    try:
        metadata_entries = getattr(meaning, "metadata_entries", None)
    except (MissingGreenlet, DetachedInstanceError):
        metadata_entries = None
    if isinstance(metadata_entries, list) and metadata_entries:
        secondary_domains = [
            str(getattr(item, "value", "") or "").strip()
            for item in metadata_entries
            if str(getattr(item, "metadata_kind", "") or "").strip() == "secondary_domain"
            and str(getattr(item, "value", "") or "").strip()
        ]
        grammar_patterns = [
            str(getattr(item, "value", "") or "").strip()
            for item in metadata_entries
            if str(getattr(item, "metadata_kind", "") or "").strip() == "grammar_pattern"
            and str(getattr(item, "value", "") or "").strip()
        ]
        return {
            "secondary_domains": secondary_domains,
            "grammar_patterns": grammar_patterns,
        }

    return {
        "secondary_domains": list(meaning.secondary_domains or []),
        "grammar_patterns": list(meaning.grammar_patterns or []),
    }


def _clean_text(value: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if isinstance(item, str) and str(item).strip()]


async def load_phrase_summary_map(
    db: AsyncSession,
    phrase_ids: Sequence[uuid.UUID],
    locale: str,
) -> dict[uuid.UUID, dict[str, str | None]]:
    if not phrase_ids:
        return {}

    summary_rows: dict[uuid.UUID, dict[str, str | None]] = {}
    senses_result = await db.execute(
        select(PhraseSense)
        .where(PhraseSense.phrase_entry_id.in_(phrase_ids))
        .order_by(PhraseSense.phrase_entry_id.asc(), PhraseSense.order_index.asc())
    )
    senses = senses_result.scalars().all()
    sense_ids = [sense.id for sense in senses]

    localized_map: dict[uuid.UUID, PhraseSenseLocalization] = {}
    if sense_ids:
        localized_result = await db.execute(
            select(PhraseSenseLocalization)
            .where(
                PhraseSenseLocalization.phrase_sense_id.in_(sense_ids),
                PhraseSenseLocalization.locale == locale,
            )
            .order_by(PhraseSenseLocalization.phrase_sense_id.asc())
        )
        for localized in localized_result.scalars().all():
            localized_map[localized.phrase_sense_id] = localized

    for sense in senses:
        row = summary_rows.setdefault(
            sense.phrase_entry_id,
            {"primary_definition": None, "translation": None},
        )
        if row["primary_definition"] is None:
            row["primary_definition"] = _clean_text(sense.definition)
        if row["translation"] is None:
            localized = localized_map.get(sense.id)
            if localized is not None:
                row["translation"] = _clean_text(localized.localized_definition)

    return summary_rows


async def load_phrase_detail_rows(
    db: AsyncSession,
    phrase_id: uuid.UUID,
    locale: str,
) -> tuple[list[PhraseSense], dict[uuid.UUID, PhraseSenseLocalization], dict[uuid.UUID, list[PhraseSenseExample]], dict[uuid.UUID, PhraseSenseExampleLocalization]]:
    senses_result = await db.execute(
        select(PhraseSense)
        .where(PhraseSense.phrase_entry_id == phrase_id)
        .order_by(PhraseSense.order_index.asc())
    )
    senses = senses_result.scalars().all()
    sense_ids = [sense.id for sense in senses]

    sense_localizations: dict[uuid.UUID, PhraseSenseLocalization] = {}
    if sense_ids:
        sense_localization_result = await db.execute(
            select(PhraseSenseLocalization)
            .where(
                PhraseSenseLocalization.phrase_sense_id.in_(sense_ids),
                PhraseSenseLocalization.locale == locale,
            )
            .order_by(PhraseSenseLocalization.phrase_sense_id.asc())
        )
        for localized in sense_localization_result.scalars().all():
            sense_localizations[localized.phrase_sense_id] = localized

    examples_by_sense: dict[uuid.UUID, list[PhraseSenseExample]] = defaultdict(list)
    example_ids: list[uuid.UUID] = []
    if sense_ids:
        examples_result = await db.execute(
            select(PhraseSenseExample)
            .where(PhraseSenseExample.phrase_sense_id.in_(sense_ids))
            .order_by(PhraseSenseExample.phrase_sense_id.asc(), PhraseSenseExample.order_index.asc())
        )
        for example in examples_result.scalars().all():
            examples_by_sense[example.phrase_sense_id].append(example)
            example_ids.append(example.id)

    example_localizations: dict[uuid.UUID, PhraseSenseExampleLocalization] = {}
    if example_ids:
        example_localization_result = await db.execute(
            select(PhraseSenseExampleLocalization)
            .where(
                PhraseSenseExampleLocalization.phrase_sense_example_id.in_(example_ids),
                PhraseSenseExampleLocalization.locale == locale,
            )
            .order_by(PhraseSenseExampleLocalization.phrase_sense_example_id.asc())
        )
        for localized in example_localization_result.scalars().all():
            example_localizations[localized.phrase_sense_example_id] = localized

    return senses, sense_localizations, examples_by_sense, example_localizations


def load_phrase_compiled_senses(entry: PhraseEntry) -> list[dict[str, object]]:
    payload = entry.compiled_payload if isinstance(entry.compiled_payload, dict) else {}
    senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    return [sense if isinstance(sense, dict) else {} for sense in senses]


def extract_phrase_legacy_metadata(sense: dict[str, object]) -> dict[str, object]:
    return {
        "part_of_speech": _clean_text(sense.get("pos") if isinstance(sense.get("pos"), str) else sense.get("part_of_speech")),
        "register": _clean_text(sense.get("register") if isinstance(sense.get("register"), str) else None),
        "primary_domain": _clean_text(sense.get("primary_domain") if isinstance(sense.get("primary_domain"), str) else None),
        "secondary_domains": _normalize_string_list(sense.get("secondary_domains")),
        "grammar_patterns": _normalize_string_list(sense.get("grammar_patterns")),
        "synonyms": _normalize_string_list(sense.get("synonyms")),
        "antonyms": _normalize_string_list(sense.get("antonyms")),
        "collocations": _normalize_string_list(sense.get("collocations")),
    }


def _phrase_sense_match_signature(sense: dict[str, object]) -> tuple[str | None, str | None]:
    definition = _clean_text(sense.get("definition") if isinstance(sense.get("definition"), str) else None)
    usage_note = _clean_text(sense.get("usage_note") if isinstance(sense.get("usage_note"), str) else None)
    return definition, usage_note


def build_phrase_legacy_metadata_map(
    senses: Sequence[PhraseSense],
    compiled_senses: Sequence[dict[str, object]],
) -> dict[uuid.UUID, dict[str, object]]:
    if not senses or not compiled_senses:
        return {}

    compiled_entries: list[dict[str, object]] = []
    entries_by_signature: dict[tuple[str | None, str | None], list[int]] = defaultdict(list)
    entries_by_definition: dict[str, list[int]] = defaultdict(list)
    entries_by_usage_note: dict[str, list[int]] = defaultdict(list)

    for index, compiled_sense in enumerate(compiled_senses):
        sense = compiled_sense if isinstance(compiled_sense, dict) else {}
        signature = _phrase_sense_match_signature(sense)
        compiled_entries.append(
            {
                "signature": signature,
                "metadata": extract_phrase_legacy_metadata(sense),
            }
        )
        entries_by_signature[signature].append(index)
        if signature[0] is not None:
            entries_by_definition[signature[0]].append(index)
        if signature[1] is not None:
            entries_by_usage_note[signature[1]].append(index)

    used_indexes: set[int] = set()
    metadata_by_sense_id: dict[uuid.UUID, dict[str, object]] = {}

    def take_candidate(indexes: list[int]) -> dict[str, object] | None:
        for index in indexes:
            if index in used_indexes:
                continue
            used_indexes.add(index)
            return compiled_entries[index]["metadata"]  # type: ignore[return-value]
        return None

    for sense in senses:
        definition = _clean_text(sense.definition)
        usage_note = _clean_text(sense.usage_note)
        metadata = (
            take_candidate(entries_by_signature.get((definition, usage_note), []))
            or (definition is not None and take_candidate(entries_by_definition.get(definition, [])))
            or (usage_note is not None and take_candidate(entries_by_usage_note.get(usage_note, [])))
        )
        metadata_by_sense_id[sense.id] = metadata or extract_phrase_legacy_metadata({})

    return metadata_by_sense_id


def build_entry_lookup(
    words: Sequence[object],
    phrases: Sequence[object],
) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for word in words:
        text = _word_text(word).strip()
        normalized = text.lower()
        if normalized and normalized not in lookup:
            lookup[normalized] = {
                "entry_type": "word",
                "entry_id": str(_word_id(word)),
                "display_text": text,
            }
    for phrase in phrases:
        phrase_text = _phrase_text(phrase).strip()
        normalized_form = _phrase_normalized_form(phrase).strip()
        for raw_value in (normalized_form, phrase_text):
            normalized = raw_value.strip().lower()
            if normalized and normalized not in lookup:
                lookup[normalized] = {
                    "entry_type": "phrase",
                    "entry_id": str(_phrase_id(phrase)),
                    "display_text": phrase_text,
                }
    return lookup


def resolve_exact_match_target(
    value: str | None,
    lookup: dict[str, dict[str, object]],
) -> dict[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    target = lookup.get(value.strip().lower())
    if target is None:
        return None
    return {
        "entry_type": str(target["entry_type"]),
        "entry_id": str(target["entry_id"]),
        "display_text": str(target["display_text"]),
    }


def find_example_links(
    sentence: str | None,
    lookup: dict[str, dict[str, object]],
    *,
    excluded_terms: Sequence[str] = (),
) -> list[dict[str, str]]:
    if not isinstance(sentence, str) or not sentence.strip():
        return []
    excluded = {term.strip().lower() for term in excluded_terms if isinstance(term, str) and term.strip()}
    tokens = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", sentence)
    results: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index in range(len(tokens)):
        for width in range(1, 0, -1):
            chunk = tokens[index:index + width]
            if len(chunk) != width:
                continue
            phrase = " ".join(chunk)
            normalized = phrase.lower()
            if normalized in excluded:
                continue
            target = lookup.get(normalized)
            if target is None:
                continue
            key = (normalized, str(target["entry_id"]))
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "text": phrase,
                    "entry_type": str(target["entry_type"]),
                    "entry_id": str(target["entry_id"]),
                }
            )
            break
    return results


def phrase_locale_payload(sense: dict[str, object], locale: str) -> dict[str, object]:
    translations = sense.get("translations") if isinstance(sense.get("translations"), dict) else {}
    payload = translations.get(locale)
    return payload if isinstance(payload, dict) else {}


def relation_terms(
    relations: Sequence[WordRelation],
    relation_type: str,
    lookup: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for relation in relations:
        current_relation_type = relation.relation_type.strip().lower() if isinstance(relation.relation_type, str) else ""
        if current_relation_type != relation_type:
            continue
        text = relation.related_word.strip() if isinstance(relation.related_word, str) else ""
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({"text": text, "target": resolve_exact_match_target(text, lookup)})
    return items


def build_relation_groups(relations_by_meaning: dict[uuid.UUID, list[WordRelation]]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for relations in relations_by_meaning.values():
        for relation in relations:
            raw_relation_type = relation.relation_type.strip() if isinstance(relation.relation_type, str) else ""
            raw_related_word = relation.related_word.strip() if isinstance(relation.related_word, str) else ""
            relation_type = raw_relation_type.lower()
            related_word_key = raw_related_word.lower()
            if not relation_type or not related_word_key:
                continue
            key = (relation_type, related_word_key)
            if key in seen:
                continue
            seen.add(key)
            grouped[relation_type].append(raw_related_word)

    return [
        {"relation_type": relation_type, "related_words": related_words}
        for relation_type, related_words in sorted(grouped.items())
    ]


async def build_catalog(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    q: str | None = None,
    status: str | None = None,
    sort: str = "rank",
    limit: int | None = None,
) -> list[dict]:
    catalog = _catalog_projection_cte()
    status_expr = func.coalesce(LearnerEntryStatus.status, literal("undecided"))
    query = (
        select(
            catalog.c.entry_type,
            catalog.c.entry_id,
            catalog.c.display_text,
            catalog.c.normalized_form,
            catalog.c.browse_rank,
            catalog.c.cefr_level,
            catalog.c.learner_part_of_speech,
            catalog.c.phrase_kind,
            status_expr.label("status"),
        )
        .select_from(
            catalog.outerjoin(
                LearnerEntryStatus,
                and_(
                    LearnerEntryStatus.user_id == user_id,
                    LearnerEntryStatus.entry_type == catalog.c.entry_type,
                    LearnerEntryStatus.entry_id == catalog.c.entry_id,
                ),
            )
        )
    )

    mapped_status = "undecided" if status == "new" else status
    if mapped_status:
        query = query.where(status_expr == mapped_status)

    lowered = q.strip().lower() if isinstance(q, str) and q.strip() else None
    if lowered:
        query = query.where(
            or_(
                func.lower(catalog.c.display_text).contains(lowered),
                func.lower(catalog.c.normalized_form).contains(lowered),
            )
        )

    if sort == "rank_desc":
        query = query.order_by(catalog.c.browse_rank.desc(), func.lower(catalog.c.display_text).asc())
    elif sort == "alpha":
        query = query.order_by(func.lower(catalog.c.display_text).asc(), catalog.c.browse_rank.asc())
    else:
        query = query.order_by(catalog.c.browse_rank.asc(), func.lower(catalog.c.display_text).asc())

    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    items: list[dict] = []
    for raw_item in result.mappings().all():
        learner_pos = raw_item.get("learner_part_of_speech")
        part_of_speech = learner_pos[0] if isinstance(learner_pos, list) and learner_pos else None
        items.append(
            {
                "entry_type": str(raw_item["entry_type"]),
                "entry_id": raw_item["entry_id"],
                "display_text": str(raw_item["display_text"]),
                "normalized_form": raw_item["normalized_form"],
                "browse_rank": int(raw_item["browse_rank"]),
                "status": str(raw_item["status"]),
                "cefr_level": raw_item.get("cefr_level"),
                "pronunciation": None,
                "translation": None,
                "primary_definition": None,
                "part_of_speech": part_of_speech,
                "phrase_kind": raw_item.get("phrase_kind"),
            }
        )
    return items


async def load_catalog_rows(
    db: AsyncSession,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    words_result = await db.execute(
        select(
            Word.id.label("id"),
            Word.word.label("word"),
            Word.frequency_rank.label("frequency_rank"),
            Word.cefr_level.label("cefr_level"),
            Word.learner_part_of_speech.label("learner_part_of_speech"),
        )
    )
    phrases_result = await db.execute(
        select(
            PhraseEntry.id.label("id"),
            PhraseEntry.phrase_text.label("phrase_text"),
            PhraseEntry.normalized_form.label("normalized_form"),
            PhraseEntry.cefr_level.label("cefr_level"),
            PhraseEntry.phrase_kind.label("phrase_kind"),
        )
    )
    return (
        _result_rows(words_result, _catalog_word_row),
        _result_rows(phrases_result, _catalog_phrase_row),
    )


def _catalog_projection_cte():
    max_ranked_word_rank = (
        select(func.coalesce(func.max(Word.frequency_rank), 0))
        .where(Word.frequency_rank.is_not(None))
        .scalar_subquery()
    )
    unranked_word_offset = (
        func.row_number().over(
            order_by=(func.lower(Word.word).asc(), Word.id.asc()),
        )
    )
    unranked_word_count = (
        select(func.count())
        .select_from(Word)
        .where(Word.frequency_rank.is_(None))
        .scalar_subquery()
    )
    phrase_offset = (
        func.row_number().over(
            order_by=(func.lower(PhraseEntry.normalized_form).asc(), PhraseEntry.id.asc()),
        )
    )

    ranked_words = select(
        literal("word").label("entry_type"),
        Word.id.label("entry_id"),
        Word.word.label("display_text"),
        Word.word.label("normalized_form"),
        Word.frequency_rank.label("browse_rank"),
        Word.cefr_level.label("cefr_level"),
        Word.learner_part_of_speech.label("learner_part_of_speech"),
        cast(literal(None), PhraseEntry.phrase_kind.type).label("phrase_kind"),
    ).where(Word.frequency_rank.is_not(None))

    unranked_words = select(
        literal("word").label("entry_type"),
        Word.id.label("entry_id"),
        Word.word.label("display_text"),
        Word.word.label("normalized_form"),
        (max_ranked_word_rank + unranked_word_offset).label("browse_rank"),
        Word.cefr_level.label("cefr_level"),
        Word.learner_part_of_speech.label("learner_part_of_speech"),
        cast(literal(None), PhraseEntry.phrase_kind.type).label("phrase_kind"),
    ).where(Word.frequency_rank.is_(None))

    phrases = select(
        literal("phrase").label("entry_type"),
        PhraseEntry.id.label("entry_id"),
        PhraseEntry.phrase_text.label("display_text"),
        PhraseEntry.normalized_form.label("normalized_form"),
        (max_ranked_word_rank + unranked_word_count + phrase_offset).label("browse_rank"),
        PhraseEntry.cefr_level.label("cefr_level"),
        cast(literal(None), Word.learner_part_of_speech.type).label("learner_part_of_speech"),
        PhraseEntry.phrase_kind.label("phrase_kind"),
    )

    return union_all(ranked_words, unranked_words, phrases).cte("knowledge_catalog_projection")


async def load_range_catalog_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    range_start: int,
) -> dict[str, object]:
    range_end = range_start + BUCKET_SIZE - 1
    catalog = _catalog_projection_cte()
    items_result = await db.execute(
        select(catalog)
        .where(
            catalog.c.browse_rank >= range_start,
            catalog.c.browse_rank <= range_end,
        )
        .order_by(catalog.c.browse_rank.asc(), catalog.c.display_text.asc())
    )
    raw_items = [dict(row) for row in items_result.mappings().all()]

    bounds_result = await db.execute(
        select(
            select(func.max(catalog.c.browse_rank))
            .where(catalog.c.browse_rank < range_start)
            .scalar_subquery()
            .label("previous_rank"),
            select(func.min(catalog.c.browse_rank))
            .where(catalog.c.browse_rank > range_end)
            .scalar_subquery()
            .label("next_rank"),
        )
    )
    bounds = bounds_result.mappings().one()

    status_map = await load_status_map_for_entries(db, user_id, raw_items)
    items: list[dict[str, object]] = []
    for raw_item in raw_items:
        learner_pos = raw_item.get("learner_part_of_speech")
        part_of_speech = learner_pos[0] if isinstance(learner_pos, list) and learner_pos else None
        items.append(
            {
                "entry_type": str(raw_item["entry_type"]),
                "entry_id": raw_item["entry_id"],
                "display_text": str(raw_item["display_text"]),
                "normalized_form": raw_item["normalized_form"],
                "browse_rank": int(raw_item["browse_rank"]),
                "status": status_map.get((str(raw_item["entry_type"]), raw_item["entry_id"]), "undecided"),
                "cefr_level": raw_item.get("cefr_level"),
                "pronunciation": None,
                "translation": None,
                "primary_definition": None,
                "part_of_speech": part_of_speech,
                "phrase_kind": raw_item.get("phrase_kind"),
            }
        )

    previous_rank = bounds.get("previous_rank")
    next_rank = bounds.get("next_rank")
    return {
        "range_start": range_start,
        "range_end": range_end,
        "previous_range_start": bucket_start_for_rank(int(previous_rank)) if previous_rank is not None else None,
        "next_range_start": bucket_start_for_rank(int(next_rank)) if next_rank is not None else None,
        "items": items,
    }


def build_catalog_items(
    words: Sequence[object],
    phrases: Sequence[object],
    *,
    status_map: dict[tuple[str, uuid.UUID], str] | None = None,
    q: str | None = None,
) -> list[dict]:
    status_map = status_map or {}
    ranked_words = sorted(
        words,
        key=lambda word: (
            _word_frequency_rank(word) if _word_frequency_rank(word) is not None else UNRANKED_BASE,
            _word_text(word).lower(),
            str(_word_id(word)),
        ),
    )
    next_rank = max((_word_frequency_rank(word) or 0) for word in ranked_words) + 1 if ranked_words else 1

    items: list[dict] = []
    for word in ranked_words:
        frequency_rank = _word_frequency_rank(word)
        browse_rank = frequency_rank if frequency_rank is not None else next_rank
        next_rank = max(next_rank, browse_rank + 1)
        item = {
            "entry_type": "word",
            "entry_id": _word_id(word),
            "display_text": _word_text(word),
            "normalized_form": _word_text(word),
            "browse_rank": browse_rank,
            "status": status_map.get(("word", _word_id(word)), "undecided"),
            "cefr_level": _word_cefr_level(word),
            "pronunciation": None,
            "translation": None,
            "primary_definition": None,
            "part_of_speech": _word_part_of_speech(word),
            "phrase_kind": None,
        }
        items.append(item)

    phrase_entries = sorted(
        phrases,
        key=lambda entry: (_phrase_normalized_form(entry).lower(), str(_phrase_id(entry))),
    )
    for entry in phrase_entries:
        item = {
            "entry_type": "phrase",
            "entry_id": _phrase_id(entry),
            "display_text": _phrase_text(entry),
            "normalized_form": _phrase_normalized_form(entry),
            "browse_rank": next_rank,
            "status": status_map.get(("phrase", _phrase_id(entry)), "undecided"),
            "cefr_level": _phrase_cefr_level(entry),
            "pronunciation": None,
            "translation": None,
            "primary_definition": None,
            "part_of_speech": None,
            "phrase_kind": _phrase_kind(entry),
        }
        next_rank += 1
        items.append(item)

    if q:
        lowered = q.lower()
        items = [
            item
            for item in items
            if lowered in (item["display_text"] or "").lower()
            or lowered in (item["normalized_form"] or "").lower()
        ]

    return sorted(items, key=lambda item: (item["browse_rank"], item["display_text"]))


def build_overview(items: Sequence[dict]) -> dict:
    buckets: dict[int, dict] = {}
    for item in items:
        start = bucket_start_for_rank(item["browse_rank"])
        bucket = buckets.setdefault(
            start,
            {
                "range_start": start,
                "range_end": start + BUCKET_SIZE - 1,
                "total_entries": 0,
                "counts": {status: 0 for status in STATUS_VALUES},
            },
        )
        bucket["total_entries"] += 1
        bucket["counts"][item["status"]] += 1

    return {
        "bucket_size": BUCKET_SIZE,
        "total_entries": len(items),
        "ranges": [buckets[key] for key in sorted(buckets)],
    }


def filter_catalog_items(
    items: Sequence[dict],
    *,
    status: str | None = None,
    q: str | None = None,
) -> list[dict]:
    filtered = list(items)

    if status:
        mapped_status = "undecided" if status == "new" else status
        filtered = [item for item in filtered if item["status"] == mapped_status]

    if q:
        lowered = q.strip().lower()
        if lowered:
            filtered = [
                item
                for item in filtered
                if lowered in (item["display_text"] or "").lower()
                or lowered in (item["normalized_form"] or "").lower()
            ]

    return filtered


def sort_catalog_items(items: Sequence[dict], sort: str) -> list[dict]:
    if sort == "rank_desc":
        return sorted(items, key=lambda item: (-item["browse_rank"], item["display_text"].lower()))
    if sort == "alpha":
        return sorted(items, key=lambda item: (item["display_text"].lower(), item["browse_rank"]))
    return sorted(items, key=lambda item: (item["browse_rank"], item["display_text"].lower()))


def build_dashboard_summary(items: Sequence[dict]) -> dict:
    counts = {status: 0 for status in STATUS_VALUES}
    for item in items:
        counts[item["status"]] += 1

    discovery_entry = next((item for item in items if item["status"] != "known"), None)
    discovery_range_start = (
        bucket_start_for_rank(discovery_entry["browse_rank"])
        if discovery_entry is not None
        else (bucket_start_for_rank(items[0]["browse_rank"]) if items else None)
    )
    next_learn_entry = (
        next((item for item in items if item["status"] == "to_learn"), None)
        or next((item for item in items if item["status"] == "learning"), None)
        or discovery_entry
    )

    return {
        "total_entries": len(items),
        "counts": counts,
        "discovery_range_start": discovery_range_start,
        "discovery_range_end": (
            discovery_range_start + BUCKET_SIZE - 1
            if discovery_range_start is not None
            else None
        ),
        "discovery_entry": discovery_entry,
        "next_learn_entry": next_learn_entry,
    }


def build_range(items: Sequence[dict], range_start: int) -> dict:
    filtered = [
        item for item in items
        if bucket_start_for_rank(item["browse_rank"]) == range_start
    ]
    ordered_range_starts = sorted({bucket_start_for_rank(item["browse_rank"]) for item in items})
    current_index = ordered_range_starts.index(range_start) if range_start in ordered_range_starts else -1
    previous_start = ordered_range_starts[current_index - 1] if current_index > 0 else None
    next_start = ordered_range_starts[current_index + 1] if current_index >= 0 and current_index + 1 < len(ordered_range_starts) else None
    return {
        "range_start": range_start,
        "range_end": range_start + BUCKET_SIZE - 1,
        "previous_range_start": previous_start,
        "next_range_start": next_start,
        "items": filtered,
    }


async def load_word_primary_definitions(db: AsyncSession, word_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Meaning]:
    if not word_ids:
        return {}
    result = await db.execute(
        select(Meaning)
        .where(Meaning.word_id.in_(word_ids))
        .order_by(Meaning.word_id.asc(), Meaning.order_index.asc())
    )
    meaning_map: dict[uuid.UUID, Meaning] = {}
    for meaning in result.scalars().all():
        meaning_map.setdefault(meaning.word_id, meaning)
    return meaning_map


async def get_status_row(
    db: AsyncSession,
    user_id: uuid.UUID,
    entry_type: str,
    entry_id: uuid.UUID,
) -> LearnerEntryStatus | None:
    result = await db.execute(
        select(LearnerEntryStatus).where(
            LearnerEntryStatus.user_id == user_id,
            LearnerEntryStatus.entry_type == entry_type,
            LearnerEntryStatus.entry_id == entry_id,
        )
    )
    return result.scalar_one_or_none()


async def load_word_detail_relations(
    db: AsyncSession,
    meaning_ids: Sequence[uuid.UUID],
) -> tuple[dict[uuid.UUID, list[MeaningExample]], dict[uuid.UUID, list[Translation]], dict[uuid.UUID, list[WordRelation]]]:
    examples_by_meaning: dict[uuid.UUID, list[MeaningExample]] = defaultdict(list)
    translations_by_meaning: dict[uuid.UUID, list[Translation]] = defaultdict(list)
    relations_by_meaning: dict[uuid.UUID, list[WordRelation]] = defaultdict(list)
    if not meaning_ids:
        return examples_by_meaning, translations_by_meaning, relations_by_meaning

    examples_result = await db.execute(
        select(MeaningExample)
        .where(MeaningExample.meaning_id.in_(meaning_ids))
        .order_by(MeaningExample.meaning_id.asc(), MeaningExample.order_index.asc())
    )
    for example in examples_result.scalars().all():
        examples_by_meaning[example.meaning_id].append(example)

    translations_result = await db.execute(
        select(Translation)
        .where(Translation.meaning_id.in_(meaning_ids))
        .options(selectinload(Translation.example_entries))
        .order_by(Translation.meaning_id.asc(), Translation.language.asc())
    )
    for translation in translations_result.scalars().all():
        translations_by_meaning[translation.meaning_id].append(translation)

    relations_result = await db.execute(
        select(WordRelation)
        .where(WordRelation.meaning_id.in_(meaning_ids))
        .order_by(WordRelation.meaning_id.asc(), WordRelation.related_word.asc())
    )
    for relation in relations_result.scalars().all():
        relations_by_meaning[relation.meaning_id].append(relation)

    return examples_by_meaning, translations_by_meaning, relations_by_meaning


async def list_search_history(db: AsyncSession, user_id: uuid.UUID) -> list[SearchHistory]:
    result = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == user_id)
        .order_by(SearchHistory.last_searched_at.desc())
    )
    return result.scalars().all()
