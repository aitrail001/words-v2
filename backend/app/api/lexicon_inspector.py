import uuid
from collections import defaultdict
from collections.abc import Sequence
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_admin_user
from app.api.request_db_metrics import finalize_request_db_metrics
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.learner_catalog_entry import LearnerCatalogEntry
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.phrase_entry import PhraseEntry
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.translation import Translation
from app.models.user import User
from app.models.word import Word
from app.models.word_relation import WordRelation
from app.services.knowledge_map import (
    normalize_confusable_words,
    normalize_meaning_metadata,
    normalize_word_forms,
    normalize_word_part_of_speech,
)
from app.services.voice_assets import build_voice_asset_playback_url, load_word_voice_assets

router = APIRouter()
logger = get_logger(__name__)

InspectorFamily = Literal["word", "phrase", "reference"]
InspectorFamilyFilter = Literal["all", "word", "phrase", "reference"]
InspectorSort = Literal["updated_desc", "rank_asc", "alpha_asc"]


class LexiconInspectorListEntry(BaseModel):
    id: str
    family: InspectorFamily
    display_text: str
    normalized_form: str | None
    language: str
    source_reference: str | None
    cefr_level: str | None
    frequency_rank: int | None
    secondary_label: str | None
    created_at: str | None


class LexiconInspectorListResponse(BaseModel):
    items: list[LexiconInspectorListEntry]
    total: int
    family: InspectorFamilyFilter
    q: str | None
    limit: int
    offset: int
    has_more: bool


class MeaningExampleResponse(BaseModel):
    id: str
    sentence: str
    difficulty: str | None
    order_index: int


class WordRelationResponse(BaseModel):
    id: str
    relation_type: str
    related_word: str


class MeaningTranslationResponse(BaseModel):
    id: str
    language: str
    translation: str


class InspectorPhraseTranslationResponse(BaseModel):
    locale: str
    definition: str | None
    usage_note: str | None
    examples: list[str]


class InspectorPhraseSenseResponse(BaseModel):
    sense_id: str | None
    definition: str
    part_of_speech: str | None
    grammar_patterns: list[str] | None
    usage_note: str | None
    examples: list[MeaningExampleResponse]
    translations: list[InspectorPhraseTranslationResponse]


class LexiconEnrichmentRunResponse(BaseModel):
    id: str
    generator_model: str | None
    validator_model: str | None
    prompt_version: str | None
    verdict: str | None
    created_at: str


class InspectorVoiceAssetResponse(BaseModel):
    id: str
    content_scope: str
    meaning_id: str | None
    meaning_example_id: str | None
    locale: str
    voice_role: str
    provider: str
    family: str
    voice_id: str
    profile_key: str
    audio_format: str
    mime_type: str | None
    playback_url: str
    playback_route_kind: str
    status: str
    generated_at: str | None
    primary_target_kind: str
    primary_target_base: str


class InspectorMeaningResponse(BaseModel):
    id: str
    definition: str
    part_of_speech: str | None
    primary_domain: str | None
    secondary_domains: list[str] | None
    register_label: str | None
    grammar_patterns: list[str] | None
    usage_note: str | None
    example_sentence: str | None
    source: str | None
    source_reference: str | None
    learner_generated_at: str | None
    order_index: int
    examples: list[MeaningExampleResponse]
    relations: list[WordRelationResponse]
    translations: list[MeaningTranslationResponse]


class LexiconInspectorWordDetail(BaseModel):
    family: Literal["word"]
    id: str
    display_text: str
    normalized_form: str
    language: str
    cefr_level: str | None
    frequency_rank: int | None
    phonetics: dict | None
    phonetic: str | None
    phonetic_source: str | None
    phonetic_confidence: float | None
    learner_part_of_speech: list[str] | None
    confusable_words: list[dict] | None
    word_forms: dict | None
    source_type: str | None
    source_reference: str | None
    learner_generated_at: str | None
    created_at: str | None
    meanings: list[InspectorMeaningResponse]
    enrichment_runs: list[LexiconEnrichmentRunResponse]
    voice_assets: list[InspectorVoiceAssetResponse]


class LexiconInspectorPhraseDetail(BaseModel):
    family: Literal["phrase"]
    id: str
    display_text: str
    normalized_form: str
    language: str
    cefr_level: str | None
    source_type: str | None
    source_reference: str | None
    phrase_kind: str
    register_label: str | None
    brief_usage_note: str | None
    confidence_score: float | None
    generated_at: str | None
    seed_metadata: dict | None
    compiled_payload: dict | None
    senses: list[InspectorPhraseSenseResponse]
    created_at: str | None


class LexiconInspectorReferenceLocalization(BaseModel):
    id: str
    locale: str
    display_form: str
    brief_description: str | None
    translation_mode: str | None


class LexiconInspectorReferenceDetail(BaseModel):
    family: Literal["reference"]
    id: str
    display_text: str
    normalized_form: str
    language: str
    source_reference: str | None
    reference_type: str
    translation_mode: str
    brief_description: str
    pronunciation: str
    learner_tip: str | None
    created_at: str | None
    localizations: list[LexiconInspectorReferenceLocalization]


def _created_iso(value) -> str | None:
    return value.isoformat() if value else None


def _as_object(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    return value if isinstance(value, list) else []


def _as_string(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _entry_matches(query: str | None, *values: str | None) -> bool:
    if not query:
        return True
    lowered = query.lower()
    return any((value or "").lower().find(lowered) >= 0 for value in values)


def _voice_asset_response(asset: LexiconVoiceAsset) -> InspectorVoiceAssetResponse:
    return InspectorVoiceAssetResponse(
        id=str(asset.id),
        content_scope=asset.content_scope,
        meaning_id=str(asset.meaning_id) if asset.meaning_id else None,
        meaning_example_id=str(asset.meaning_example_id) if asset.meaning_example_id else None,
        locale=asset.locale,
        voice_role=asset.voice_role,
        provider=asset.provider,
        family=asset.family,
        voice_id=asset.voice_id,
        profile_key=asset.profile_key,
        audio_format=asset.audio_format,
        mime_type=asset.mime_type,
        playback_url=build_voice_asset_playback_url(asset),
        playback_route_kind="backend_content_route",
        status=asset.status,
        generated_at=_created_iso(asset.generated_at),
        primary_target_kind=asset.storage_kind,
        primary_target_base=asset.storage_base,
    )


def _sort_entries(items: list[LexiconInspectorListEntry], sort: InspectorSort) -> list[LexiconInspectorListEntry]:
    if sort == "alpha_asc":
        return sorted(items, key=lambda item: ((item.display_text or "").lower(), item.family, item.id))
    if sort == "rank_asc":
        return sorted(
            items,
            key=lambda item: (
                item.frequency_rank if item.frequency_rank is not None else 10**9,
                (item.display_text or "").lower(),
                item.family,
            ),
        )
    return sorted(
        items,
        key=lambda item: (
            item.created_at or "",
            item.family,
            item.id,
        ),
        reverse=True,
    )


def _browse_word_entries_query(q: str | None):
    query = select(
        literal("word").label("family"),
        Word.id.label("id"),
        Word.word.label("display_text"),
        Word.word.label("normalized_form"),
        Word.language.label("language"),
        Word.source_reference.label("source_reference"),
        Word.cefr_level.label("cefr_level"),
        Word.frequency_rank.label("frequency_rank"),
        Word.phonetic.label("secondary_label"),
        Word.created_at.label("created_at"),
    )
    if q:
        lowered = q.strip().lower()
        if lowered:
            query = query.where(
                or_(
                    func.lower(Word.word).contains(lowered),
                    func.lower(Word.source_reference).contains(lowered),
                )
            )
    return query


def _browse_phrase_entries_query(q: str | None):
    query = select(
        literal("phrase").label("family"),
        PhraseEntry.id.label("id"),
        PhraseEntry.phrase_text.label("display_text"),
        PhraseEntry.normalized_form.label("normalized_form"),
        PhraseEntry.language.label("language"),
        PhraseEntry.source_reference.label("source_reference"),
        PhraseEntry.cefr_level.label("cefr_level"),
        literal(None).label("frequency_rank"),
        PhraseEntry.phrase_kind.label("secondary_label"),
        PhraseEntry.created_at.label("created_at"),
    )
    if q:
        lowered = q.strip().lower()
        if lowered:
            query = query.where(
                or_(
                    func.lower(PhraseEntry.phrase_text).contains(lowered),
                    func.lower(PhraseEntry.normalized_form).contains(lowered),
                    func.lower(PhraseEntry.source_reference).contains(lowered),
                )
            )
    return query


def _browse_reference_entries_query(q: str | None):
    query = select(
        literal("reference").label("family"),
        ReferenceEntry.id.label("id"),
        ReferenceEntry.display_form.label("display_text"),
        ReferenceEntry.normalized_form.label("normalized_form"),
        ReferenceEntry.language.label("language"),
        ReferenceEntry.source_reference.label("source_reference"),
        literal(None).label("cefr_level"),
        literal(None).label("frequency_rank"),
        ReferenceEntry.reference_type.label("secondary_label"),
        ReferenceEntry.created_at.label("created_at"),
    )
    if q:
        lowered = q.strip().lower()
        if lowered:
            query = query.where(
                or_(
                    func.lower(ReferenceEntry.display_form).contains(lowered),
                    func.lower(ReferenceEntry.normalized_form).contains(lowered),
                    func.lower(ReferenceEntry.source_reference).contains(lowered),
                )
            )
    return query


def _browse_entries_order_by(entries, sort: InspectorSort):
    if sort == "alpha_asc":
        return [
            func.lower(entries.c.display_text).asc(),
            entries.c.family.asc(),
            entries.c.id.asc(),
        ]
    if sort == "rank_asc":
        return [
            entries.c.frequency_rank.asc().nullslast(),
            func.lower(entries.c.display_text).asc(),
            entries.c.family.asc(),
            entries.c.id.asc(),
        ]
    return [
        entries.c.created_at.desc().nullslast(),
        entries.c.family.asc(),
        entries.c.id.asc(),
    ]


async def _browse_word_entries_alpha_page(
    db: AsyncSession,
    *,
    page_size: int,
) -> list[LexiconInspectorListEntry]:
    seed = (
        select(
            LearnerCatalogEntry.entry_id.label("entry_id"),
            LearnerCatalogEntry.display_text.label("display_text"),
        )
        .where(LearnerCatalogEntry.entry_type == "word")
        .order_by(func.lower(LearnerCatalogEntry.display_text).asc(), LearnerCatalogEntry.entry_id.asc())
        .limit(page_size)
        .subquery()
    )
    result = await db.execute(
        select(
            seed.c.entry_id.label("id"),
            seed.c.display_text.label("display_text"),
            Word.word.label("normalized_form"),
            Word.language.label("language"),
            Word.source_reference.label("source_reference"),
            Word.cefr_level.label("cefr_level"),
            Word.frequency_rank.label("frequency_rank"),
            Word.phonetic.label("secondary_label"),
            Word.created_at.label("created_at"),
        )
        .join(Word, Word.id == seed.c.entry_id)
        .order_by(func.lower(seed.c.display_text).asc(), seed.c.entry_id.asc())
    )
    return [
        LexiconInspectorListEntry(
            id=str(row["id"]),
            family="word",
            display_text=row["display_text"],
            normalized_form=row["normalized_form"],
            language=row["language"],
            source_reference=row["source_reference"],
            cefr_level=row["cefr_level"],
            frequency_rank=row["frequency_rank"],
            secondary_label=row["secondary_label"],
            created_at=_created_iso(row["created_at"]),
        )
        for row in result.mappings().all()
    ]


async def _browse_phrase_entries_alpha_page(
    db: AsyncSession,
    *,
    page_size: int,
) -> list[LexiconInspectorListEntry]:
    seed = (
        select(
            LearnerCatalogEntry.entry_id.label("entry_id"),
            LearnerCatalogEntry.display_text.label("display_text"),
        )
        .where(LearnerCatalogEntry.entry_type == "phrase")
        .order_by(func.lower(LearnerCatalogEntry.display_text).asc(), LearnerCatalogEntry.entry_id.asc())
        .limit(page_size)
        .subquery()
    )
    result = await db.execute(
        select(
            seed.c.entry_id.label("id"),
            seed.c.display_text.label("display_text"),
            PhraseEntry.normalized_form.label("normalized_form"),
            PhraseEntry.language.label("language"),
            PhraseEntry.source_reference.label("source_reference"),
            PhraseEntry.cefr_level.label("cefr_level"),
            PhraseEntry.phrase_kind.label("secondary_label"),
            PhraseEntry.created_at.label("created_at"),
        )
        .join(PhraseEntry, PhraseEntry.id == seed.c.entry_id)
        .order_by(func.lower(seed.c.display_text).asc(), seed.c.entry_id.asc())
    )
    return [
        LexiconInspectorListEntry(
            id=str(row["id"]),
            family="phrase",
            display_text=row["display_text"],
            normalized_form=row["normalized_form"],
            language=row["language"],
            source_reference=row["source_reference"],
            cefr_level=row["cefr_level"],
            frequency_rank=None,
            secondary_label=row["secondary_label"],
            created_at=_created_iso(row["created_at"]),
        )
        for row in result.mappings().all()
    ]


async def _browse_reference_entries_alpha_page(
    db: AsyncSession,
    *,
    page_size: int,
) -> list[LexiconInspectorListEntry]:
    result = await db.execute(
        select(
            ReferenceEntry.id.label("id"),
            ReferenceEntry.display_form.label("display_text"),
            ReferenceEntry.normalized_form.label("normalized_form"),
            ReferenceEntry.language.label("language"),
            ReferenceEntry.source_reference.label("source_reference"),
            ReferenceEntry.reference_type.label("secondary_label"),
            ReferenceEntry.created_at.label("created_at"),
        )
        .order_by(func.lower(ReferenceEntry.display_form).asc(), ReferenceEntry.id.asc())
        .limit(page_size)
    )
    return [
        LexiconInspectorListEntry(
            id=str(row["id"]),
            family="reference",
            display_text=row["display_text"],
            normalized_form=row["normalized_form"],
            language=row["language"],
            source_reference=row["source_reference"],
            cefr_level=None,
            frequency_rank=None,
            secondary_label=row["secondary_label"],
            created_at=_created_iso(row["created_at"]),
        )
        for row in result.mappings().all()
    ]


async def _browse_entries_alpha_fast_path(
    db: AsyncSession,
    *,
    family: InspectorFamilyFilter,
    limit: int,
    offset: int,
) -> tuple[list[LexiconInspectorListEntry], int]:
    page_size = limit + offset
    items: list[LexiconInspectorListEntry] = []
    total = 0
    if family in {"all", "word"}:
        total += (
            await db.execute(
                select(func.count())
                .select_from(LearnerCatalogEntry)
                .where(LearnerCatalogEntry.entry_type == "word")
            )
        ).scalar_one()
        items.extend(await _browse_word_entries_alpha_page(db, page_size=page_size))
    if family in {"all", "phrase"}:
        total += (
            await db.execute(
                select(func.count())
                .select_from(LearnerCatalogEntry)
                .where(LearnerCatalogEntry.entry_type == "phrase")
            )
        ).scalar_one()
        items.extend(await _browse_phrase_entries_alpha_page(db, page_size=page_size))
    if family in {"all", "reference"}:
        total += (await db.execute(select(func.count()).select_from(ReferenceEntry))).scalar_one()
        items.extend(await _browse_reference_entries_alpha_page(db, page_size=page_size))
    sorted_items = _sort_entries(items, "alpha_asc")
    return sorted_items[offset: offset + limit], total


@router.get("/entries", response_model=LexiconInspectorListResponse)
async def browse_lexicon_entries(
    request: Request,
    response: Response,
    family: InspectorFamilyFilter = Query(default="all"),
    q: str | None = Query(default=None),
    sort: InspectorSort = Query(default="updated_desc"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    if not q and sort == "alpha_asc":
        paged_items, total = await _browse_entries_alpha_fast_path(
            db,
            family=family,
            limit=limit,
            offset=offset,
        )
    else:
        union_queries = []
        if family in {"all", "word"}:
            union_queries.append(_browse_word_entries_query(q))
        if family in {"all", "phrase"}:
            union_queries.append(_browse_phrase_entries_query(q))
        if family in {"all", "reference"}:
            union_queries.append(_browse_reference_entries_query(q))

        entries = union_all(*union_queries).subquery()
        total_result = await db.execute(select(func.count()).select_from(entries))
        total = total_result.scalar_one()
        page_result = await db.execute(
            select(entries).order_by(*_browse_entries_order_by(entries, sort)).offset(offset).limit(limit)
        )
        paged_items = [
            LexiconInspectorListEntry(
                id=str(row["id"]),
                family=row["family"],
                display_text=row["display_text"],
                normalized_form=row["normalized_form"],
                language=row["language"],
                source_reference=row["source_reference"],
                cefr_level=row["cefr_level"],
                frequency_rank=row["frequency_rank"],
                secondary_label=row["secondary_label"],
                created_at=_created_iso(row["created_at"]),
            )
            for row in page_result.mappings().all()
        ]
    result = LexiconInspectorListResponse(
        items=paged_items,
        total=total,
        family=family,
        q=q,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Lexicon-Inspector",
        request_start=request_start,
    )
    logger.info("lexicon_inspector_request", route_name="browse_entries", result_count=total, **metrics)
    return result


@router.get("/entries/word/{entry_id}", response_model=LexiconInspectorWordDetail)
async def get_word_inspector_detail(
    entry_id: uuid.UUID,
    request: Request,
    response: Response,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    result = await db.execute(
        select(Word)
        .options(
            selectinload(Word.part_of_speech_entries),
            selectinload(Word.confusable_entries),
            selectinload(Word.form_entries),
        )
        .where(Word.id == entry_id)
    )
    word = result.scalar_one_or_none()
    if word is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lexicon inspector entry not found")

    meanings_result = await db.execute(
        select(Meaning)
        .options(selectinload(Meaning.metadata_entries))
        .where(Meaning.word_id == entry_id)
        .order_by(Meaning.order_index)
    )
    meanings = meanings_result.scalars().all()
    meaning_ids = [meaning.id for meaning in meanings]

    examples_by_meaning: dict[uuid.UUID, list[MeaningExample]] = defaultdict(list)
    if meaning_ids:
        examples_result = await db.execute(
            select(MeaningExample)
            .where(MeaningExample.meaning_id.in_(meaning_ids))
            .order_by(MeaningExample.meaning_id.asc(), MeaningExample.order_index.asc())
        )
        for example in examples_result.scalars().all():
            examples_by_meaning[example.meaning_id].append(example)

    translations_by_meaning: dict[uuid.UUID, list[Translation]] = defaultdict(list)
    if meaning_ids:
        translations_result = await db.execute(
            select(Translation)
            .where(Translation.meaning_id.in_(meaning_ids))
            .order_by(Translation.meaning_id.asc(), Translation.language.asc())
        )
        for translation in translations_result.scalars().all():
            translations_by_meaning[translation.meaning_id].append(translation)

    relations_result = await db.execute(
        select(WordRelation)
        .where(WordRelation.word_id == entry_id)
        .order_by(WordRelation.meaning_id.asc().nullslast(), WordRelation.relation_type.asc(), WordRelation.related_word.asc())
    )
    relations = relations_result.scalars().all()
    relations_by_meaning: dict[uuid.UUID, list[WordRelation]] = defaultdict(list)
    for relation in relations:
        if relation.meaning_id is not None:
            relations_by_meaning[relation.meaning_id].append(relation)

    referenced_run_ids = {
        run_id
        for run_id in [word.phonetic_enrichment_run_id] + [example.enrichment_run_id for examples in examples_by_meaning.values() for example in examples] + [relation.enrichment_run_id for relation in relations]
        if run_id is not None
    }
    enrichment_runs: Sequence[LexiconEnrichmentRun] = []
    if referenced_run_ids:
        runs_result = await db.execute(
            select(LexiconEnrichmentRun)
            .where(LexiconEnrichmentRun.id.in_(referenced_run_ids))
            .order_by(LexiconEnrichmentRun.created_at.desc())
        )
        enrichment_runs = runs_result.scalars().all()
    voice_assets = await load_word_voice_assets(
        db,
        word_id=word.id,
        meaning_ids=[meaning.id for meaning in meanings],
        example_ids=[example.id for examples in examples_by_meaning.values() for example in examples],
    )

    result = LexiconInspectorWordDetail(
        family="word",
        id=str(word.id),
        display_text=word.word,
        normalized_form=word.word,
        language=word.language,
        cefr_level=word.cefr_level,
        frequency_rank=word.frequency_rank,
        phonetics=word.phonetics,
        phonetic=word.phonetic,
        phonetic_source=word.phonetic_source,
        phonetic_confidence=word.phonetic_confidence,
        learner_part_of_speech=normalize_word_part_of_speech(word),
        confusable_words=normalize_confusable_words(word),
        word_forms=normalize_word_forms(word),
        source_type=word.source_type,
        source_reference=word.source_reference,
        learner_generated_at=_created_iso(word.learner_generated_at),
        created_at=_created_iso(word.created_at),
        meanings=[
            InspectorMeaningResponse(
                id=str(meaning.id),
                definition=meaning.definition,
                part_of_speech=meaning.part_of_speech,
                primary_domain=meaning.primary_domain,
                secondary_domains=normalize_meaning_metadata(meaning)["secondary_domains"],
                register_label=meaning.register_label,
                grammar_patterns=normalize_meaning_metadata(meaning)["grammar_patterns"],
                usage_note=meaning.usage_note,
                example_sentence=meaning.example_sentence,
                source=meaning.source,
                source_reference=meaning.source_reference,
                learner_generated_at=_created_iso(meaning.learner_generated_at),
                order_index=meaning.order_index,
                examples=[
                    MeaningExampleResponse(
                        id=str(example.id),
                        sentence=example.sentence,
                        difficulty=example.difficulty,
                        order_index=example.order_index,
                    )
                    for example in examples_by_meaning.get(meaning.id, [])
                ],
                relations=[
                    WordRelationResponse(
                        id=str(relation.id),
                        relation_type=relation.relation_type,
                        related_word=relation.related_word,
                    )
                    for relation in relations_by_meaning.get(meaning.id, [])
                ],
                translations=[
                    MeaningTranslationResponse(
                        id=str(translation.id),
                        language=translation.language,
                        translation=translation.translation,
                    )
                    for translation in translations_by_meaning.get(meaning.id, [])
                ],
            )
            for meaning in meanings
        ],
        enrichment_runs=[
            LexiconEnrichmentRunResponse(
                id=str(run.id),
                generator_model=run.generator_model,
                validator_model=run.validator_model,
                prompt_version=run.prompt_version,
                verdict=run.verdict,
                created_at=run.created_at.isoformat(),
            )
            for run in enrichment_runs
        ],
        voice_assets=[_voice_asset_response(asset) for asset in voice_assets],
    )
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Lexicon-Inspector",
        request_start=request_start,
    )
    logger.info("lexicon_inspector_request", route_name="word_detail", **metrics)
    return result


@router.get("/entries/phrase/{entry_id}", response_model=LexiconInspectorPhraseDetail)
async def get_phrase_inspector_detail(
    entry_id: uuid.UUID,
    request: Request,
    response: Response,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    request_start = perf_counter()
    result = await db.execute(select(PhraseEntry).where(PhraseEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lexicon inspector entry not found")

    payload = _as_object(entry.compiled_payload)
    senses: list[InspectorPhraseSenseResponse] = []
    for sense_index, raw_sense in enumerate(_as_list(payload.get("senses")), start=1):
        sense = _as_object(raw_sense)
        translations: list[InspectorPhraseTranslationResponse] = []
        for locale, raw_translation in sorted(_as_object(sense.get("translations")).items()):
            translation = _as_object(raw_translation)
            translations.append(
                InspectorPhraseTranslationResponse(
                    locale=str(locale),
                    definition=_as_string(translation.get("definition")),
                    usage_note=_as_string(translation.get("usage_note")),
                    examples=[str(example) for example in _as_list(translation.get("examples")) if str(example).strip()],
                )
            )
        senses.append(
            InspectorPhraseSenseResponse(
                sense_id=_as_string(sense.get("sense_id")),
                definition=_as_string(sense.get("definition")) or f"Sense {sense_index}",
                part_of_speech=_as_string(sense.get("part_of_speech")),
                grammar_patterns=[str(pattern) for pattern in _as_list(sense.get("grammar_patterns")) if str(pattern).strip()] or None,
                usage_note=_as_string(sense.get("usage_note")),
                examples=[
                    MeaningExampleResponse(
                        id=f"{entry.id}-sense-{sense_index}-example-{example_index}",
                        sentence=_as_string(_as_object(raw_example).get("sentence")) or str(raw_example),
                        difficulty=_as_string(_as_object(raw_example).get("difficulty")),
                        order_index=example_index - 1,
                    )
                    for example_index, raw_example in enumerate(_as_list(sense.get("examples")), start=1)
                    if (_as_string(_as_object(raw_example).get("sentence")) or str(raw_example).strip())
                ],
                translations=translations,
            )
        )

    result = LexiconInspectorPhraseDetail(
        family="phrase",
        id=str(entry.id),
        display_text=entry.phrase_text,
        normalized_form=entry.normalized_form,
        language=entry.language,
        cefr_level=entry.cefr_level,
        source_type=entry.source_type,
        source_reference=entry.source_reference,
        phrase_kind=entry.phrase_kind,
        register_label=entry.register_label,
        brief_usage_note=entry.brief_usage_note,
        confidence_score=entry.confidence_score,
        generated_at=_created_iso(entry.generated_at),
        seed_metadata=entry.seed_metadata,
        compiled_payload=entry.compiled_payload,
        senses=senses,
        created_at=_created_iso(entry.created_at),
    )
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Lexicon-Inspector",
        request_start=request_start,
    )
    logger.info("lexicon_inspector_request", route_name="phrase_detail", **metrics)
    return result


@router.get("/entries/reference/{entry_id}", response_model=LexiconInspectorReferenceDetail)
async def get_reference_inspector_detail(
    entry_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ReferenceEntry).where(ReferenceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lexicon inspector entry not found")

    localizations_result = await db.execute(
        select(ReferenceLocalization)
        .where(ReferenceLocalization.reference_entry_id == entry_id)
        .order_by(ReferenceLocalization.locale.asc())
    )
    localizations = localizations_result.scalars().all()

    return LexiconInspectorReferenceDetail(
        family="reference",
        id=str(entry.id),
        display_text=entry.display_form,
        normalized_form=entry.normalized_form,
        language=entry.language,
        source_reference=entry.source_reference,
        reference_type=entry.reference_type,
        translation_mode=entry.translation_mode,
        brief_description=entry.brief_description,
        pronunciation=entry.pronunciation,
        learner_tip=entry.learner_tip,
        created_at=_created_iso(entry.created_at),
        localizations=[
            LexiconInspectorReferenceLocalization(
                id=str(localization.id),
                locale=localization.locale,
                display_form=localization.display_form,
                brief_description=localization.brief_description,
                translation_mode=localization.translation_mode,
            )
            for localization in localizations
        ],
    )
