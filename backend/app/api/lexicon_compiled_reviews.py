import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_artifact_review_item_event import LexiconArtifactReviewItemEvent
from app.models.lexicon_regeneration_request import LexiconRegenerationRequest
from app.models.user import User
from app.services.lexicon_jsonl_reviews import (
    APPROVED_FILENAME,
    DECISIONS_FILENAME,
    REGENERATE_FILENAME,
    REJECTED_FILENAME,
    resolve_repo_local_path,
)

router = APIRouter()

REQUIRED_TRANSLATION_LOCALES = ["zh-Hans", "es", "ar", "pt-BR", "ja"]
ALLOWED_ENTITY_CATEGORIES = {"general", "name", "place", "brand", "entity_other"}
REQUIRED_COMPILED_FIELDS = [
    "schema_version",
    "entry_id",
    "entry_type",
    "normalized_form",
    "source_provenance",
    "word",
    "part_of_speech",
    "cefr_level",
    "frequency_rank",
    "forms",
    "senses",
    "confusable_words",
    "generated_at",
]


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


class LexiconCompiledReviewImportByPathRequest(BaseModel):
    artifact_path: str
    source_type: str | None = "lexicon_compiled_export"
    source_reference: str | None = None


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


class LexiconCompiledReviewMaterializeRequest(BaseModel):
    output_dir: str | None = None


class LexiconCompiledReviewMaterializeResponse(BaseModel):
    decision_count: int
    approved_count: int
    rejected_count: int
    regenerate_count: int
    decisions_output_path: str
    approved_output_path: str
    rejected_output_path: str
    regenerate_output_path: str


def _compiled_meaning_limit(frequency_rank: Any) -> int:
    try:
        rank = int(frequency_rank)
    except (TypeError, ValueError):
        return 4
    if rank <= 0:
        return 4
    if rank <= 5000:
        return 8
    if rank <= 10000:
        return 6
    return 4


def _validate_compiled_sense_translations(value: Any, *, sense_index: int, example_count: int) -> list[str]:
    errors: list[str] = []
    if value in (None, {}):
        return errors
    if not isinstance(value, dict):
        return [f"sense {sense_index} translations must be an object keyed by locale"]
    for locale in REQUIRED_TRANSLATION_LOCALES:
        locale_payload = value.get(locale)
        if not isinstance(locale_payload, dict):
            errors.append(f"sense {sense_index} translations must include locale {locale}")
            continue
        if not isinstance(locale_payload.get("definition"), str) or not locale_payload.get("definition", "").strip():
            errors.append(f"sense {sense_index} translations.{locale}.definition must be a non-empty string")
        if not isinstance(locale_payload.get("usage_note"), str) or not locale_payload.get("usage_note", "").strip():
            errors.append(f"sense {sense_index} translations.{locale}.usage_note must be a non-empty string")
        examples = locale_payload.get("examples")
        if not isinstance(examples, list) or not examples:
            errors.append(f"sense {sense_index} translations.{locale}.examples must be a non-empty list")
            continue
        if len(examples) != example_count:
            errors.append(f"sense {sense_index} translations.{locale}.examples must align with English example count {example_count}")
            continue
        for example_index, example in enumerate(examples, start=1):
            if not isinstance(example, str) or not example.strip():
                errors.append(f"sense {sense_index} translations.{locale}.examples[{example_index}] must be a non-empty string")
    return errors


def _validate_compiled_record(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_COMPILED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    entry_type = payload.get("entry_type")
    if entry_type not in {None, "word", "phrase", "reference"}:
        errors.append(f"unsupported entry_type: {payload.get('entry_type')}")

    source_provenance = payload.get("source_provenance")
    if source_provenance is not None and not isinstance(source_provenance, list):
        errors.append("source_provenance must be a list")

    entity_category = payload.get("entity_category", "general")
    if entity_category not in ALLOWED_ENTITY_CATEGORIES:
        errors.append(f"unsupported entity_category: {entity_category}")

    senses = payload.get("senses", [])
    if isinstance(senses, list) and entry_type in {None, "word"}:
        max_senses = _compiled_meaning_limit(payload.get("frequency_rank"))
        if len(senses) > max_senses:
            errors.append(f"senses exceeds allowed limit {max_senses} for frequency_rank {payload.get('frequency_rank')}")
        for index, sense in enumerate(senses, start=1):
            examples = sense.get("examples", []) if isinstance(sense, dict) else []
            if not examples:
                errors.append(f"sense {index} must include at least one example")
            if isinstance(sense, dict):
                errors.extend(_validate_compiled_sense_translations(sense.get("translations"), sense_index=index, example_count=len(examples)))

    if entry_type == "phrase":
        for field in ("phrase_kind", "display_form", "normalized_form", "generated_at"):
            if field not in payload or payload.get(field) in (None, ""):
                errors.append(f"missing required phrase field: {field}")
        if not isinstance(payload.get("part_of_speech"), list):
            errors.append("phrase part_of_speech must be a list")

    if entry_type == "reference":
        for field in ("reference_type", "display_form", "normalized_form", "translation_mode", "brief_description", "pronunciation", "generated_at"):
            if field not in payload or payload.get(field) in (None, ""):
                errors.append(f"missing required reference field: {field}")
        for field in ("localized_display_form", "localized_brief_description", "localizations"):
            if field in payload and payload.get(field) is not None and not isinstance(payload.get(field), (dict, list)):
                errors.append(f"{field} must be an object or list")

    return errors


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _artifact_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_compiled_rows(payload_bytes: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload_bytes.decode("utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Compiled review import line {line_number} is not valid JSON: {exc.msg}") from exc
        errors = _validate_compiled_record(row)
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
    return rows


async def _persist_compiled_review_batch(
    *,
    artifact_filename: str,
    payload_bytes: bytes,
    rows: list[dict[str, Any]],
    source_type: str | None,
    source_reference: str | None,
    current_user: User,
    db: AsyncSession,
) -> LexiconCompiledReviewBatchResponse:
    artifact_sha256 = _artifact_sha256_bytes(payload_bytes)
    existing_result = await db.execute(
        select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.artifact_sha256 == artifact_sha256)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return _batch_response(existing)

    artifact_family = _artifact_family(artifact_filename, rows)
    batch = LexiconArtifactReviewBatch(
        artifact_family=artifact_family,
        artifact_filename=artifact_filename,
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


def _batch_reviewed_output_dir(batch: LexiconArtifactReviewBatch, settings: Settings) -> Path:
    source_reference = str(batch.source_reference or "").strip()
    if source_reference:
        snapshot_root = Path(settings.lexicon_snapshot_root).expanduser()
        if not snapshot_root.is_absolute():
            snapshot_root = (Path.cwd() / snapshot_root).resolve()
        candidate = (snapshot_root / source_reference / "reviewed").resolve()
        try:
            candidate.relative_to(snapshot_root)
            return candidate
        except ValueError:
            pass
    return (Path.cwd() / "data" / "lexicon" / "compiled-review" / str(batch.id)).resolve()


def _materialized_rows(
    batch: LexiconArtifactReviewBatch,
    items: Sequence[LexiconArtifactReviewItem],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    approved_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    regenerate_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    for item in items:
        if item.review_status not in {"approved", "rejected"}:
            continue
        decision = _decision_response(batch, item).model_dump(mode="json")
        decision_rows.append(decision)
        if item.review_status == "approved" and item.import_eligible:
            approved_rows.append(item.compiled_payload)
            continue
        if item.review_status == "rejected":
            rejected_rows.append(
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
                }
            )
            if item.regen_requested:
                regenerate_rows.append(
                    {
                        "schema_version": "lexicon_review_decision.v1",
                        "entry_id": item.entry_id,
                        "entry_type": item.entry_type,
                        "normalized_form": item.normalized_form,
                        "artifact_sha256": batch.artifact_sha256,
                        "compiled_payload_sha256": item.compiled_payload_sha256,
                        "decision_reason": item.decision_reason,
                    }
                )
    return approved_rows, rejected_rows, regenerate_rows, decision_rows


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


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
    existing_result = await db.execute(
        select(LexiconRegenerationRequest).where(LexiconRegenerationRequest.item_id == item.id)
    )
    existing_request = existing_result.scalar_one_or_none()

    if item.review_status != "rejected":
        if existing_request is not None:
            await db.delete(existing_request)
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
    if existing_request is None:
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

    existing_request.request_status = "pending"
    existing_request.request_reason = item.decision_reason
    existing_request.request_payload = request_payload


@router.post("/batches/import", response_model=LexiconCompiledReviewBatchResponse, status_code=status.HTTP_201_CREATED)
async def import_compiled_review_batch(
    file: UploadFile = File(...),
    source_type: str | None = Form(default="lexicon_compiled_export"),
    source_reference: str | None = Form(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    payload_bytes = await file.read()
    rows = _parse_compiled_rows(payload_bytes)
    return await _persist_compiled_review_batch(
        artifact_filename=file.filename or "compiled.jsonl",
        payload_bytes=payload_bytes,
        rows=rows,
        source_type=source_type,
        source_reference=source_reference,
        current_user=current_user,
        db=db,
    )


@router.post("/batches/import-by-path", response_model=LexiconCompiledReviewBatchResponse, status_code=status.HTTP_201_CREATED)
async def import_compiled_review_batch_by_path(
    request: LexiconCompiledReviewImportByPathRequest,
    current_user: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    artifact_path = resolve_repo_local_path(request.artifact_path, settings=settings)
    if artifact_path.suffix != ".jsonl":
        raise HTTPException(status_code=400, detail="Artifact path must point to a .jsonl file")
    payload_bytes = artifact_path.read_bytes()
    rows = _parse_compiled_rows(payload_bytes)
    return await _persist_compiled_review_batch(
        artifact_filename=artifact_path.name,
        payload_bytes=payload_bytes,
        rows=rows,
        source_type=request.source_type,
        source_reference=request.source_reference,
        current_user=current_user,
        db=db,
    )


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


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compiled_review_batch(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _batch_or_404(batch_id, db)
    await db.delete(batch)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    batch = await _batch_or_404(batch_id, db)
    result = await db.execute(
        select(LexiconArtifactReviewItem)
        .where(
            LexiconArtifactReviewItem.batch_id == batch_id,
            LexiconArtifactReviewItem.review_status == "approved",
        )
        .order_by(LexiconArtifactReviewItem.display_text.asc())
    )
    approved_rows, _, _, _ = _materialized_rows(batch=batch, items=result.scalars().all())
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in approved_rows)
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
    _, rejected_rows, _, _ = _materialized_rows(batch=batch, items=result.scalars().all())
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rejected_rows)
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
    _, _, regenerate_rows, _ = _materialized_rows(batch=batch, items=result.scalars().all())
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in regenerate_rows)
    return Response(content=body, media_type="application/x-ndjson")


@router.get("/batches/{batch_id}/export/decisions")
async def export_compiled_review_decisions(
    batch_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _batch_or_404(batch_id, db)
    items = await _load_batch_items(batch.id, db)
    _, _, _, decision_rows = _materialized_rows(batch=batch, items=items)
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in decision_rows)
    return Response(content=body, media_type="application/x-ndjson")


@router.post("/batches/{batch_id}/materialize", response_model=LexiconCompiledReviewMaterializeResponse)
async def materialize_compiled_review_outputs(
    batch_id: uuid.UUID,
    request: LexiconCompiledReviewMaterializeRequest,
    _current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    batch = await _batch_or_404(batch_id, db)
    items = await _load_batch_items(batch.id, db)
    output_dir = (
        resolve_repo_local_path(request.output_dir, settings=settings, allow_missing=True)
        if request.output_dir
        else _batch_reviewed_output_dir(batch, settings)
    )
    approved_rows, rejected_rows, regenerate_rows, decision_rows = _materialized_rows(batch=batch, items=items)
    decisions_output_path = output_dir / DECISIONS_FILENAME
    approved_output_path = output_dir / APPROVED_FILENAME
    rejected_output_path = output_dir / REJECTED_FILENAME
    regenerate_output_path = output_dir / REGENERATE_FILENAME
    _write_jsonl(decisions_output_path, decision_rows)
    _write_jsonl(approved_output_path, approved_rows)
    _write_jsonl(rejected_output_path, rejected_rows)
    _write_jsonl(regenerate_output_path, regenerate_rows)
    return LexiconCompiledReviewMaterializeResponse(
        decision_count=len(decision_rows),
        approved_count=len(approved_rows),
        rejected_count=len(rejected_rows),
        regenerate_count=len(regenerate_rows),
        decisions_output_path=str(decisions_output_path),
        approved_output_path=str(approved_output_path),
        rejected_output_path=str(rejected_output_path),
        regenerate_output_path=str(regenerate_output_path),
    )
