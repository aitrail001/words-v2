import uuid
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.api.auth import get_current_user
from app.api.request_db_metrics import finalize_request_db_metrics
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.lexicon_voice_asset import LexiconVoiceAsset
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
    build_relation_groups,
    build_word_translation_map,
    collect_exact_lookup_terms,
    find_example_links,
    get_preferences,
    get_status_row,
    load_catalog_neighbors,
    list_search_history,
    load_entry_lookup_for_terms,
    load_dashboard_summary,
    load_overview_summary,
    load_phrase_detail_rows,
    load_phrase_summary_map,
    load_range_catalog_items,
    load_word_detail_relations,
    load_word_primary_definitions,
    normalize_confusable_words,
    normalize_meaning_metadata,
    normalize_translation_examples,
    normalize_word_forms,
    relation_terms,
    resolve_exact_match_target,
    select_pronunciation,
)
from app.services.voice_assets import (
    build_voice_asset_playback_url,
    load_phrase_voice_assets,
    load_word_voice_assets,
)

router = APIRouter()
logger = get_logger(__name__)


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
    voice_assets: list["LearnerVoiceAssetResponse"] = []


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


class LearnerVoiceAssetResponse(BaseModel):
    id: str
    content_scope: str
    meaning_id: str | None = None
    meaning_example_id: str | None = None
    phrase_sense_id: str | None = None
    phrase_sense_example_id: str | None = None
    locale: str
    voice_role: str
    provider: str
    family: str
    voice_id: str
    profile_key: str
    audio_format: str
    mime_type: str | None = None
    speaking_rate: float | None = None
    pitch_semitones: float | None = None
    lead_ms: int = 0
    tail_ms: int = 0
    effects_profile_id: str | None = None
    playback_url: str
    storage_kind: str
    storage_base: str
    relative_path: str
    status: str
    generation_error: str | None = None
    generated_at: str | None = None


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
    voice_assets: list[LearnerVoiceAssetResponse] = []
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
        voice_assets=item.get("voice_assets", []),
    )


def _voice_asset_response(asset: LexiconVoiceAsset) -> LearnerVoiceAssetResponse:
    return LearnerVoiceAssetResponse(
        id=str(asset.id),
        content_scope=asset.content_scope,
        meaning_id=str(asset.meaning_id) if asset.meaning_id else None,
        meaning_example_id=str(asset.meaning_example_id) if asset.meaning_example_id else None,
        phrase_sense_id=str(asset.phrase_sense_id) if asset.phrase_sense_id else None,
        phrase_sense_example_id=str(asset.phrase_sense_example_id) if asset.phrase_sense_example_id else None,
        locale=asset.locale,
        voice_role=asset.voice_role,
        provider=asset.provider,
        family=asset.family,
        voice_id=asset.voice_id,
        profile_key=asset.profile_key,
        audio_format=asset.audio_format,
        mime_type=asset.mime_type,
        speaking_rate=asset.speaking_rate,
        pitch_semitones=asset.pitch_semitones,
        lead_ms=int(asset.lead_ms or 0),
        tail_ms=int(asset.tail_ms or 0),
        effects_profile_id=asset.effects_profile_id,
        playback_url=build_voice_asset_playback_url(asset),
        storage_kind=asset.storage_kind,
        storage_base=asset.storage_base,
        relative_path=asset.relative_path,
        status=asset.status,
        generation_error=asset.generation_error,
        generated_at=asset.generated_at.isoformat() if asset.generated_at else None,
    )


async def _load_summary_voice_assets(
    db: AsyncSession,
    items: list[dict],
) -> dict[tuple[str, uuid.UUID], list[LearnerVoiceAssetResponse]]:
    word_ids = [item["entry_id"] for item in items if item["entry_type"] == "word"]
    phrase_ids = [item["entry_id"] for item in items if item["entry_type"] == "phrase"]
    clauses = []
    if word_ids:
        clauses.append(
            (LexiconVoiceAsset.word_id.in_(word_ids)) & (LexiconVoiceAsset.content_scope == "word")
        )
    if phrase_ids:
        clauses.append(
            (LexiconVoiceAsset.phrase_entry_id.in_(phrase_ids))
            & (LexiconVoiceAsset.content_scope == "word")
        )
    if not clauses:
        return {}

    result = await db.execute(
        select(LexiconVoiceAsset)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(or_(*clauses))
    )
    grouped: dict[tuple[str, uuid.UUID], list[LearnerVoiceAssetResponse]] = {}
    for asset in result.scalars().all():
        if asset.word_id is not None:
            key = ("word", asset.word_id)
        elif asset.phrase_entry_id is not None:
            key = ("phrase", asset.phrase_entry_id)
        else:
            continue
        grouped.setdefault(key, []).append(_voice_asset_response(asset))
    return grouped


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


def _finalize_knowledge_map_metrics(
    response: Response,
    request: Request,
    *,
    route_name: str,
    request_start: float,
    result_count: int | None = None,
) -> None:
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Knowledge-Map",
        request_start=request_start,
    )
    logger.info(
        "knowledge_map_request",
        route_name=route_name,
        query_count=metrics["query_count"],
        query_duration_ms=metrics["query_duration_ms"],
        request_duration_ms=metrics["request_duration_ms"],
        result_count=result_count,
        path=request.url.path,
    )


async def _hydrate_summary_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    items: list[dict],
) -> list[dict]:
    word_ids = [item["entry_id"] for item in items if item["entry_type"] == "word"]
    phrase_ids = [item["entry_id"] for item in items if item["entry_type"] == "phrase"]
    if not word_ids and not phrase_ids:
        return items

    voice_assets_by_entry = await _load_summary_voice_assets(db, items)

    preferences = await get_preferences(db, user_id)
    if word_ids:
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
            item["voice_assets"] = [
                asset.model_dump()
                for asset in voice_assets_by_entry.get(("word", item["entry_id"]), [])
            ]

    if phrase_ids:
        phrase_summary_map = await load_phrase_summary_map(db, phrase_ids, preferences.translation_locale)
        for item in items:
            if item["entry_type"] != "phrase":
                continue
            summary_row = phrase_summary_map.get(item["entry_id"])
            if summary_row is None:
                continue
            item["translation"] = summary_row["translation"]
            item["primary_definition"] = summary_row["primary_definition"]
            item["voice_assets"] = [
                asset.model_dump()
                for asset in voice_assets_by_entry.get(("phrase", item["entry_id"]), [])
            ]

    return items


@router.get("/overview", response_model=KnowledgeMapOverviewResponse)
async def get_knowledge_map_overview(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    overview = await load_overview_summary(db, current_user.id)
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="overview",
        request_start=request_start,
        result_count=len(overview["ranges"]),
    )
    return KnowledgeMapOverviewResponse(**overview)


@router.get("/dashboard", response_model=KnowledgeMapDashboardResponse)
async def get_knowledge_map_dashboard(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    summary = await load_dashboard_summary(db, current_user.id)
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="dashboard",
        request_start=request_start,
        result_count=summary["total_entries"],
    )
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
    request: Request,
    response: Response,
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

    request_start = perf_counter()
    items = await build_catalog(
        db,
        current_user.id,
        q=q,
        status=status_filter,
        sort=sort,
        limit=limit,
    )
    items = await _hydrate_summary_items(db, current_user.id, items)
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="list",
        request_start=request_start,
        result_count=len(items),
    )
    return KnowledgeMapListResponse(items=[_summary_from_item(item) for item in items])


@router.get("/ranges/{range_start}", response_model=KnowledgeMapRangeResponse)
async def get_knowledge_map_range(
    request: Request,
    response: Response,
    range_start: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    range_payload = await load_range_catalog_items(db, current_user.id, range_start)
    range_payload["items"] = await _hydrate_summary_items(
        db,
        current_user.id,
        range_payload["items"],
    )
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="range",
        request_start=request_start,
        result_count=len(range_payload["items"]),
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
    request: Request,
    response: Response,
    entry_type: str,
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    request_start = perf_counter()
    preferences = await get_preferences(db, current_user.id)

    if entry_type == "word":
        word_result = await db.execute(
            select(Word)
            .options(
                load_only(
                    Word.id,
                    Word.word,
                    Word.language,
                    Word.phonetics,
                    Word.phonetic,
                    Word.cefr_level,
                    Word.frequency_rank,
                ),
                selectinload(Word.part_of_speech_entries),
                selectinload(Word.form_entries),
                selectinload(Word.confusable_entries),
            )
            .where(Word.id == entry_id)
        )
        word = word_result.scalar_one_or_none()
        if word is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

        meanings_result = await db.execute(
            select(Meaning)
            .options(selectinload(Meaning.metadata_entries))
            .where(Meaning.word_id == entry_id)
            .order_by(Meaning.order_index.asc())
        )
        meanings = meanings_result.scalars().all()
        meaning_ids = [meaning.id for meaning in meanings]
        examples_by_meaning, translations_by_meaning, relations_by_meaning = await load_word_detail_relations(db, meaning_ids)
        example_ids = [example.id for examples in examples_by_meaning.values() for example in examples]
        voice_assets = await load_word_voice_assets(
            db,
            word_id=word.id,
            meaning_ids=meaning_ids,
            example_ids=example_ids,
        )
        status_row = await get_status_row(db, current_user.id, "word", entry_id)
        current_entry, previous_entry, next_entry = await load_catalog_neighbors(db, "word", entry_id)
        forms = normalize_word_forms(word)

        lookup_terms = collect_exact_lookup_terms(
            values=[
                *forms["derivations"],
                *(item.related_word for rows in relations_by_meaning.values() for item in rows),
                *(item["word"] for item in normalize_confusable_words(word)),
            ],
            sentences=[example.sentence for rows in examples_by_meaning.values() for example in rows],
        )
        entry_lookup = await load_entry_lookup_for_terms(db, lookup_terms)

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
        detail_response = KnowledgeMapDetailResponse(
            entry_type="word",
            entry_id=str(word.id),
            display_text=word.word,
            normalized_form=word.word,
            browse_rank=int(current_entry["browse_rank"]) if current_entry is not None else (word.frequency_rank or 0),
            status=status_row.status if status_row else "undecided",
            cefr_level=word.cefr_level,
            pronunciation=select_pronunciation(word, preferences.accent_preference),
            translation=translation,
            primary_definition=primary_definition,
            supported_translation_locales=list(SUPPORTED_TRANSLATION_LOCALES),
            voice_assets=[_voice_asset_response(asset) for asset in voice_assets],
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
                        secondary_domains=normalize_meaning_metadata(meaning)["secondary_domains"],
                        grammar_patterns=normalize_meaning_metadata(meaning)["grammar_patterns"],
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
                                        translation_examples[example_index]
                                        for item in translations_by_meaning.get(meaning.id, [])
                                        for translation_examples in [normalize_translation_examples(item)]
                                        if item.language == preferences.translation_locale
                                        and len(translation_examples) > example_index
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
                                examples=normalize_translation_examples(translation),
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
            previous_entry=_adjacent_entry(previous_entry),
            next_entry=_adjacent_entry(next_entry),
        )
        _finalize_knowledge_map_metrics(
            response,
            request,
            route_name="entry_detail_word",
            request_start=request_start,
            result_count=len(detail_response.meanings),
        )
        return detail_response

    phrase_result = await db.execute(
        select(PhraseEntry)
        .options(
            load_only(
                PhraseEntry.id,
                PhraseEntry.phrase_text,
                PhraseEntry.normalized_form,
                PhraseEntry.phrase_kind,
                PhraseEntry.language,
                PhraseEntry.cefr_level,
                PhraseEntry.register_label,
                PhraseEntry.brief_usage_note,
            )
        )
        .where(PhraseEntry.id == entry_id)
    )
    phrase = phrase_result.scalar_one_or_none()
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    status_row = await get_status_row(db, current_user.id, "phrase", entry_id)
    current_entry, previous_entry, next_entry = await load_catalog_neighbors(db, "phrase", entry_id)
    senses_by_phrase, localized_by_sense, examples_by_sense, localized_examples_by_example = await load_phrase_detail_rows(
        db,
        phrase.id,
        preferences.translation_locale,
    )
    phrase_sense_ids = [sense.id for sense in senses_by_phrase]
    phrase_example_ids = [example.id for examples in examples_by_sense.values() for example in examples]
    voice_assets = await load_phrase_voice_assets(
        db,
        phrase_entry_id=phrase.id,
        phrase_sense_ids=phrase_sense_ids,
        phrase_example_ids=phrase_example_ids,
    )
    lookup_terms = collect_exact_lookup_terms(
        values=[
            *(text for sense in senses_by_phrase for text in list(sense.synonyms or [])),
            *(text for sense in senses_by_phrase for text in list(sense.antonyms or [])),
            *(text for sense in senses_by_phrase for text in list(sense.collocations or [])),
        ],
        sentences=[example.sentence for rows in examples_by_sense.values() for example in rows],
    )
    entry_lookup = await load_entry_lookup_for_terms(db, lookup_terms)
    senses = []
    for sense in senses_by_phrase:
        localized_sense = localized_by_sense.get(sense.id)
        senses.append(
            PhraseSenseResponse(
                sense_id=str(sense.id),
                definition=sense.definition,
                localized_definition=localized_sense.localized_definition if localized_sense is not None else None,
                part_of_speech=sense.part_of_speech,
                usage_note=sense.usage_note,
                localized_usage_note=localized_sense.localized_usage_note if localized_sense is not None else None,
                register=sense.register,
                primary_domain=sense.primary_domain,
                secondary_domains=list(sense.secondary_domains or []),
                grammar_patterns=list(sense.grammar_patterns or []),
                synonyms=[
                    LinkedTextResponse(
                        text=text,
                        target=(
                            LinkTargetResponse(**target)
                            if (target := resolve_exact_match_target(text, entry_lookup))
                            else None
                        ),
                    )
                    for text in list(sense.synonyms or [])
                ],
                antonyms=[
                    LinkedTextResponse(
                        text=text,
                        target=(
                            LinkTargetResponse(**target)
                            if (target := resolve_exact_match_target(text, entry_lookup))
                            else None
                        ),
                    )
                    for text in list(sense.antonyms or [])
                ],
                collocations=[
                    LinkedTextResponse(
                        text=text,
                        target=(
                            LinkTargetResponse(**target)
                            if (target := resolve_exact_match_target(text, entry_lookup))
                            else None
                        ),
                    )
                    for text in list(sense.collocations or [])
                ],
                examples=[
                    MeaningExampleResponse(
                        id=str(example.id),
                        sentence=example.sentence,
                        difficulty=example.difficulty,
                        translation=(
                            localized_examples_by_example[example.id].translation
                            if example.id in localized_examples_by_example
                            else None
                        ),
                        linked_entries=[
                            InlineLinkedEntryResponse(**link)
                            for link in find_example_links(
                                example.sentence,
                                entry_lookup,
                                excluded_terms=[phrase.normalized_form, phrase.phrase_text],
                            )
                        ],
                    )
                    for example in examples_by_sense.get(sense.id, [])
                ],
            )
        )

    primary_definition = senses_by_phrase[0].definition if senses_by_phrase else None
    translation = None
    if senses_by_phrase:
        first_localized = localized_by_sense.get(senses_by_phrase[0].id)
        if first_localized is not None:
            translation = first_localized.localized_definition

    detail_response = KnowledgeMapDetailResponse(
        entry_type="phrase",
        entry_id=str(phrase.id),
        display_text=phrase.phrase_text,
        normalized_form=phrase.normalized_form,
        browse_rank=int(current_entry["browse_rank"]) if current_entry is not None else 0,
        status=status_row.status if status_row else "undecided",
        cefr_level=phrase.cefr_level,
        pronunciation=None,
        translation=translation,
        primary_definition=primary_definition,
        supported_translation_locales=list(SUPPORTED_TRANSLATION_LOCALES),
        voice_assets=[_voice_asset_response(asset) for asset in voice_assets],
        forms=None,
        senses=senses,
        relation_groups=[],
        confusable_words=[],
        previous_entry=_adjacent_entry(previous_entry),
        next_entry=_adjacent_entry(next_entry),
    )
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="entry_detail_phrase",
        request_start=request_start,
        result_count=len(detail_response.senses),
    )
    return detail_response


@router.put("/entries/{entry_type}/{entry_id}/status", response_model=StatusResponse)
async def put_knowledge_map_status(
    request: Request,
    response: Response,
    entry_type: str,
    entry_id: uuid.UUID,
    payload: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if entry_type not in ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge map entry not found")

    request_start = perf_counter()
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
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="status_update",
        request_start=request_start,
        result_count=1,
    )
    return StatusResponse(entry_type=entry_type, entry_id=str(entry_id), status=row.status)


@router.get("/search", response_model=KnowledgeMapSearchResponse)
async def search_knowledge_map(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    items = await build_catalog(db, current_user.id, q=q)
    items = await _hydrate_summary_items(db, current_user.id, items)
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="search",
        request_start=request_start,
        result_count=len(items),
    )
    return KnowledgeMapSearchResponse(items=[_summary_from_item(item) for item in items])


@router.get("/search-history", response_model=SearchHistoryListResponse)
async def get_search_history(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    rows = await list_search_history(db, current_user.id)
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="search_history_list",
        request_start=request_start,
        result_count=len(rows),
    )
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
    request: Request,
    response: Response,
    payload: SearchHistoryWriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
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
    _finalize_knowledge_map_metrics(
        response,
        request,
        route_name="search_history_write",
        request_start=request_start,
        result_count=1,
    )
    return SearchHistoryItemResponse(
        query=row.query,
        entry_type=row.entry_type,
        entry_id=str(row.entry_id) if row.entry_id else None,
        last_searched_at=row.last_searched_at.isoformat(),
    )
