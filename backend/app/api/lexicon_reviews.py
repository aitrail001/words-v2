import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.database import get_db
from app.models.lexicon_review_batch import LexiconReviewBatch
from app.models.lexicon_review_item import LexiconReviewItem
from app.models.meaning import Meaning
from app.models.user import User
from app.models.word import Word

router = APIRouter()

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_LINES = 50000
REQUIRED_ROW_FIELDS = {
    'schema_version',
    'snapshot_id',
    'lexeme_id',
    'lemma',
    'language',
    'risk_band',
    'selection_risk_score',
    'deterministic_selected_wn_synset_ids',
    'candidate_metadata',
    'generated_at',
    'generation_run_id',
}
ALLOWED_REVIEW_STATUSES = {'pending', 'approved', 'rejected', 'needs_edit'}


class LexiconReviewBatchResponse(BaseModel):
    id: str
    user_id: str
    status: str
    source_filename: str
    source_hash: str
    source_type: str | None
    source_reference: str | None
    snapshot_id: str | None
    total_items: int
    review_required_count: int
    auto_accepted_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class LexiconReviewItemResponse(BaseModel):
    id: str
    batch_id: str
    lexeme_id: str
    lemma: str
    language: str
    wordfreq_rank: int | None
    risk_band: str
    selection_risk_score: int
    deterministic_selected_wn_synset_ids: list[str]
    reranked_selected_wn_synset_ids: list[str] | None
    candidate_metadata: list[dict[str, Any]]
    auto_accepted: bool
    review_required: bool
    review_status: str
    review_override_wn_synset_ids: list[str] | None
    review_comment: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    row_payload: dict[str, Any]
    created_at: datetime


class LexiconReviewItemUpdateRequest(BaseModel):
    review_status: str = Field(...)
    review_comment: str | None = None
    review_override_wn_synset_ids: list[str] | None = None


class LexiconReviewBatchPublishPreviewItemResponse(BaseModel):
    item_id: str
    lemma: str
    language: str
    action: str
    selected_synset_ids: list[str]
    existing_lexicon_meaning_count: int
    new_meaning_count: int
    warnings: list[str]


class LexiconReviewBatchPublishPreviewResponse(BaseModel):
    batch_id: str
    publishable_item_count: int
    created_word_count: int
    updated_word_count: int
    replaced_meaning_count: int
    created_meaning_count: int
    skipped_item_count: int
    items: list[LexiconReviewBatchPublishPreviewItemResponse]


class LexiconReviewBatchPublishResponse(BaseModel):
    batch_id: str
    status: str
    published_item_count: int
    published_word_count: int
    updated_word_count: int
    replaced_meaning_count: int
    created_meaning_count: int
    published_at: datetime


PUBLISH_SOURCE_TYPE = "lexicon_review_publish"


def _publish_source_reference(batch_id: uuid.UUID) -> str:
    return f"lexicon_review_batch:{batch_id}"


def _meaning_source_reference(batch_id: uuid.UUID, lexeme_id: str, order_index: int) -> str:
    return f"{_publish_source_reference(batch_id)}:{lexeme_id}:{order_index}"


def _selected_publish_ids(item: LexiconReviewItem) -> list[str]:
    for candidate in (item.review_override_wn_synset_ids, item.reranked_selected_wn_synset_ids, item.deterministic_selected_wn_synset_ids):
        if candidate:
            return [str(value) for value in candidate]
    return []


def _candidate_metadata_by_id(item: LexiconReviewItem) -> dict[str, dict[str, Any]]:
    return {str(entry.get("wn_synset_id") or ""): entry for entry in item.candidate_metadata or []}


def _resolve_publish_meanings(item: LexiconReviewItem) -> list[dict[str, Any]]:
    metadata_by_id = _candidate_metadata_by_id(item)
    meanings: list[dict[str, Any]] = []
    for order_index, synset_id in enumerate(_selected_publish_ids(item)):
        metadata = metadata_by_id.get(synset_id)
        if metadata is None:
            raise HTTPException(status_code=400, detail=f"Publish metadata missing for selected synset {synset_id} on lexeme {item.lexeme_id}")
        definition = str(metadata.get("canonical_gloss") or "").strip()
        if not definition:
            raise HTTPException(status_code=400, detail=f"Publish definition missing for selected synset {synset_id} on lexeme {item.lexeme_id}")
        meanings.append({
            "definition": definition,
            "part_of_speech": str(metadata.get("part_of_speech") or "") or None,
            "order_index": order_index,
            "source_reference": _meaning_source_reference(item.batch_id, item.lexeme_id, order_index),
        })
    return meanings


async def _build_publish_plan(batch: LexiconReviewBatch, db: AsyncSession) -> dict[str, Any]:
    items_result = await db.execute(
        select(LexiconReviewItem)
        .where(LexiconReviewItem.batch_id == batch.id)
        .order_by(LexiconReviewItem.lemma.asc())
    )
    items = items_result.scalars().all()
    publishable_items = [item for item in items if item.review_status == 'approved']
    if not publishable_items:
        raise HTTPException(status_code=400, detail='No approved lexicon review items are publishable')

    plan_items: list[dict[str, Any]] = []
    created_word_count = 0
    updated_word_count = 0
    replaced_meaning_count = 0
    created_meaning_count = 0
    for item in publishable_items:
        publish_meanings = _resolve_publish_meanings(item)
        word_result = await db.execute(
            select(Word).where(Word.word == item.lemma, Word.language == item.language)
        )
        existing_word = word_result.scalar_one_or_none()
        action = 'create_word' if existing_word is None else 'update_word'
        if action == 'create_word':
            created_word_count += 1
        else:
            updated_word_count += 1

        existing_lexicon_meanings: list[Meaning] = []
        if existing_word is not None:
            existing_meanings_result = await db.execute(
                select(Meaning).where(Meaning.word_id == existing_word.id).order_by(Meaning.order_index.asc())
            )
            existing_meanings = existing_meanings_result.scalars().all()
            existing_lexicon_meanings = [meaning for meaning in existing_meanings if meaning.source == PUBLISH_SOURCE_TYPE]
            replaced_meaning_count += len(existing_lexicon_meanings)

        created_meaning_count += len(publish_meanings)
        plan_items.append({
            'item': item,
            'existing_word': existing_word,
            'action': action,
            'selected_synset_ids': _selected_publish_ids(item),
            'publish_meanings': publish_meanings,
            'existing_lexicon_meanings': existing_lexicon_meanings,
            'warnings': [],
        })

    return {
        'batch': batch,
        'items': plan_items,
        'publishable_item_count': len(plan_items),
        'created_word_count': created_word_count,
        'updated_word_count': updated_word_count,
        'replaced_meaning_count': replaced_meaning_count,
        'created_meaning_count': created_meaning_count,
        'skipped_item_count': len(items) - len(plan_items),
    }


def _to_batch_response(batch: LexiconReviewBatch) -> LexiconReviewBatchResponse:
    return LexiconReviewBatchResponse(
        id=str(batch.id),
        user_id=str(batch.user_id),
        status=batch.status,
        source_filename=batch.source_filename,
        source_hash=batch.source_hash,
        source_type=batch.source_type,
        source_reference=batch.source_reference,
        snapshot_id=batch.snapshot_id,
        total_items=batch.total_items,
        review_required_count=batch.review_required_count,
        auto_accepted_count=batch.auto_accepted_count,
        error_message=batch.error_message,
        created_at=batch.created_at,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
    )


def _to_item_response(item: LexiconReviewItem) -> LexiconReviewItemResponse:
    return LexiconReviewItemResponse(
        id=str(item.id),
        batch_id=str(item.batch_id),
        lexeme_id=item.lexeme_id,
        lemma=item.lemma,
        language=item.language,
        wordfreq_rank=item.wordfreq_rank,
        risk_band=item.risk_band,
        selection_risk_score=item.selection_risk_score,
        deterministic_selected_wn_synset_ids=item.deterministic_selected_wn_synset_ids,
        reranked_selected_wn_synset_ids=item.reranked_selected_wn_synset_ids,
        candidate_metadata=item.candidate_metadata,
        auto_accepted=item.auto_accepted,
        review_required=item.review_required,
        review_status=item.review_status,
        review_override_wn_synset_ids=item.review_override_wn_synset_ids,
        review_comment=item.review_comment,
        reviewed_by=str(item.reviewed_by) if item.reviewed_by else None,
        reviewed_at=item.reviewed_at,
        row_payload=item.row_payload,
        created_at=item.created_at,
    )


async def _get_batch_for_user(batch_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> LexiconReviewBatch:
    result = await db.execute(
        select(LexiconReviewBatch).where(
            LexiconReviewBatch.id == batch_id,
            LexiconReviewBatch.user_id == user_id,
        )
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail='Lexicon review batch not found')
    return batch


async def _get_item_for_user(item_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> LexiconReviewItem:
    result = await db.execute(
        select(LexiconReviewItem)
        .join(LexiconReviewBatch, LexiconReviewItem.batch_id == LexiconReviewBatch.id)
        .where(LexiconReviewItem.id == item_id, LexiconReviewBatch.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail='Lexicon review item not found')
    return item


def _validate_row(row: dict[str, Any], *, line_number: int, seen_lexeme_ids: set[str]) -> None:
    missing = sorted(field for field in REQUIRED_ROW_FIELDS if field not in row)
    if missing:
        raise HTTPException(status_code=400, detail=f'line {line_number}: missing required fields: {", ".join(missing)}')
    lexeme_id = str(row.get('lexeme_id') or '').strip()
    if not lexeme_id:
        raise HTTPException(status_code=400, detail=f'line {line_number}: lexeme_id must not be empty')
    if lexeme_id in seen_lexeme_ids:
        raise HTTPException(status_code=400, detail=f'line {line_number}: duplicate lexeme_id: {lexeme_id}')
    seen_lexeme_ids.add(lexeme_id)
    if not isinstance(row.get('deterministic_selected_wn_synset_ids'), list):
        raise HTTPException(status_code=400, detail=f'line {line_number}: deterministic_selected_wn_synset_ids must be a list')
    if not isinstance(row.get('candidate_metadata'), list):
        raise HTTPException(status_code=400, detail=f'line {line_number}: candidate_metadata must be a list')


async def _parse_upload(file: UploadFile) -> tuple[bytes, list[dict[str, Any]]]:
    filename = (file.filename or '').strip()
    if not filename.lower().endswith('.jsonl'):
        raise HTTPException(status_code=400, detail='Only .jsonl files are supported')
    payload = await file.read()
    await file.close()
    if len(payload) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail='Import file exceeds size limit')
    try:
        text = payload.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail='Import file must be UTF-8 encoded') from exc
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail='Import file is empty')
    if len(lines) > MAX_IMPORT_LINES:
        raise HTTPException(status_code=400, detail='Import file exceeds line limit')
    rows: list[dict[str, Any]] = []
    seen_lexeme_ids: set[str] = set()
    snapshot_id: str | None = None
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f'line {index}: invalid JSON') from exc
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail=f'line {index}: each row must be a JSON object')
        _validate_row(row, line_number=index, seen_lexeme_ids=seen_lexeme_ids)
        row_snapshot_id = str(row.get('snapshot_id') or '').strip()
        if snapshot_id is None:
            snapshot_id = row_snapshot_id
        elif row_snapshot_id != snapshot_id:
            raise HTTPException(status_code=400, detail=f'line {index}: snapshot_id must match the first row')
        rows.append(row)
    return payload, rows


@router.post('/batches/import', response_model=LexiconReviewBatchResponse, status_code=status.HTTP_201_CREATED)
async def import_lexicon_review_batch(
    response: Response,
    file: UploadFile = File(...),
    source_type: str | None = Form(default='lexicon_selection_decisions'),
    source_reference: str | None = Form(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconReviewBatchResponse:
    payload, rows = await _parse_upload(file)
    source_hash = hashlib.sha256(payload).hexdigest()
    existing_result = await db.execute(
        select(LexiconReviewBatch)
        .where(LexiconReviewBatch.user_id == current_user.id)
        .where(LexiconReviewBatch.source_hash == source_hash)
        .order_by(LexiconReviewBatch.created_at.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None and existing.status == 'importing':
        response.status_code = status.HTTP_202_ACCEPTED
        return _to_batch_response(existing)
    if existing is not None and existing.status in {'imported', 'reviewing', 'published'}:
        response.status_code = status.HTTP_200_OK
        return _to_batch_response(existing)

    now = datetime.now(timezone.utc)
    batch = LexiconReviewBatch(
        id=uuid.uuid4(),
        user_id=current_user.id,
        status='imported',
        source_filename=(file.filename or '').strip(),
        source_hash=source_hash,
        source_type=source_type,
        source_reference=source_reference,
        snapshot_id=str(rows[0].get('snapshot_id') or ''),
        total_items=len(rows),
        review_required_count=sum(1 for row in rows if bool(row.get('review_required'))),
        auto_accepted_count=sum(1 for row in rows if bool(row.get('auto_accepted'))),
        import_metadata={
            'schema_versions': sorted({str(row.get('schema_version') or '') for row in rows}),
            'line_count': len(rows),
        },
        started_at=now,
        completed_at=now,
        created_at=now,
    )
    db.add(batch)
    for row in rows:
        item = LexiconReviewItem(
            id=uuid.uuid4(),
            batch_id=batch.id,
            lexeme_id=str(row.get('lexeme_id') or ''),
            lemma=str(row.get('lemma') or ''),
            language=str(row.get('language') or 'en'),
            wordfreq_rank=row.get('wordfreq_rank'),
            risk_band=str(row.get('risk_band') or ''),
            selection_risk_score=int(row.get('selection_risk_score') or 0),
            deterministic_selected_wn_synset_ids=[str(item) for item in row.get('deterministic_selected_wn_synset_ids') or []],
            reranked_selected_wn_synset_ids=[str(item) for item in row.get('reranked_selected_wn_synset_ids') or []] or None,
            candidate_metadata=list(row.get('candidate_metadata') or []),
            auto_accepted=bool(row.get('auto_accepted')),
            review_required=bool(row.get('review_required')),
            review_status='approved' if bool(row.get('auto_accepted')) else 'pending',
            review_override_wn_synset_ids=None,
            row_payload=row,
        )
        db.add(item)
    await db.commit()
    return _to_batch_response(batch)


@router.get('/batches', response_model=list[LexiconReviewBatchResponse])
async def list_lexicon_review_batches(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[LexiconReviewBatchResponse]:
    result = await db.execute(
        select(LexiconReviewBatch)
        .where(LexiconReviewBatch.user_id == current_user.id)
        .order_by(LexiconReviewBatch.created_at.desc())
        .limit(50)
    )
    batches = result.scalars().all()
    return [_to_batch_response(batch) for batch in batches]


@router.get('/batches/{batch_id}', response_model=LexiconReviewBatchResponse)
async def get_lexicon_review_batch(
    batch_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconReviewBatchResponse:
    batch = await _get_batch_for_user(batch_id, current_user.id, db)
    return _to_batch_response(batch)


@router.get('/batches/{batch_id}/items', response_model=list[LexiconReviewItemResponse])
async def list_lexicon_review_items(
    batch_id: uuid.UUID,
    review_status: str | None = Query(default=None),
    risk_band: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[LexiconReviewItemResponse]:
    await _get_batch_for_user(batch_id, current_user.id, db)
    query = select(LexiconReviewItem).where(LexiconReviewItem.batch_id == batch_id)
    if review_status is not None:
        query = query.where(LexiconReviewItem.review_status == review_status)
    if risk_band is not None:
        query = query.where(LexiconReviewItem.risk_band == risk_band)
    if review_required is not None:
        query = query.where(LexiconReviewItem.review_required == review_required)
    query = query.order_by(
        LexiconReviewItem.review_required.desc(),
        LexiconReviewItem.selection_risk_score.desc(),
        LexiconReviewItem.lemma.asc(),
    )
    result = await db.execute(query)
    items = result.scalars().all()
    return [_to_item_response(item) for item in items]


@router.get('/batches/{batch_id}/publish-preview', response_model=LexiconReviewBatchPublishPreviewResponse)
async def preview_lexicon_review_batch_publish(
    batch_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconReviewBatchPublishPreviewResponse:
    batch = await _get_batch_for_user(batch_id, current_user.id, db)
    plan = await _build_publish_plan(batch, db)
    return LexiconReviewBatchPublishPreviewResponse(
        batch_id=str(batch.id),
        publishable_item_count=plan['publishable_item_count'],
        created_word_count=plan['created_word_count'],
        updated_word_count=plan['updated_word_count'],
        replaced_meaning_count=plan['replaced_meaning_count'],
        created_meaning_count=plan['created_meaning_count'],
        skipped_item_count=plan['skipped_item_count'],
        items=[
            LexiconReviewBatchPublishPreviewItemResponse(
                item_id=str(entry['item'].id),
                lemma=entry['item'].lemma,
                language=entry['item'].language,
                action=entry['action'],
                selected_synset_ids=entry['selected_synset_ids'],
                existing_lexicon_meaning_count=len(entry['existing_lexicon_meanings']),
                new_meaning_count=len(entry['publish_meanings']),
                warnings=entry['warnings'],
            )
            for entry in plan['items']
        ],
    )


@router.post('/batches/{batch_id}/publish', response_model=LexiconReviewBatchPublishResponse)
async def publish_lexicon_review_batch(
    batch_id: uuid.UUID,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconReviewBatchPublishResponse:
    batch = await _get_batch_for_user(batch_id, current_user.id, db)
    plan = await _build_publish_plan(batch, db)
    publish_reference = _publish_source_reference(batch.id)

    for entry in plan['items']:
        item = entry['item']
        word = entry['existing_word']
        if word is None:
            word = Word(
                word=item.lemma,
                language=item.language,
                frequency_rank=item.wordfreq_rank,
                source_type=PUBLISH_SOURCE_TYPE,
                source_reference=publish_reference,
            )
            db.add(word)
            await db.flush()
        else:
            word.frequency_rank = item.wordfreq_rank
            word.source_type = PUBLISH_SOURCE_TYPE
            word.source_reference = publish_reference

        for meaning in entry['existing_lexicon_meanings']:
            await db.delete(meaning)

        for meaning_payload in entry['publish_meanings']:
            db.add(Meaning(
                word_id=word.id,
                definition=meaning_payload['definition'],
                part_of_speech=meaning_payload['part_of_speech'],
                example_sentence=None,
                order_index=meaning_payload['order_index'],
                source=PUBLISH_SOURCE_TYPE,
                source_reference=meaning_payload['source_reference'],
            ))

    published_at = datetime.now(timezone.utc)
    batch.status = 'published'
    summary = dict(batch.import_metadata or {})
    summary['publish_summary'] = {
        'published_at': published_at.isoformat(),
        'published_item_count': plan['publishable_item_count'],
        'published_word_count': plan['created_word_count'],
        'updated_word_count': plan['updated_word_count'],
        'replaced_meaning_count': plan['replaced_meaning_count'],
        'created_meaning_count': plan['created_meaning_count'],
    }
    batch.import_metadata = summary
    batch.completed_at = published_at
    await db.commit()
    return LexiconReviewBatchPublishResponse(
        batch_id=str(batch.id),
        status=batch.status,
        published_item_count=plan['publishable_item_count'],
        published_word_count=plan['created_word_count'],
        updated_word_count=plan['updated_word_count'],
        replaced_meaning_count=plan['replaced_meaning_count'],
        created_meaning_count=plan['created_meaning_count'],
        published_at=published_at,
    )


@router.patch('/items/{item_id}', response_model=LexiconReviewItemResponse)
async def update_lexicon_review_item(
    item_id: uuid.UUID,
    request: LexiconReviewItemUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconReviewItemResponse:
    if request.review_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid review_status')
    item = await _get_item_for_user(item_id, current_user.id, db)
    item.review_status = request.review_status
    item.review_comment = request.review_comment
    item.review_override_wn_synset_ids = request.review_override_wn_synset_ids
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return _to_item_response(item)
