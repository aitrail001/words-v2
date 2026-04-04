from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.user import User
from app.models.word import Word
from app.models.word_relation import WordRelation
from app.services.knowledge_map import normalize_confusable_words
from app.services.knowledge_map import normalize_meaning_metadata
from app.services.knowledge_map import normalize_word_part_of_speech
from app.services.voice_assets import (
    build_fallback_local_storage_path,
    build_fallback_storage_target_url,
    build_local_storage_path,
    build_storage_target_url,
    build_voice_asset_playback_url,
    load_word_voice_assets,
)

logger = get_logger(__name__)
router = APIRouter()


def _voice_asset_parent_filters(asset: LexiconVoiceAsset):
    if asset.word_id is not None:
        return [LexiconVoiceAsset.word_id == asset.word_id]
    if asset.meaning_id is not None:
        return [LexiconVoiceAsset.meaning_id == asset.meaning_id]
    if asset.meaning_example_id is not None:
        return [LexiconVoiceAsset.meaning_example_id == asset.meaning_example_id]
    if asset.phrase_entry_id is not None:
        return [LexiconVoiceAsset.phrase_entry_id == asset.phrase_entry_id]
    if asset.phrase_sense_id is not None:
        return [LexiconVoiceAsset.phrase_sense_id == asset.phrase_sense_id]
    if asset.phrase_sense_example_id is not None:
        return [LexiconVoiceAsset.phrase_sense_example_id == asset.phrase_sense_example_id]
    return []


async def _find_voice_asset_fallback(
    db: AsyncSession,
    asset: LexiconVoiceAsset,
) -> LexiconVoiceAsset | None:
    parent_filters = _voice_asset_parent_filters(asset)
    if not parent_filters:
        return None
    result = await db.execute(
        select(LexiconVoiceAsset)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(
            and_(
                LexiconVoiceAsset.id != asset.id,
                *parent_filters,
                LexiconVoiceAsset.content_scope == asset.content_scope,
                LexiconVoiceAsset.locale == asset.locale,
                LexiconVoiceAsset.voice_role == asset.voice_role,
                LexiconVoiceAsset.profile_key == asset.profile_key,
                LexiconVoiceAsset.source_text_hash == asset.source_text_hash,
            )
        )
        .order_by(LexiconVoiceAsset.created_at.desc(), LexiconVoiceAsset.id.desc())
    )
    for candidate in result.scalars().all():
        remote_url = build_storage_target_url(candidate)
        if remote_url:
            return candidate
        try:
            local_path = build_local_storage_path(candidate)
        except FileNotFoundError:
            fallback_remote_url = build_fallback_storage_target_url(candidate)
            if fallback_remote_url:
                return candidate
            try:
                fallback_path = build_fallback_local_storage_path(candidate)
            except FileNotFoundError:
                continue
            if fallback_path.exists() and fallback_path.is_file():
                return candidate
            continue
        if local_path.exists() and local_path.is_file():
            return candidate
    return None


class PhoneticVariantResponse(BaseModel):
    ipa: str
    confidence: float


class PhoneticsResponse(BaseModel):
    us: PhoneticVariantResponse
    uk: PhoneticVariantResponse
    au: PhoneticVariantResponse


# Schemas
class MeaningResponse(BaseModel):
    id: str
    definition: str
    part_of_speech: str | None
    example_sentence: str | None
    order_index: int


class WordResponse(BaseModel):
    id: str
    word: str
    language: str
    phonetics: PhoneticsResponse | None = None
    phonetic: str | None
    frequency_rank: int | None


class WordDetailResponse(WordResponse):
    meanings: list[MeaningResponse]
    voice_targets: "LearnerVoiceTargetsResponse"


class MeaningExampleResponse(BaseModel):
    id: str
    sentence: str
    difficulty: str | None
    order_index: int
    source: str | None
    confidence: float | None
    enrichment_run_id: str | None


class WordRelationResponse(BaseModel):
    id: str
    relation_type: str
    related_word: str
    related_word_id: str | None
    source: str | None
    confidence: float | None
    enrichment_run_id: str | None


class LexiconEnrichmentRunResponse(BaseModel):
    id: str
    enrichment_job_id: str
    generator_provider: str | None
    generator_model: str | None
    validator_provider: str | None
    validator_model: str | None
    prompt_version: str | None
    prompt_hash: str | None
    verdict: str | None
    confidence: float | None
    token_input: int | None
    token_output: int | None
    estimated_cost: float | None
    created_at: str


class VoiceAssetResponse(BaseModel):
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
    speaking_rate: float | None
    pitch_semitones: float | None
    lead_ms: int
    tail_ms: int
    effects_profile_id: str | None
    playback_url: str
    storage_kind: str
    storage_base: str
    relative_path: str
    status: str
    generation_error: str | None
    generated_at: str | None


class LearnerVoiceVariantResponse(BaseModel):
    playback_url: str
    relative_path: str
    locale: str
    voice_role: str
    audio_format: str
    status: str


class LearnerVoiceTargetResponse(BaseModel):
    preferred_locale: str | None = None
    preferred_playback_url: str | None = None
    locales: dict[str, LearnerVoiceVariantResponse] = Field(default_factory=dict)


class LearnerVoiceExampleResponse(BaseModel):
    example_id: str
    voice: LearnerVoiceTargetResponse | None = None


class LearnerMeaningVoiceResponse(BaseModel):
    meaning_id: str
    voice: LearnerVoiceTargetResponse | None = None
    examples: list[LearnerVoiceExampleResponse] = Field(default_factory=list)


class LearnerVoiceTargetsResponse(BaseModel):
    entry: LearnerVoiceTargetResponse | None = None
    meanings: list[LearnerMeaningVoiceResponse] = Field(default_factory=list)


class EnrichedMeaningResponse(MeaningResponse):
    model_config = ConfigDict(populate_by_name=True)

    wn_synset_id: str | None
    primary_domain: str | None
    secondary_domains: list[str] | None
    register_label: str | None = Field(default=None, serialization_alias="register", validation_alias="register")
    grammar_patterns: list[str] | None
    usage_note: str | None
    learner_generated_at: str | None
    examples: list[MeaningExampleResponse]
    relations: list[WordRelationResponse]


class WordEnrichmentDetailResponse(WordResponse):
    phonetic_source: str | None
    phonetic_confidence: float | None
    phonetic_enrichment_run_id: str | None
    cefr_level: str | None
    part_of_speech: list[str] | None
    confusable_words: list[dict[str, str | None]] | None
    learner_generated_at: str | None
    meanings: list[EnrichedMeaningResponse]
    enrichment_runs: list[LexiconEnrichmentRunResponse]
    voice_assets: list[VoiceAssetResponse]
    voice_targets: LearnerVoiceTargetsResponse = Field(default_factory=LearnerVoiceTargetsResponse)


class LookupRequest(BaseModel):
    word: str

    @field_validator("word")
    @classmethod
    def word_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Word must not be empty")
        return v


def _word_response(word: Word) -> WordResponse:
    return WordResponse(
        id=str(word.id),
        word=word.word,
        language=word.language,
        phonetics=word.phonetics,
        phonetic=word.phonetic,
        frequency_rank=word.frequency_rank,
    )


def _meaning_response(meaning: Meaning) -> MeaningResponse:
    return MeaningResponse(
        id=str(meaning.id),
        definition=meaning.definition,
        part_of_speech=meaning.part_of_speech,
        example_sentence=meaning.example_sentence,
        order_index=meaning.order_index,
    )


def _voice_asset_response(asset: LexiconVoiceAsset) -> VoiceAssetResponse:
    return VoiceAssetResponse(
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


def _normalize_learner_locale(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"en_us", "us"}:
        return "us"
    if lowered in {"en_gb", "uk"}:
        return "uk"
    if lowered in {"en_au", "au"}:
        return "au"
    return lowered


def _learner_voice_variant_response(asset: LexiconVoiceAsset) -> LearnerVoiceVariantResponse:
    return LearnerVoiceVariantResponse(
        playback_url=build_voice_asset_playback_url(asset),
        relative_path=asset.relative_path,
        locale=asset.locale,
        voice_role=asset.voice_role,
        audio_format=asset.audio_format,
        status=asset.status,
    )


def _finalize_learner_voice_target(
    locales: dict[str, LearnerVoiceVariantResponse],
) -> LearnerVoiceTargetResponse | None:
    if not locales:
        return None

    preferred_locale = next((locale for locale in ("us", "uk", "au") if locale in locales), next(iter(locales)))
    preferred = locales[preferred_locale]
    return LearnerVoiceTargetResponse(
        preferred_locale=preferred_locale,
        preferred_playback_url=preferred.playback_url,
        locales=dict(locales),
    )


def _group_learner_voice_targets(
    assets: list[LexiconVoiceAsset],
    *,
    meanings: list[Meaning],
    examples_by_meaning: dict[uuid.UUID, list[MeaningExample]],
) -> LearnerVoiceTargetsResponse:
    entry_locales: dict[str, LearnerVoiceVariantResponse] = {}
    meaning_locales: dict[str, dict[str, LearnerVoiceVariantResponse]] = defaultdict(dict)
    example_locales: dict[str, dict[str, LearnerVoiceVariantResponse]] = defaultdict(dict)

    for asset in assets:
        locale_key = _normalize_learner_locale(asset.locale)
        if locale_key is None:
            continue
        variant = _learner_voice_variant_response(asset)
        if asset.content_scope == "word" and asset.word_id is not None:
            entry_locales.setdefault(locale_key, variant)
        elif asset.content_scope == "definition" and asset.meaning_id is not None:
            meaning_locales[str(asset.meaning_id)].setdefault(locale_key, variant)
        elif asset.content_scope == "example" and asset.meaning_example_id is not None:
            example_locales[str(asset.meaning_example_id)].setdefault(locale_key, variant)

    return LearnerVoiceTargetsResponse(
        entry=_finalize_learner_voice_target(entry_locales),
        meanings=[
            LearnerMeaningVoiceResponse(
                meaning_id=str(meaning.id),
                voice=_finalize_learner_voice_target(meaning_locales.get(str(meaning.id), {})),
                examples=[
                        LearnerVoiceExampleResponse(
                            example_id=str(example.id),
                            voice=_finalize_learner_voice_target(
                                example_locales.get(str(example.id), {})
                            ),
                        )
                    for example in examples_by_meaning.get(meaning.id, [])
                ],
            )
            for meaning in meanings
        ],
    )


@router.get("/search", response_model=list[WordResponse])
async def search_words(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WordResponse]:
    normalized_query = q.strip()
    result = await db.execute(
        select(Word)
        .where(Word.word.ilike(f"{normalized_query}%"))
        .order_by(Word.frequency_rank.asc().nullslast())
        .limit(20)
    )
    words = result.scalars().all()

    return [_word_response(w) for w in words]


@router.get("/voice-assets/{asset_id}/content")
async def get_voice_asset_content(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(LexiconVoiceAsset)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(LexiconVoiceAsset.id == asset_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset not found")

    selected_asset = asset
    remote_url = build_storage_target_url(selected_asset)
    if remote_url:
        return RedirectResponse(remote_url)

    try:
        local_path = build_local_storage_path(selected_asset)
    except FileNotFoundError as exc:
        fallback_remote_url = build_fallback_storage_target_url(selected_asset)
        if fallback_remote_url:
            return RedirectResponse(fallback_remote_url)
        try:
            local_path = build_fallback_local_storage_path(selected_asset)
        except FileNotFoundError:
            fallback_asset = await _find_voice_asset_fallback(db, selected_asset)
            if fallback_asset is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
            selected_asset = fallback_asset
            remote_url = build_storage_target_url(selected_asset)
            if remote_url:
                return RedirectResponse(remote_url)
            try:
                local_path = build_local_storage_path(selected_asset)
            except FileNotFoundError as fallback_exc:
                fallback_remote_url = build_fallback_storage_target_url(selected_asset)
                if fallback_remote_url:
                    return RedirectResponse(fallback_remote_url)
                try:
                    local_path = build_fallback_local_storage_path(selected_asset)
                except FileNotFoundError:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fallback_exc)) from fallback_exc
    if not local_path.exists() or not local_path.is_file():
        fallback_remote_url = build_fallback_storage_target_url(selected_asset)
        if fallback_remote_url:
            return RedirectResponse(fallback_remote_url)
        try:
            fallback_path = build_fallback_local_storage_path(selected_asset)
        except FileNotFoundError:
            fallback_asset = await _find_voice_asset_fallback(db, selected_asset)
            if fallback_asset is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset file not found")
            selected_asset = fallback_asset
            remote_url = build_storage_target_url(selected_asset)
            if remote_url:
                return RedirectResponse(remote_url)
            try:
                local_path = build_local_storage_path(selected_asset)
            except FileNotFoundError:
                fallback_remote_url = build_fallback_storage_target_url(selected_asset)
                if fallback_remote_url:
                    return RedirectResponse(fallback_remote_url)
                try:
                    local_path = build_fallback_local_storage_path(selected_asset)
                except FileNotFoundError:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset file not found")
        else:
            if not fallback_path.exists() or not fallback_path.is_file():
                fallback_asset = await _find_voice_asset_fallback(db, selected_asset)
                if fallback_asset is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset file not found")
                selected_asset = fallback_asset
                remote_url = build_storage_target_url(selected_asset)
                if remote_url:
                    return RedirectResponse(remote_url)
                try:
                    local_path = build_local_storage_path(selected_asset)
                except FileNotFoundError:
                    fallback_remote_url = build_fallback_storage_target_url(selected_asset)
                    if fallback_remote_url:
                        return RedirectResponse(fallback_remote_url)
                    try:
                        local_path = build_fallback_local_storage_path(selected_asset)
                    except FileNotFoundError:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset file not found")
                else:
                    if not local_path.exists() or not local_path.is_file():
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice asset file not found")
            else:
                local_path = fallback_path
    return FileResponse(local_path, media_type=selected_asset.mime_type or "audio/mpeg", filename=Path(selected_asset.relative_path).name)


@router.get("/{word_id}/enrichment", response_model=WordEnrichmentDetailResponse)
async def get_word_enrichment(
    word_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordEnrichmentDetailResponse:
    result = await db.execute(
        select(Word)
        .options(selectinload(Word.confusable_entries), selectinload(Word.part_of_speech_entries))
        .where(Word.id == word_id)
    )
    word = result.scalar_one_or_none()

    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )

    meanings_result = await db.execute(
        select(Meaning)
        .options(selectinload(Meaning.metadata_entries))
        .where(Meaning.word_id == word_id)
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
        examples = examples_result.scalars().all()
        for example in examples:
            examples_by_meaning[example.meaning_id].append(example)
    else:
        examples = []

    relations_result = await db.execute(
        select(WordRelation)
        .where(WordRelation.word_id == word_id)
        .order_by(WordRelation.meaning_id.asc().nullslast(), WordRelation.relation_type.asc(), WordRelation.related_word.asc())
    )
    relations = relations_result.scalars().all()
    relations_by_meaning: dict[uuid.UUID, list[WordRelation]] = defaultdict(list)
    for relation in relations:
        if relation.meaning_id is not None:
            relations_by_meaning[relation.meaning_id].append(relation)

    referenced_run_ids = {
        run_id
        for run_id in [word.phonetic_enrichment_run_id] + [example.enrichment_run_id for example in examples] + [relation.enrichment_run_id for relation in relations]
        if run_id is not None
    }
    enrichment_runs: list[LexiconEnrichmentRun] = []
    if referenced_run_ids:
        runs_result = await db.execute(
            select(LexiconEnrichmentRun)
            .where(LexiconEnrichmentRun.id.in_(referenced_run_ids))
            .order_by(LexiconEnrichmentRun.created_at.desc())
        )
        enrichment_runs = runs_result.scalars().all()

    meaning_metadata = {meaning.id: normalize_meaning_metadata(meaning) for meaning in meanings}
    voice_assets = await load_word_voice_assets(
        db,
        word_id=word.id,
        meaning_ids=meaning_ids,
        example_ids=[example.id for example in examples],
    )

    voice_targets = _group_learner_voice_targets(
        assets=voice_assets,
        meanings=meanings,
        examples_by_meaning=examples_by_meaning,
    )

    return WordEnrichmentDetailResponse(
        id=str(word.id),
        word=word.word,
        language=word.language,
        phonetics=word.phonetics,
        phonetic=word.phonetic,
        frequency_rank=word.frequency_rank,
        phonetic_source=word.phonetic_source,
        phonetic_confidence=word.phonetic_confidence,
        phonetic_enrichment_run_id=str(word.phonetic_enrichment_run_id) if word.phonetic_enrichment_run_id else None,
        cefr_level=word.cefr_level,
        part_of_speech=normalize_word_part_of_speech(word),
        confusable_words=normalize_confusable_words(word),
        learner_generated_at=word.learner_generated_at.isoformat() if word.learner_generated_at else None,
        meanings=[
            EnrichedMeaningResponse(
                **_meaning_response(meaning).model_dump(),
                wn_synset_id=meaning.wn_synset_id,
                primary_domain=meaning.primary_domain,
                secondary_domains=meaning_metadata[meaning.id]["secondary_domains"],
                register_label=meaning.register_label,
                grammar_patterns=meaning_metadata[meaning.id]["grammar_patterns"],
                usage_note=meaning.usage_note,
                learner_generated_at=meaning.learner_generated_at.isoformat() if meaning.learner_generated_at else None,
                examples=[
                    MeaningExampleResponse(
                        id=str(example.id),
                        sentence=example.sentence,
                        difficulty=example.difficulty,
                        order_index=example.order_index,
                        source=example.source,
                        confidence=example.confidence,
                        enrichment_run_id=str(example.enrichment_run_id) if example.enrichment_run_id else None,
                    )
                    for example in examples_by_meaning.get(meaning.id, [])
                ],
                relations=[
                    WordRelationResponse(
                        id=str(relation.id),
                        relation_type=relation.relation_type,
                        related_word=relation.related_word,
                        related_word_id=str(relation.related_word_id) if relation.related_word_id else None,
                        source=relation.source,
                        confidence=relation.confidence,
                        enrichment_run_id=str(relation.enrichment_run_id) if relation.enrichment_run_id else None,
                    )
                    for relation in relations_by_meaning.get(meaning.id, [])
                ],
            )
            for meaning in meanings
        ],
        enrichment_runs=[
            LexiconEnrichmentRunResponse(
                id=str(run.id),
                enrichment_job_id=str(run.enrichment_job_id),
                generator_provider=run.generator_provider,
                generator_model=run.generator_model,
                validator_provider=run.validator_provider,
                validator_model=run.validator_model,
                prompt_version=run.prompt_version,
                prompt_hash=run.prompt_hash,
                verdict=run.verdict,
                confidence=run.confidence,
                token_input=run.token_input,
                token_output=run.token_output,
                estimated_cost=run.estimated_cost,
                created_at=run.created_at.isoformat(),
            )
            for run in enrichment_runs
        ],
        voice_assets=[_voice_asset_response(asset) for asset in voice_assets],
        voice_targets=voice_targets,
    )


@router.get("/{word_id}", response_model=WordDetailResponse)
async def get_word(
    word_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordDetailResponse:
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()

    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )

    meanings_result = await db.execute(
        select(Meaning)
        .options(selectinload(Meaning.metadata_entries))
        .where(Meaning.word_id == word_id)
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
    voice_assets = await load_word_voice_assets(
        db,
        word_id=word.id,
        meaning_ids=meaning_ids,
        example_ids=[example.id for examples in examples_by_meaning.values() for example in examples],
    )

    return WordDetailResponse(
        **_word_response(word).model_dump(),
        meanings=[_meaning_response(m) for m in meanings],
        voice_targets=_group_learner_voice_targets(
            assets=voice_assets,
            meanings=meanings,
            examples_by_meaning=examples_by_meaning,
        ),
    )


@router.post("/lookup", response_model=WordDetailResponse)
async def lookup_word(
    request: LookupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordDetailResponse:
    # Check local DB first
    result = await db.execute(
        select(Word).where(Word.word == request.word, Word.language == "en")
    )
    word = result.scalar_one_or_none()

    if word is not None:
        meanings_result = await db.execute(
            select(Meaning)
            .options(selectinload(Meaning.metadata_entries))
            .where(Meaning.word_id == word.id)
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
        voice_assets = await load_word_voice_assets(
            db,
            word_id=word.id,
            meaning_ids=meaning_ids,
            example_ids=[example.id for examples in examples_by_meaning.values() for example in examples],
        )

        return WordDetailResponse(
            **_word_response(word).model_dump(),
            meanings=[_meaning_response(m) for m in meanings],
            voice_targets=_group_learner_voice_targets(
                assets=voice_assets,
                meanings=meanings,
                examples_by_meaning=examples_by_meaning,
            ),
        )

    # Not found locally — return 404 for now
    # Dictionary API integration will be added as a service
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Word '{request.word}' not found",
    )
