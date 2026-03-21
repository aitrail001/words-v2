import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.database import get_db
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_artifact_review_item_event import LexiconArtifactReviewItemEvent
from app.models.lexicon_regeneration_request import LexiconRegenerationRequest
from app.models.user import User
from tools.lexicon.validate import validate_compiled_record

router = APIRouter()


class LexiconCompiledReviewBatchResponse(BaseModel):
    id: str
    artifact_family: str
    artifact_filename: str
    artifact_sha256: str
    artifact_row_count: int
    compiled_schema_version: str
    snapshot_id: str | None
    source_type: str | None
    source_reference: str | None
    status: str
    total_items: int
    pending_count: int
    approved_count: int
    rejected_count: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class LexiconCompiledReviewItemResponse(BaseModel):
    id: str
    batch_id: str
    entry_id: str
    entry_type: str
    normalized_form: str | None
    display_text: str
    entity_category: str | None
    language: str
    frequency_rank: int | None
    cefr_level: str | None
    review_status: str
    review_priority: int
    validator_status: str | None
    validator_issues: list[dict[str, Any]] | None
    qc_status: str | None
    qc_score: float | None
    qc_issues: list[dict[str, Any]] | None
    regen_requested: bool
    import_eligible: bool
    decision_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    compiled_payload: dict[str, Any]
    compiled_payload_sha256: str
    created_at: datetime
    updated_at: datetime


class LexiconCompiledReviewItemUpdateRequest(BaseModel):
    review_status: str
    decision_reason: str | None = None


class LexiconCompiledReviewDecisionResponse(BaseModel):
    schema_version: str
    artifact_sha256: str
    entry_id: str
    entry_type: str
    decision: str
    decision_reason: str | None
    compiled_payload_sha256: str
    reviewed_by: str | None
    reviewed_at: datetime | None


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _artifact_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_family(filename: str, rows: list[dict[str, Any]]) -> str:
    if all(str(row.get("entry_type") or "word") == "phrase" for row in rows):
        return "compiled_phrases"
    if all(str(row.get("entry_type") or "word") == "reference" for row in rows):
        return "compiled_references"
    if filename.endswith("phrases.enriched.jsonl"):
        return "compiled_phrases"
    if filename.endswith("references.enriched.jsonl"):
        return "compiled_references"
    return "compiled_words"


def _decision_status(item: LexiconArtifactReviewItem) -> str:
    if item.review_status == "approved":
        return "approved"
    if item.review_status == "rejected":
        return "rejected"
    return "reopened"


def _batch_response(batch: LexiconArtifactReviewBatch) -> LexiconCompiledReviewBatchResponse:
    return LexiconCompiledReviewBatchResponse(
        id=str(batch.id),
        artifact_family=batch.artifact_family,
        artifact_filename=batch.artifact_filename,
        artifact_sha256=batch.artifact_sha256,
        artifact_row_count=batch.artifact_row_count,
        compiled_schema_version=batch.compiled_schema_version,
        snapshot_id=batch.snapshot_id,
        source_type=batch.source_type,
        source_reference=batch.source_reference,
        status=batch.status,
        total_items=batch.total_items,
        pending_count=batch.pending_count,
        approved_count=batch.approved_count,
        rejected_count=batch.rejected_count,
        created_by=str(batch.created_by) if batch.created_by else None,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        completed_at=batch.completed_at,
    )


def _item_response(item: LexiconArtifactReviewItem) -> LexiconCompiledReviewItemResponse:
    return LexiconCompiledReviewItemResponse(
        id=str(item.id),
        batch_id=str(item.batch_id),
        entry_id=item.entry_id,
        entry_type=item.entry_type,
        normalized_form=item.normalized_form,
        display_text=item.display_text,
        entity_category=item.entity_category,
        language=item.language,
        frequency_rank=item.frequency_rank,
        cefr_level=item.cefr_level,
        review_status=item.review_status,
        review_priority=item.review_priority,
        validator_status=item.validator_status,
        validator_issues=item.validator_issues,
        qc_status=item.qc_status,
        qc_score=item.qc_score,
        qc_issues=item.qc_issues,
        regen_requested=item.regen_requested,
        import_eligible=item.import_eligible,
        decision_reason=item.decision_reason,
        reviewed_by=str(item.reviewed_by) if item.reviewed_by else None,
        reviewed_at=item.reviewed_at,
        compiled_payload=item.compiled_payload,
        compiled_payload_sha256=item.compiled_payload_sha256,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _decision_response(batch: LexiconArtifactReviewBatch, item: LexiconArtifactReviewItem) -> LexiconCompiledReviewDecisionResponse:
    return LexiconCompiledReviewDecisionResponse(
        schema_version="lexicon_review_decision.v1",
        artifact_sha256=batch.artifact_sha256,
        entry_id=item.entry_id,
        entry_type=item.entry_type,
        decision=_decision_status(item),
        decision_reason=item.decision_reason,
        compiled_payload_sha256=item.compiled_payload_sha256,
        reviewed_by=str(item.reviewed_by) if item.reviewed_by else None,
        reviewed_at=item.reviewed_at,
    )


async def _batch_or_404(batch_id: uuid.UUID, db: AsyncSession) -> LexiconArtifactReviewBatch:
    result = await db.execute(select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Compiled review batch not found")
    return batch


def _refresh_batch_counts(batch: LexiconArtifactReviewBatch, items: Sequence[LexiconArtifactReviewItem]) -> None:
    approved_count = sum(1 for item in items if item.review_status == "approved")
    rejected_count = sum(1 for item in items if item.review_status == "rejected")
    total_items = len(items)
    pending_count = total_items - approved_count - rejected_count
    batch.total_items = total_items
    batch.pending_count = pending_count
    batch.approved_count = approved_count
    batch.rejected_count = rejected_count
    batch.status = "completed" if pending_count == 0 else "pending_review"
    batch.completed_at = datetime.now(timezone.utc) if pending_count == 0 else None
    batch.updated_at = datetime.now(timezone.utc)


async def _load_batch_items(batch_id: uuid.UUID, db: AsyncSession) -> list[LexiconArtifactReviewItem]:
    result = await db.execute(
        select(LexiconArtifactReviewItem)
        .where(LexiconArtifactReviewItem.batch_id == batch_id)
        .order_by(LexiconArtifactReviewItem.review_priority.asc(), LexiconArtifactReviewItem.display_text.asc())
    )
    return list(result.scalars().all())


async def _upsert_regeneration_request(
    *,
    batch: LexiconArtifactReviewBatch,
    item: LexiconArtifactReviewItem,
    current_user: User,
    db: AsyncSession,
) -> None:
    if item.review_status != "rejected":
        if item.regeneration_request is not None:
            await db.delete(item.regeneration_request)
        return

    request_payload = {
        "schema_version": "lexicon_review_decision.v1",
        "artifact_sha256": batch.artifact_sha256,
        "entry_id": item.entry_id,
        "entry_type": item.entry_type,
        "normalized_form": item.normalized_form,
        "compiled_payload_sha256": item.compiled_payload_sha256,
        "decision_reason": item.decision_reason,
    }
    if item.regeneration_request is None:
        db.add(
            LexiconRegenerationRequest(
                batch_id=batch.id,
                item_id=item.id,
                entry_id=item.entry_id,
                entry_type=item.entry_type,
                artifact_sha256=batch.artifact_sha256,
                request_reason=item.decision_reason,
                request_payload=request_payload,
                created_by=current_user.id,
            )
        )
        return

    item.regeneration_request.request_status = "pending"
    item.regeneration_request.request_reason = item.decision_reason
    item.regeneration_request.request_payload = request_payload


@router.post("/batches/import", response_model=LexiconCompiledReviewBatchResponse, status_code=status.HTTP_201_CREATED)
async def import_compiled_review_batch(
    file: UploadFile = File(...),
    source_type: str | None = Form(default="lexicon_compiled_export"),
    source_reference: str | None = Form(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    payload_bytes = await file.read()
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload_bytes.decode("utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Compiled review import line {line_number} is not valid JSON: {exc.msg}") from exc
        errors = validate_compiled_record(row)
        if errors:
            raise HTTPException(status_code=400, detail=f"Compiled review import validation failed: {'; '.join(errors)}")
        rows.append(row)
    if not rows:
        raise HTTPException(status_code=400, detail="Compiled review import file is empty")

    seen_entry_ids: set[str] = set()
    for row in rows:
        entry_id = str(row.get("entry_id") or "").strip()
        if entry_id in seen_entry_ids:
            raise HTTPException(status_code=400, detail=f"Compiled review import contains duplicate entry_id: {entry_id}")
        seen_entry_ids.add(entry_id)

    artifact_sha256 = _artifact_sha256_bytes(payload_bytes)
    existing_result = await db.execute(
        select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.artifact_sha256 == artifact_sha256)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return _batch_response(existing)

    artifact_family = _artifact_family(file.filename or "", rows)
    batch = LexiconArtifactReviewBatch(
        artifact_family=artifact_family,
        artifact_filename=file.filename or "compiled.jsonl",
        artifact_sha256=artifact_sha256,
        artifact_row_count=len(rows),
        compiled_schema_version=str(rows[0].get("schema_version") or ""),
        snapshot_id=str(rows[0].get("snapshot_id") or "") or None,
        source_type=source_type,
        source_reference=source_reference,
        status="pending_review",
        total_items=len(rows),
        pending_count=len(rows),
        approved_count=0,
        rejected_count=0,
        created_by=current_user.id,
    )
    db.add(batch)
    await db.flush()

    for row in rows:
        item = LexiconArtifactReviewItem(
            batch_id=batch.id,
            entry_id=str(row.get("entry_id") or ""),
            entry_type=str(row.get("entry_type") or "word"),
            normalized_form=str(row.get("normalized_form") or "") or None,
            display_text=str(row.get("display_form") or row.get("word") or row.get("normalized_form") or ""),
            entity_category=str(row.get("entity_category") or "") or None,
            language=str(row.get("language") or "en"),
            frequency_rank=row.get("frequency_rank"),
            cefr_level=str(row.get("cefr_level") or "") or None,
            validator_status="pass",
            validator_issues=[],
            qc_status=None,
            qc_score=None,
            qc_issues=[],
            compiled_payload=row,
            compiled_payload_sha256=_payload_sha256(row),
            search_text=" ".join(
                str(value) for value in [row.get("entry_id"), row.get("normalized_form"), row.get("display_form"), row.get("word")] if value
            ),
        )
        db.add(item)
    await db.commit()
    return _batch_response(batch)


@router.get("/batches", response_model=list[LexiconCompiledReviewBatchResponse])
async def list_compiled_review_batches(
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LexiconArtifactReviewBatch)
        .order_by(LexiconArtifactReviewBatch.created_at.desc())
    )
    return [_batch_response(batch) for batch in result.scalars().all()]


@router.get("/batches/{batch_id}", response_model=LexiconCompiledReviewBatchResponse)
async def get_compiled_review_batch(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return _batch_response(await _batch_or_404(batch_id, db))


@router.get("/batches/{batch_id}/items", response_model=list[LexiconCompiledReviewItemResponse])
async def list_compiled_review_items(
    batch_id: uuid.UUID,
    review_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await _batch_or_404(batch_id, db)
    query = select(LexiconArtifactReviewItem).where(LexiconArtifactReviewItem.batch_id == batch_id)
    if review_status:
        query = query.where(LexiconArtifactReviewItem.review_status == review_status)
    if search:
        search_text = f"%{search.strip().lower()}%"
        query = query.where(LexiconArtifactReviewItem.search_text.ilike(search_text))
    query = query.order_by(LexiconArtifactReviewItem.review_priority.asc(), LexiconArtifactReviewItem.display_text.asc())
    result = await db.execute(query)
    return [_item_response(item) for item in result.scalars().all()]


@router.patch("/items/{item_id}", response_model=LexiconCompiledReviewItemResponse)
async def update_compiled_review_item(
    item_id: uuid.UUID,
    request: LexiconCompiledReviewItemUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LexiconArtifactReviewItem).where(LexiconArtifactReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Compiled review item not found")
    batch = await _batch_or_404(item.batch_id, db)
    if request.review_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid compiled review status")

    previous_status = item.review_status
    item.review_status = request.review_status
    item.decision_reason = request.decision_reason
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.updated_at = datetime.now(timezone.utc)
    item.import_eligible = request.review_status == "approved"
    item.regen_requested = request.review_status == "rejected"
    await _upsert_regeneration_request(batch=batch, item=item, current_user=current_user, db=db)
    db.add(
        LexiconArtifactReviewItemEvent(
            item_id=item.id,
            event_type=request.review_status,
            from_status=previous_status,
            to_status=request.review_status,
            actor_user_id=current_user.id,
            reason=request.decision_reason,
        )
    )
    _refresh_batch_counts(batch, await _load_batch_items(batch.id, db))
    await db.commit()
    return _item_response(item)


@router.get("/batches/{batch_id}/export/approved")
async def export_approved_compiled_rows(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await _batch_or_404(batch_id, db)
    result = await db.execute(
        select(LexiconArtifactReviewItem)
        .where(
            LexiconArtifactReviewItem.batch_id == batch_id,
            LexiconArtifactReviewItem.review_status == "approved",
        )
        .order_by(LexiconArtifactReviewItem.display_text.asc())
    )
    approved_items = [
        item
        for item in result.scalars().all()
        if item.review_status == "approved" and item.import_eligible
    ]
    body = "".join(json.dumps(item.compiled_payload, ensure_ascii=False) + "\n" for item in approved_items)
    return Response(content=body, media_type="application/x-ndjson")


@router.get("/batches/{batch_id}/export/rejected")
async def export_rejected_compiled_rows(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _batch_or_404(batch_id, db)
    result = await db.execute(
        select(LexiconArtifactReviewItem)
        .where(LexiconArtifactReviewItem.batch_id == batch_id)
        .order_by(LexiconArtifactReviewItem.display_text.asc())
    )
    rejected_items = [item for item in result.scalars().all() if item.review_status == "rejected"]
    body = "".join(
        json.dumps(
            {
                **item.compiled_payload,
                "entry_id": item.entry_id,
                "entry_type": item.entry_type,
                "artifact_sha256": batch.artifact_sha256,
                "decision": _decision_status(item),
                "decision_reason": item.decision_reason,
                "compiled_payload_sha256": item.compiled_payload_sha256,
                "reviewed_by": str(item.reviewed_by) if item.reviewed_by else None,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            },
            ensure_ascii=False,
        )
        + "\n"
        for item in rejected_items
    )
    return Response(content=body, media_type="application/x-ndjson")


@router.get("/batches/{batch_id}/export/regenerate")
async def export_regenerate_compiled_rows(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _batch_or_404(batch_id, db)
    result = await db.execute(
        select(LexiconArtifactReviewItem)
        .where(LexiconArtifactReviewItem.batch_id == batch_id)
        .order_by(LexiconArtifactReviewItem.display_text.asc())
    )
    regenerate_items = [item for item in result.scalars().all() if item.review_status == "rejected" and item.regen_requested]
    body = "".join(
        json.dumps(
            {
                "schema_version": "lexicon_review_decision.v1",
                "entry_id": item.entry_id,
                "entry_type": item.entry_type,
                "normalized_form": item.normalized_form,
                "artifact_sha256": batch.artifact_sha256,
                "compiled_payload_sha256": item.compiled_payload_sha256,
                "decision_reason": item.decision_reason,
            },
            ensure_ascii=False,
        )
        + "\n"
        for item in regenerate_items
    )
    return Response(content=body, media_type="application/x-ndjson")


@router.get("/batches/{batch_id}/export/decisions")
async def export_compiled_review_decisions(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _batch_or_404(batch_id, db)
    items = await _load_batch_items(batch.id, db)
    decision_items = [item for item in items if item.review_status in {"approved", "rejected"}]
    body = "".join(
        json.dumps(_decision_response(batch, item).model_dump(mode="json"), ensure_ascii=False) + "\n"
        for item in decision_items
    )
    return Response(content=body, media_type="application/x-ndjson")
