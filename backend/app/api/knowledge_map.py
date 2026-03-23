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
from app.models.user import User
from app.models.word import Word
from app.services.knowledge_map import (
    ENTRY_TYPES,
    STATUS_VALUES,
    build_catalog,
    build_catalog_items,
    build_overview,
    build_range,
    build_word_translation_map,
    extract_phrase_primary_definition,
    extract_phrase_translation,
    get_preferences,
    get_status_row,
    list_search_history,
    load_word_detail_relations,
    load_word_primary_definitions,
    select_pronunciation,
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


class MeaningExampleResponse(BaseModel):
    id: str
    sentence: str
    difficulty: str | None


class TranslationResponse(BaseModel):
    id: str
    language: str
    translation: str


class RelationResponse(BaseModel):
    id: str
    relation_type: str
    related_word: str


class KnowledgeMeaningResponse(BaseModel):
    id: str
    definition: str
    part_of_speech: str | None
    examples: list[MeaningExampleResponse]
    translations: list[TranslationResponse]
    relations: list[RelationResponse]


class PhraseSenseResponse(BaseModel):
    sense_id: str | None
    definition: str
    part_of_speech: str | None
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
    meanings: list[KnowledgeMeaningResponse] = []
    senses: list[PhraseSenseResponse] = []
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


@router.get("/overview", response_model=KnowledgeMapOverviewResponse)
async def get_knowledge_map_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    overview = build_overview(await build_catalog(db, current_user.id))
    return KnowledgeMapOverviewResponse(**overview)


@router.get("/ranges/{range_start}", response_model=KnowledgeMapRangeResponse)
async def get_knowledge_map_range(
    range_start: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await build_catalog(db, current_user.id)
    range_payload = build_range(items, range_start)
    word_ids = [item["entry_id"] for item in range_payload["items"] if item["entry_type"] == "word"]
    primary_meanings = await load_word_primary_definitions(db, word_ids)

    for item in range_payload["items"]:
        if item["entry_type"] == "word":
            meaning = primary_meanings.get(item["entry_id"])
            item["primary_definition"] = meaning.definition if meaning is not None else None

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
        status_row = await get_status_row(db, current_user.id, "word", entry_id)
        catalog = build_catalog_items(words_result.scalars().all(), phrases_result.scalars().all())
        current_index = next((index for index, item in enumerate(catalog) if item["entry_type"] == "word" and item["entry_id"] == entry_id), None)

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
            meanings=[
                KnowledgeMeaningResponse(
                    id=str(meaning.id),
                    definition=meaning.definition,
                    part_of_speech=meaning.part_of_speech,
                    examples=[
                        MeaningExampleResponse(
                            id=str(example.id),
                            sentence=example.sentence,
                            difficulty=example.difficulty,
                        )
                        for example in examples_by_meaning.get(meaning.id, [])
                    ],
                    translations=[
                        TranslationResponse(
                            id=str(translation.id),
                            language=translation.language,
                            translation=translation.translation,
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
    catalog = build_catalog_items(words_result.scalars().all(), phrases_result.scalars().all())
    current_index = next((index for index, item in enumerate(catalog) if item["entry_type"] == "phrase" and item["entry_id"] == entry_id), None)

    payload = phrase.compiled_payload if isinstance(phrase.compiled_payload, dict) else {}
    raw_senses = payload.get("senses") if isinstance(payload.get("senses"), list) else []
    senses = []
    for sense_index, raw_sense in enumerate(raw_senses, start=1):
        sense = raw_sense if isinstance(raw_sense, dict) else {}
        raw_examples = sense.get("examples") if isinstance(sense.get("examples"), list) else []
        senses.append(
            PhraseSenseResponse(
                sense_id=sense.get("sense_id") if isinstance(sense.get("sense_id"), str) else None,
                definition=sense.get("definition") if isinstance(sense.get("definition"), str) else f"Sense {sense_index}",
                part_of_speech=sense.get("part_of_speech") if isinstance(sense.get("part_of_speech"), str) else None,
                examples=[
                    MeaningExampleResponse(
                        id=f"{phrase.id}-sense-{sense_index}-example-{example_index}",
                        sentence=example.get("sentence") if isinstance(example, dict) and isinstance(example.get("sentence"), str) else str(example),
                        difficulty=example.get("difficulty") if isinstance(example, dict) and isinstance(example.get("difficulty"), str) else None,
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
        senses=senses,
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
