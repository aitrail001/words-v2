import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.database import get_db
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.phrase_entry import PhraseEntry
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.translation import Translation
from app.models.user import User
from app.models.word import Word
from app.models.word_relation import WordRelation

router = APIRouter()

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


async def _browse_word_entries(db: AsyncSession, q: str | None) -> list[LexiconInspectorListEntry]:
    result = await db.execute(select(Word))
    words = result.scalars().all()
    items: list[LexiconInspectorListEntry] = []
    for word in words:
        if not _entry_matches(q, word.word, word.source_reference):
            continue
        items.append(
            LexiconInspectorListEntry(
                id=str(word.id),
                family="word",
                display_text=word.word,
                normalized_form=word.word,
                language=word.language,
                source_reference=word.source_reference,
                cefr_level=word.cefr_level,
                frequency_rank=word.frequency_rank,
                secondary_label=word.phonetic,
                created_at=_created_iso(word.created_at),
            )
        )
    return items


async def _browse_phrase_entries(db: AsyncSession, q: str | None) -> list[LexiconInspectorListEntry]:
    result = await db.execute(select(PhraseEntry))
    entries = result.scalars().all()
    items: list[LexiconInspectorListEntry] = []
    for entry in entries:
        if not _entry_matches(q, entry.phrase_text, entry.normalized_form, entry.source_reference):
            continue
        items.append(
            LexiconInspectorListEntry(
                id=str(entry.id),
                family="phrase",
                display_text=entry.phrase_text,
                normalized_form=entry.normalized_form,
                language=entry.language,
                source_reference=entry.source_reference,
                cefr_level=entry.cefr_level,
                frequency_rank=None,
                secondary_label=entry.phrase_kind,
                created_at=_created_iso(entry.created_at),
            )
        )
    return items


async def _browse_reference_entries(db: AsyncSession, q: str | None) -> list[LexiconInspectorListEntry]:
    result = await db.execute(select(ReferenceEntry))
    entries = result.scalars().all()
    items: list[LexiconInspectorListEntry] = []
    for entry in entries:
        if not _entry_matches(q, entry.display_form, entry.normalized_form, entry.source_reference):
            continue
        items.append(
            LexiconInspectorListEntry(
                id=str(entry.id),
                family="reference",
                display_text=entry.display_form,
                normalized_form=entry.normalized_form,
                language=entry.language,
                source_reference=entry.source_reference,
                cefr_level=None,
                frequency_rank=None,
                secondary_label=entry.reference_type,
                created_at=_created_iso(entry.created_at),
            )
        )
    return items


@router.get("/entries", response_model=LexiconInspectorListResponse)
async def browse_lexicon_entries(
    family: InspectorFamilyFilter = Query(default="all"),
    q: str | None = Query(default=None),
    sort: InspectorSort = Query(default="updated_desc"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    items: list[LexiconInspectorListEntry] = []
    if family in {"all", "word"}:
        items.extend(await _browse_word_entries(db, q))
    if family in {"all", "phrase"}:
        items.extend(await _browse_phrase_entries(db, q))
    if family in {"all", "reference"}:
        items.extend(await _browse_reference_entries(db, q))

    sorted_items = _sort_entries(items, sort)
    paged_items = sorted_items[offset: offset + limit]
    return LexiconInspectorListResponse(
        items=paged_items,
        total=len(sorted_items),
        family=family,
        q=q,
        limit=limit,
        offset=offset,
        has_more=offset + limit < len(sorted_items),
    )


@router.get("/entries/word/{entry_id}", response_model=LexiconInspectorWordDetail)
async def get_word_inspector_detail(
    entry_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Word).where(Word.id == entry_id))
    word = result.scalar_one_or_none()
    if word is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lexicon inspector entry not found")

    meanings_result = await db.execute(select(Meaning).where(Meaning.word_id == entry_id).order_by(Meaning.order_index))
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

    return LexiconInspectorWordDetail(
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
        learner_part_of_speech=word.learner_part_of_speech,
        confusable_words=word.confusable_words,
        word_forms=word.word_forms,
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
                secondary_domains=meaning.secondary_domains,
                register_label=meaning.register_label,
                grammar_patterns=meaning.grammar_patterns,
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
    )


@router.get("/entries/phrase/{entry_id}", response_model=LexiconInspectorPhraseDetail)
async def get_phrase_inspector_detail(
    entry_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
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

    return LexiconInspectorPhraseDetail(
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
