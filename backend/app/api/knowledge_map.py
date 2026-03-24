import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.phrase_entry import PhraseEntry
from app.models.search_history import SearchHistory
from app.models.translation import Translation
from app.models.user import User
from app.models.word import Word
from app.services.knowledge_map import (
    ENTRY_TYPES,
    LIST_SORT_VALUES,
    LIST_STATUS_VALUES,
    STATUS_VALUES,
    SUPPORTED_TRANSLATION_LOCALES,
    build_catalog,
    build_catalog_items,
    build_dashboard_summary,
    build_entry_lookup,
    build_overview,
    build_range,
    build_relation_groups,
    build_word_translation_map,
    extract_phrase_primary_definition,
    extract_phrase_translation,
    find_example_links,
    filter_catalog_items,
    get_preferences,
    get_status_row,
    list_search_history,
    load_word_detail_relations,
    load_word_primary_definitions,
    normalize_confusable_words,
    normalize_word_forms,
    phrase_locale_payload,
    relation_terms,
    resolve_exact_match_target,
    select_pronunciation,
    sort_catalog_items,
)

router = APIRouter()


class RangeCountsResponse(BaseModel):
    undecided: int
    to_learn: int
    learning: int
    known: int


class OverviewRangeResponse(BaseModel):
    range_start: int
    range_end: int
    total_entries: int
    counts: RangeCountsResponse


class KnowledgeMapOverviewResponse(BaseModel):
    bucket_size: int
    total_entries: int
    ranges: list[OverviewRangeResponse]


class KnowledgeMapAdjacentEntryResponse(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str
    browse_rank: int
    status: str


class KnowledgeMapDashboardResponse(BaseModel):
    total_entries: int
    counts: RangeCountsResponse
    discovery_range_start: int | None
    discovery_range_end: int | None
    discovery_entry: KnowledgeMapAdjacentEntryResponse | None
    next_learn_entry: KnowledgeMapAdjacentEntryResponse | None


class KnowledgeMapEntrySummary(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str
    normalized_form: str | None
    browse_rank: int
    status: str
    cefr_level: str | None
    pronunciation: str | None
    translation: str | None
    primary_definition: str | None
    part_of_speech: str | None
    phrase_kind: str | None


class KnowledgeMapRangeResponse(BaseModel):
    range_start: int
    range_end: int
    previous_range_start: int | None
    next_range_start: int | None
    items: list[KnowledgeMapEntrySummary]


class KnowledgeMapSearchResponse(BaseModel):
    items: list[KnowledgeMapEntrySummary]


class KnowledgeMapListResponse(BaseModel):
    items: list[KnowledgeMapEntrySummary]


class MeaningExampleResponse(BaseModel):
    id: str
    sentence: str
    difficulty: str | None
    translation: str | None = None
    linked_entries: list["InlineLinkedEntryResponse"] = []


class TranslationResponse(BaseModel):
    id: str
    language: str
    translation: str
    usage_note: str | None = None
    examples: list[str] = []


class RelationResponse(BaseModel):
    id: str
    relation_type: str
    related_word: str


class RelationGroupResponse(BaseModel):
    relation_type: str
    related_words: list[str]


class ConfusableWordResponse(BaseModel):
    word: str
    note: str | None = None
    target: "LinkTargetResponse | None" = None


class InlineLinkedEntryResponse(BaseModel):
    text: str
    entry_type: str
    entry_id: str


class LinkTargetResponse(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str


class LinkedTextResponse(BaseModel):
    text: str
    target: LinkTargetResponse | None = None


class WordFormsResponse(BaseModel):
    verb_forms: dict[str, str]
    plural_forms: list[str]
    derivations: list[LinkedTextResponse]
    comparative: str | None = None
    superlative: str | None = None


class KnowledgeMeaningResponse(BaseModel):
    id: str
    definition: str
    localized_definition: str | None = None
    part_of_speech: str | None
    usage_note: str | None = None
    localized_usage_note: str | None = None
    register: str | None = None
    primary_domain: str | None = None
    secondary_domains: list[str] = []
    grammar_patterns: list[str] = []
    synonyms: list[LinkedTextResponse] = []
    antonyms: list[LinkedTextResponse] = []
    collocations: list[LinkedTextResponse] = []
    examples: list[MeaningExampleResponse]
    translations: list[TranslationResponse]
    relations: list[RelationResponse]


class PhraseSenseResponse(BaseModel):
    sense_id: str | None
    definition: str
    localized_definition: str | None = None
    part_of_speech: str | None
    usage_note: str | None = None
    localized_usage_note: str | None = None
    register: str | None = None
    primary_domain: str | None = None
    secondary_domains: list[str] = []
    grammar_patterns: list[str] = []
    synonyms: list[LinkedTextResponse] = []
    antonyms: list[LinkedTextResponse] = []
    collocations: list[LinkedTextResponse] = []
    examples: list[MeaningExampleResponse]


class AdjacentEntryResponse(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str


class KnowledgeMapDetailResponse(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str
    normalized_form: str | None
    browse_rank: int
    status: str
    cefr_level: str | None
    pronunciation: str | None
    translation: str | None
    primary_definition: str | None
    supported_translation_locales: list[str] = []
    forms: WordFormsResponse | None = None
    meanings: list[KnowledgeMeaningResponse] = []
    senses: list[PhraseSenseResponse] = []
    relation_groups: list[RelationGroupResponse] = []
    confusable_words: list[ConfusableWordResponse] = []
    previous_entry: AdjacentEntryResponse | None = None
    next_entry: AdjacentEntryResponse | None = None


class StatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in STATUS_VALUES:
            raise ValueError("Unsupported status")
        return value


class StatusResponse(BaseModel):
    entry_type: str
    entry_id: str
    status: str


class SearchHistoryWriteRequest(BaseModel):
    query: str
    entry_type: str | None = None
    entry_id: str | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must not be empty")
        return value

    @field_validator("entry_type")
    @classmethod
    def validate_entry_type(cls, value: str | None) -> str | None:
        if value is not None and value not in ENTRY_TYPES:
            raise ValueError("Unsupported entry type")
        return value


class SearchHistoryItemResponse(BaseModel):
    query: str
    entry_type: str | None
    entry_id: str | None
    last_searched_at: str


class SearchHistoryListResponse(BaseModel):
    items: list[SearchHistoryItemResponse]


def _summary_from_item(item: dict) -> KnowledgeMapEntrySummary:
    return KnowledgeMapEntrySummary(
        entry_type=item["entry_type"],
        entry_id=str(item["entry_id"]),
        display_text=item["display_text"],
        normalized_form=item["normalized_form"],
        browse_rank=item["browse_rank"],
        status=item["status"],
        cefr_level=item["cefr_level"],
        pronunciation=item["pronunciation"],
        translation=item["translation"],
        primary_definition=item["primary_definition"],
        part_of_speech=item["part_of_speech"],
        phrase_kind=item["phrase_kind"],
    )


def _adjacent_entry(item: dict | None) -> AdjacentEntryResponse | None:
    if item is None:
        return None
    return AdjacentEntryResponse(
        entry_type=item["entry_type"],
        entry_id=str(item["entry_id"]),
        display_text=item["display_text"],
    )


def _dashboard_entry(item: dict | None) -> KnowledgeMapAdjacentEntryResponse | None:
    if item is None:
        return None
    return KnowledgeMapAdjacentEntryResponse(
        entry_type=item["entry_type"],
        entry_id=str(item["entry_id"]),
        display_text=item["display_text"],
        browse_rank=item["browse_rank"],
        status=item["status"],
    )


async def _hydrate_summary_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    items: list[dict],
) -> list[dict]:
    word_ids = [item["entry_id"] for item in items if item["entry_type"] == "word"]
    if not word_ids:
        return items

    preferences = await get_preferences(db, user_id)
    primary_meanings = await load_word_primary_definitions(db, word_ids)
    meaning_ids = [meaning.id for meaning in primary_meanings.values()]

    translations = []
    if meaning_ids:
        translations_result = await db.execute(
            select(Translation)
            .where(Translation.meaning_id.in_(meaning_ids))
            .order_by(Translation.meaning_id.asc(), Translation.language.asc())
        )
        translations = translations_result.scalars().all()

    translation_map = build_word_translation_map(
        translations,
        preferences.translation_locale,
    )
    words_result = await db.execute(select(Word).where(Word.id.in_(word_ids)))
    words_by_id = {word.id: word for word in words_result.scalars().all()}

    for item in items:
        if item["entry_type"] != "word":
            continue
        meaning = primary_meanings.get(item["entry_id"])
        word = words_by_id.get(item["entry_id"])
        item["primary_definition"] = meaning.definition if meaning is not None else item.get("primary_definition")
        item["translation"] = translation_map.get(meaning.id) if meaning is not None else item.get("translation")
        item["pronunciation"] = (
            select_pronunciation(word, preferences.accent_preference)
            if word is not None
            else item.get("pronunciation")
        )

    phrase_ids = [item["entry_id"] for item in items if item["entry_type"] == "phrase"]
    if phrase_ids:
        phrases_result = await db.execute(select(PhraseEntry).where(PhraseEntry.id.in_(phrase_ids)))
        phrases_by_id = {phrase.id: phrase for phrase in phrases_result.scalars().all()}
        for item in items:
            if item["entry_type"] != "phrase":
                continue
            phrase = phrases_by_id.get(item["entry_id"])
            if phrase is None:
                continue
            item["translation"] = extract_phrase_translation(phrase, preferences.translation_locale)
            item["primary_definition"] = extract_phrase_primary_definition(phrase) or item.get("primary_definition")

    return items


@router.get("/overview", response_model=KnowledgeMapOverviewResponse)
async def get_knowledge_map_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    overview = build_overview(await build_catalog(db, current_user.id))
    return KnowledgeMapOverviewResponse(**overview)


@router.get("/dashboard", response_model=KnowledgeMapDashboardResponse)
async def get_knowledge_map_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    summary = build_dashboard_summary(await build_catalog(db, current_user.id))
    return KnowledgeMapDashboardResponse(
        total_entries=summary["total_entries"],
        counts=RangeCountsResponse(**summary["counts"]),
        discovery_range_start=summary["discovery_range_start"],
        discovery_range_end=summary["discovery_range_end"],
        discovery_entry=_dashboard_entry(summary["discovery_entry"]),
        next_learn_entry=_dashboard_entry(summary["next_learn_entry"]),
    )


@router.get("/list", response_model=KnowledgeMapListResponse)
async def get_knowledge_map_list(
    status_filter: str = Query(..., alias="status"),
    q: str | None = Query(default=None),
    sort: str = Query(default="rank"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if status_filter not in LIST_STATUS_VALUES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported knowledge list status")
    if sort not in LIST_SORT_VALUES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported knowledge list sort")

    items = await build_catalog(db, current_user.id)
    filtered = filter_catalog_items(items, status=status_filter, q=q)
    ordered = sort_catalog_items(filtered, sort)[:limit]
    ordered = await _hydrate_summary_items(db, current_user.id, ordered)
    return KnowledgeMapListResponse(items=[_summary_from_item(item) for item in ordered])


@router.get("/ranges/{range_start}", response_model=KnowledgeMapRangeResponse)
async def get_knowledge_map_range(
    range_start: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await build_catalog(db, current_user.id)
    range_payload = build_range(items, range_start)
    range_payload["items"] = await _hydrate_summary_items(
        db,
        current_user.id,
        range_payload["items"],
    )

    return KnowledgeMapRangeResponse(
        range_start=range_payload["range_start"],
        range_end=range_payload["range_end"],
        previous_range_start=range_payload["previous_range_start"],
        next_range_start=range_payload["next_range_start"],
        items=[_summary_from_item(item) for item in range_payload["items"]],
    )


@router.get("/entries/{entry_type}/{entry_id}", response_model=KnowledgeMapDetailResponse)
async def get_knowledge_map_entry_detail(
    entry_type: str,
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    preferences = await get_preferences(db, current_user.id)

    if entry_type == "word":
        word_result = await db.execute(select(Word).where(Word.id == entry_id))
        word = word_result.scalar_one_or_none()
        if word is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

        meanings_result = await db.execute(
            select(Meaning)
            .where(Meaning.word_id == entry_id)
            .order_by(Meaning.order_index.asc())
        )
        meanings = meanings_result.scalars().all()
        meaning_ids = [meaning.id for meaning in meanings]
        examples_by_meaning, translations_by_meaning, relations_by_meaning = await load_word_detail_relations(db, meaning_ids)
        words_result = await db.execute(select(Word))
        phrases_result = await db.execute(select(PhraseEntry))
        all_words = words_result.scalars().all()
        all_phrases = phrases_result.scalars().all()
        entry_lookup = build_entry_lookup(all_words, all_phrases)
        status_row = await get_status_row(db, current_user.id, "word", entry_id)
        catalog = build_catalog_items(all_words, all_phrases)
        current_index = next((index for index, item in enumerate(catalog) if item["entry_type"] == "word" and item["entry_id"] == entry_id), None)
        forms = normalize_word_forms(word)

        translation = None
        translation_map = build_word_translation_map(
            [translation for rows in translations_by_meaning.values() for translation in rows],
            preferences.translation_locale,
        )
        for meaning in meanings:
            if meaning.id in translation_map:
                translation = translation_map[meaning.id]
                break

        primary_definition = meanings[0].definition if meanings else None
        return KnowledgeMapDetailResponse(
            entry_type="word",
            entry_id=str(word.id),
            display_text=word.word,
            normalized_form=word.word,
            browse_rank=catalog[current_index]["browse_rank"] if current_index is not None else (word.frequency_rank or 0),
            status=status_row.status if status_row else "undecided",
            cefr_level=word.cefr_level,
            pronunciation=select_pronunciation(word, preferences.accent_preference),
            translation=translation,
            primary_definition=primary_definition,
            supported_translation_locales=list(SUPPORTED_TRANSLATION_LOCALES),
            forms=WordFormsResponse(
                verb_forms=forms["verb_forms"],
                plural_forms=forms["plural_forms"],
                derivations=[
                    LinkedTextResponse(
                        text=item,
                        target=LinkTargetResponse(**target) if (target := resolve_exact_match_target(item, entry_lookup)) else None,
                    )
                    for item in forms["derivations"]
                ],
                comparative=forms["comparative"],
                superlative=forms["superlative"],
            ),
            meanings=[
                KnowledgeMeaningResponse(
                    id=str(meaning.id),
                    definition=meaning.definition,
                    localized_definition=next(
                        (
                            item.translation
                            for item in translations_by_meaning.get(meaning.id, [])
                            if item.language == preferences.translation_locale
                        ),
                        None,
                    ),
                    part_of_speech=meaning.part_of_speech,
                    usage_note=meaning.usage_note,
                    localized_usage_note=next(
                        (
                            getattr(item, "usage_note", None)
                            for item in translations_by_meaning.get(meaning.id, [])
                            if item.language == preferences.translation_locale
                        ),
                        None,
                    ),
                    register=meaning.register_label,
                    primary_domain=meaning.primary_domain,
                    secondary_domains=list(meaning.secondary_domains or []),
                    grammar_patterns=list(meaning.grammar_patterns or []),
                    synonyms=[
                        LinkedTextResponse(text=item["text"], target=LinkTargetResponse(**item["target"]) if item["target"] else None)
                        for item in relation_terms(relations_by_meaning.get(meaning.id, []), "synonym", entry_lookup)
                    ],
                    antonyms=[
                        LinkedTextResponse(text=item["text"], target=LinkTargetResponse(**item["target"]) if item["target"] else None)
                        for item in relation_terms(relations_by_meaning.get(meaning.id, []), "antonym", entry_lookup)
                    ],
                    collocations=[
                        LinkedTextResponse(text=item["text"], target=LinkTargetResponse(**item["target"]) if item["target"] else None)
                        for item in relation_terms(relations_by_meaning.get(meaning.id, []), "collocation", entry_lookup)
                    ],
                    examples=[
                        MeaningExampleResponse(
                            id=str(example.id),
                            sentence=example.sentence,
                            difficulty=example.difficulty,
                            translation=next(
                                (
                                    item.examples[example_index]
                                    for item in translations_by_meaning.get(meaning.id, [])
                                    if item.language == preferences.translation_locale
                                    and isinstance(getattr(item, "examples", None), list)
                                    and len(item.examples) > example_index
                                ),
                                None,
                            ),
                            linked_entries=[
                                InlineLinkedEntryResponse(**link)
                                for link in find_example_links(
                                    example.sentence,
                                    entry_lookup,
                                )
                            ],
                        )
                        for example_index, example in enumerate(examples_by_meaning.get(meaning.id, []))
                    ],
                    translations=[
                        TranslationResponse(
                            id=str(translation.id),
                            language=translation.language,
                            translation=translation.translation,
                            usage_note=getattr(translation, "usage_note", None),
                            examples=list(getattr(translation, "examples", []) or []),
                        )
                        for translation in translations_by_meaning.get(meaning.id, [])
                    ],
                    relations=[
                        RelationResponse(
                            id=str(relation.id),
                            relation_type=relation.relation_type,
                            related_word=relation.related_word,
                        )
                        for relation in relations_by_meaning.get(meaning.id, [])
                    ],
                )
                for meaning in meanings
            ],
            relation_groups=[
                RelationGroupResponse(
                    relation_type=group["relation_type"],
                    related_words=list(group["related_words"]),
                )
                for group in build_relation_groups(relations_by_meaning)
            ],
            confusable_words=[
                ConfusableWordResponse(
                    word=item["word"],
                    note=item["note"],
                    target=(
                        LinkTargetResponse(**target)
                        if (target := resolve_exact_match_target(item["word"], entry_lookup))
                        else None
                    ),
                )
                for item in normalize_confusable_words(word)
            ],
            previous_entry=_adjacent_entry(catalog[current_index - 1] if current_index not in (None, 0) else None),
            next_entry=_adjacent_entry(catalog[current_index + 1] if current_index is not None and current_index + 1 < len(catalog) else None),
        )

    phrase_result = await db.execute(select(PhraseEntry).where(PhraseEntry.id == entry_id))
    phrase = phrase_result.scalar_one_or_none()
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    status_row = await get_status_row(db, current_user.id, "phrase", entry_id)
    words_result = await db.execute(select(Word))
    phrases_result = await db.execute(select(PhraseEntry))
    all_words = words_result.scalars().all()
    all_phrases = phrases_result.scalars().all()
    catalog = build_catalog_items(all_words, all_phrases)
    current_index = next((index for index, item in enumerate(catalog) if item["entry_type"] == "phrase" and item["entry_id"] == entry_id), None)

    payload = phrase.compiled_payload if isinstance(phrase.compiled_payload, dict) else {}
    raw_senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    entry_lookup = build_entry_lookup(all_words, all_phrases)
    senses = []
    for sense_index, raw_sense in enumerate(raw_senses, start=1):
        sense = raw_sense if isinstance(raw_sense, dict) else {}
        raw_examples = sense.get("examples") if isinstance(sense.get("examples"), list) else []
        locale_payload = phrase_locale_payload(sense, preferences.translation_locale)
        senses.append(
            PhraseSenseResponse(
                sense_id=sense.get("sense_id") if isinstance(sense.get("sense_id"), str) else None,
                definition=sense.get("definition") if isinstance(sense.get("definition"), str) else f"Sense {sense_index}",
                localized_definition=locale_payload.get("definition") if isinstance(locale_payload.get("definition"), str) else None,
                part_of_speech=(
                    sense.get("part_of_speech")
                    if isinstance(sense.get("part_of_speech"), str)
                    else (sense.get("pos") if isinstance(sense.get("pos"), str) else None)
                ),
                usage_note=sense.get("usage_note") if isinstance(sense.get("usage_note"), str) else None,
                localized_usage_note=locale_payload.get("usage_note") if isinstance(locale_payload.get("usage_note"), str) else None,
                register=sense.get("register") if isinstance(sense.get("register"), str) else None,
                primary_domain=sense.get("primary_domain") if isinstance(sense.get("primary_domain"), str) else None,
                secondary_domains=[
                    str(item)
                    for item in (sense.get("secondary_domains") if isinstance(sense.get("secondary_domains"), list) else [])
                    if str(item).strip()
                ],
                grammar_patterns=[
                    str(item)
                    for item in (sense.get("grammar_patterns") if isinstance(sense.get("grammar_patterns"), list) else [])
                    if str(item).strip()
                ],
                synonyms=[
                    LinkedTextResponse(text=str(item).strip(), target=LinkTargetResponse(**target) if (target := resolve_exact_match_target(str(item).strip(), entry_lookup)) else None)
                    for item in (sense.get("synonyms") if isinstance(sense.get("synonyms"), list) else [])
                    if str(item).strip()
                ],
                antonyms=[
                    LinkedTextResponse(text=str(item).strip(), target=LinkTargetResponse(**target) if (target := resolve_exact_match_target(str(item).strip(), entry_lookup)) else None)
                    for item in (sense.get("antonyms") if isinstance(sense.get("antonyms"), list) else [])
                    if str(item).strip()
                ],
                collocations=[
                    LinkedTextResponse(text=str(item).strip(), target=LinkTargetResponse(**target) if (target := resolve_exact_match_target(str(item).strip(), entry_lookup)) else None)
                    for item in (sense.get("collocations") if isinstance(sense.get("collocations"), list) else [])
                    if str(item).strip()
                ],
                examples=[
                    MeaningExampleResponse(
                        id=f"{phrase.id}-sense-{sense_index}-example-{example_index}",
                        sentence=example.get("sentence") if isinstance(example, dict) and isinstance(example.get("sentence"), str) else str(example),
                        difficulty=example.get("difficulty") if isinstance(example, dict) and isinstance(example.get("difficulty"), str) else None,
                        translation=(
                            locale_payload.get("examples")[example_index - 1]
                            if isinstance(locale_payload.get("examples"), list)
                            and len(locale_payload.get("examples")) >= example_index
                            and isinstance(locale_payload.get("examples")[example_index - 1], str)
                            else None
                        ),
                        linked_entries=[
                            InlineLinkedEntryResponse(**link)
                            for link in find_example_links(
                                example.get("sentence") if isinstance(example, dict) else str(example),
                                entry_lookup,
                                excluded_terms=[phrase.normalized_form, phrase.phrase_text],
                            )
                        ],
                    )
                    for example_index, example in enumerate(raw_examples, start=1)
                ],
            )
        )

    return KnowledgeMapDetailResponse(
        entry_type="phrase",
        entry_id=str(phrase.id),
        display_text=phrase.phrase_text,
        normalized_form=phrase.normalized_form,
        browse_rank=catalog[current_index]["browse_rank"] if current_index is not None else 0,
        status=status_row.status if status_row else "undecided",
        cefr_level=phrase.cefr_level,
        pronunciation=None,
        translation=extract_phrase_translation(phrase, preferences.translation_locale),
        primary_definition=extract_phrase_primary_definition(phrase),
        supported_translation_locales=list(SUPPORTED_TRANSLATION_LOCALES),
        forms=None,
        senses=senses,
        relation_groups=[],
        confusable_words=[],
        previous_entry=_adjacent_entry(catalog[current_index - 1] if current_index not in (None, 0) else None),
        next_entry=_adjacent_entry(catalog[current_index + 1] if current_index is not None and current_index + 1 < len(catalog) else None),
    )


@router.put("/entries/{entry_type}/{entry_id}/status", response_model=StatusResponse)
async def put_knowledge_map_status(
    entry_type: str,
    entry_id: uuid.UUID,
    payload: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    model = Word if entry_type == "word" else PhraseEntry
    entity_result = await db.execute(select(model).where(model.id == entry_id))
    entity = entity_result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    row = await get_status_row(db, current_user.id, entry_type, entry_id)
    if row is None:
        row = LearnerEntryStatus(
            user_id=current_user.id,
            entry_type=entry_type,
            entry_id=entry_id,
            status=payload.status,
        )
        db.add(row)
    else:
        row.status = payload.status
    await db.commit()
    return StatusResponse(entry_type=entry_type, entry_id=str(entry_id), status=row.status)


@router.get("/search", response_model=KnowledgeMapSearchResponse)
async def search_knowledge_map(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await build_catalog(db, current_user.id, q=q)
    items = await _hydrate_summary_items(db, current_user.id, items)
    return KnowledgeMapSearchResponse(items=[_summary_from_item(item) for item in items])


@router.get("/search-history", response_model=SearchHistoryListResponse)
async def get_search_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_search_history(db, current_user.id)
    return SearchHistoryListResponse(
        items=[
            SearchHistoryItemResponse(
                query=row.query,
                entry_type=row.entry_type,
                entry_id=str(row.entry_id) if row.entry_id else None,
                last_searched_at=row.last_searched_at.isoformat(),
            )
            for row in rows
        ]
    )


@router.post("/search-history", response_model=SearchHistoryItemResponse, status_code=status.HTTP_201_CREATED)
async def post_search_history(
    payload: SearchHistoryWriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing_result = await db.execute(
        select(SearchHistory).where(
            SearchHistory.user_id == current_user.id,
            SearchHistory.query == payload.query,
        )
    )
    row = existing_result.scalar_one_or_none()
    if row is None:
        row = SearchHistory(
            user_id=current_user.id,
            query=payload.query,
            entry_type=payload.entry_type,
            entry_id=uuid.UUID(payload.entry_id) if payload.entry_id else None,
        )
        db.add(row)
    else:
        row.entry_type = payload.entry_type
        row.entry_id = uuid.UUID(payload.entry_id) if payload.entry_id else None
    await db.commit()
    return SearchHistoryItemResponse(
        query=row.query,
        entry_type=row.entry_type,
        entry_id=str(row.entry_id) if row.entry_id else None,
        last_searched_at=row.last_searched_at.isoformat(),
    )
