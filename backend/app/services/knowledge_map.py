import uuid
from collections import defaultdict
from collections.abc import Sequence
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.phrase_entry import PhraseEntry
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


def build_entry_lookup(
    words: Sequence[Word],
    phrases: Sequence[PhraseEntry],
) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for word in words:
        normalized = word.word.strip().lower()
        if normalized and normalized not in lookup:
            lookup[normalized] = {
                "entry_type": "word",
                "entry_id": str(word.id),
                "display_text": word.word,
            }
    for phrase in phrases:
        for raw_value in (phrase.normalized_form, phrase.phrase_text):
            normalized = raw_value.strip().lower()
            if normalized and normalized not in lookup:
                lookup[normalized] = {
                    "entry_type": "phrase",
                    "entry_id": str(phrase.id),
                    "display_text": phrase.phrase_text,
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
) -> list[dict]:
    words_result = await db.execute(select(Word))
    phrases_result = await db.execute(select(PhraseEntry))
    status_map = await load_status_map(db, user_id)
    return build_catalog_items(
        words_result.scalars().all(),
        phrases_result.scalars().all(),
        status_map=status_map,
        q=q,
    )

def build_catalog_items(
    words: Sequence[Word],
    phrases: Sequence[PhraseEntry],
    *,
    status_map: dict[tuple[str, uuid.UUID], str] | None = None,
    q: str | None = None,
) -> list[dict]:
    status_map = status_map or {}
    ranked_words = sorted(
        words,
        key=lambda word: (
            word.frequency_rank if word.frequency_rank is not None else UNRANKED_BASE,
            word.word.lower(),
            str(word.id),
        ),
    )
    next_rank = max((word.frequency_rank or 0) for word in ranked_words) + 1 if ranked_words else 1

    items: list[dict] = []
    for word in ranked_words:
        browse_rank = normalize_word_rank(word, next_rank)
        next_rank = max(next_rank, browse_rank + 1)
        item = {
            "entry_type": "word",
            "entry_id": word.id,
            "display_text": word.word,
            "normalized_form": word.word,
            "browse_rank": browse_rank,
            "status": status_map.get(("word", word.id), "undecided"),
            "cefr_level": word.cefr_level,
            "pronunciation": word.phonetic,
            "translation": None,
            "primary_definition": None,
            "part_of_speech": word.learner_part_of_speech[0] if isinstance(word.learner_part_of_speech, list) and word.learner_part_of_speech else None,
            "phrase_kind": None,
        }
        items.append(item)

    phrase_entries = sorted(
        phrases,
        key=lambda entry: (entry.normalized_form.lower(), str(entry.id)),
    )
    for entry in phrase_entries:
        item = {
            "entry_type": "phrase",
            "entry_id": entry.id,
            "display_text": entry.phrase_text,
            "normalized_form": entry.normalized_form,
            "browse_rank": next_rank,
            "status": status_map.get(("phrase", entry.id), "undecided"),
            "cefr_level": entry.cefr_level,
            "pronunciation": None,
            "translation": None,
            "primary_definition": extract_phrase_primary_definition(entry),
            "part_of_speech": None,
            "phrase_kind": entry.phrase_kind,
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
