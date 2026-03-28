from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_artifact_review_item_event import LexiconArtifactReviewItemEvent
from app.models.lexicon_regeneration_request import LexiconRegenerationRequest

CompiledReviewStatus = Literal["pending", "approved", "rejected"]

DEFAULT_COMPILED_REVIEW_PAGE_SIZE = 50
MAX_COMPILED_REVIEW_PAGE_SIZE = 200
BULK_REVIEW_CHUNK_SIZE = 500


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_review_status(review_status: str) -> CompiledReviewStatus:
    if review_status not in {"pending", "approved", "rejected"}:
        raise ValueError("Invalid compiled review status")
    return review_status


def apply_review_decision(
    item: LexiconArtifactReviewItem,
    *,
    review_status: CompiledReviewStatus,
    decision_reason: str | None,
    actor_user_id: uuid.UUID | None,
    reviewed_at: datetime | None = None,
) -> str:
    reviewed_at = reviewed_at or utc_now()
    previous_status = item.review_status
    item.review_status = review_status
    item.decision_reason = decision_reason
    item.reviewed_by = actor_user_id
    item.reviewed_at = reviewed_at
    item.updated_at = reviewed_at
    item.import_eligible = review_status == "approved"
    item.regen_requested = review_status == "rejected"
    return previous_status


def recalculate_batch_counts(
    batch: LexiconArtifactReviewBatch,
    *,
    total_items: int,
    approved_count: int,
    rejected_count: int,
    updated_at: datetime | None = None,
) -> None:
    pending_count = total_items - approved_count - rejected_count
    batch.total_items = total_items
    batch.pending_count = pending_count
    batch.approved_count = approved_count
    batch.rejected_count = rejected_count
    batch.status = "completed" if pending_count == 0 else "pending_review"
    batch.completed_at = (updated_at or utc_now()) if pending_count == 0 else None
    batch.updated_at = updated_at or utc_now()


def build_compiled_review_items_query(
    *,
    batch_id: uuid.UUID,
    review_status: str | None = None,
    search: str | None = None,
) -> Select[tuple[LexiconArtifactReviewItem]]:
    query = select(LexiconArtifactReviewItem).where(LexiconArtifactReviewItem.batch_id == batch_id)
    if review_status:
        query = query.where(LexiconArtifactReviewItem.review_status == review_status)
    if search:
        query = query.where(LexiconArtifactReviewItem.search_text.ilike(f"%{search.strip().lower()}%"))
    return query.order_by(
        LexiconArtifactReviewItem.review_priority.asc(),
        LexiconArtifactReviewItem.display_text.asc(),
        LexiconArtifactReviewItem.id.asc(),
    )


async def count_compiled_review_items(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    review_status: str | None = None,
    search: str | None = None,
) -> int:
    count_query = select(func.count()).select_from(
        build_compiled_review_items_query(batch_id=batch_id, review_status=review_status, search=search).subquery()
    )
    result = await db.execute(count_query)
    return int(result.scalar_one() or 0)


async def recalculate_batch_counts_from_db(db: AsyncSession, batch: LexiconArtifactReviewBatch) -> None:
    total_items = await count_compiled_review_items(db, batch_id=batch.id)
    approved_count = await count_compiled_review_items(db, batch_id=batch.id, review_status="approved")
    rejected_count = await count_compiled_review_items(db, batch_id=batch.id, review_status="rejected")
    recalculate_batch_counts(
        batch,
        total_items=total_items,
        approved_count=approved_count,
        rejected_count=rejected_count,
    )


def recalculate_batch_counts_from_rows(
    batch: LexiconArtifactReviewBatch,
    items: list[LexiconArtifactReviewItem],
    *,
    updated_at: datetime | None = None,
) -> None:
    recalculate_batch_counts(
        batch,
        total_items=len(items),
        approved_count=sum(1 for item in items if item.review_status == "approved"),
        rejected_count=sum(1 for item in items if item.review_status == "rejected"),
        updated_at=updated_at,
    )


async def upsert_regeneration_request_async(
    *,
    db: AsyncSession,
    batch: LexiconArtifactReviewBatch,
    item: LexiconArtifactReviewItem,
    actor_user_id: uuid.UUID | None,
) -> None:
    existing_result = await db.execute(
        select(LexiconRegenerationRequest).where(LexiconRegenerationRequest.item_id == item.id)
    )
    existing_request = existing_result.scalar_one_or_none()
    if item.review_status != "rejected":
        if existing_request is not None:
            await db.delete(existing_request)
        return

    request_payload = _regeneration_request_payload(batch=batch, item=item)
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
                created_by=actor_user_id,
            )
        )
        return

    existing_request.request_status = "pending"
    existing_request.request_reason = item.decision_reason
    existing_request.request_payload = request_payload


def upsert_regeneration_request_sync(
    *,
    db: Session,
    batch: LexiconArtifactReviewBatch,
    item: LexiconArtifactReviewItem,
    actor_user_id: uuid.UUID | None,
) -> None:
    existing_request = db.execute(
        select(LexiconRegenerationRequest).where(LexiconRegenerationRequest.item_id == item.id)
    ).scalar_one_or_none()
    if item.review_status != "rejected":
        if existing_request is not None:
            db.delete(existing_request)
        return
    request_payload = _regeneration_request_payload(batch=batch, item=item)

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
                created_by=actor_user_id,
            )
        )
        return

    existing_request.request_status = "pending"
    existing_request.request_reason = item.decision_reason
    existing_request.request_payload = request_payload


def _regeneration_request_payload(
    *,
    batch: LexiconArtifactReviewBatch,
    item: LexiconArtifactReviewItem,
) -> dict[str, str | None]:
    return {
        "schema_version": "lexicon_review_decision.v1",
        "artifact_sha256": batch.artifact_sha256,
        "entry_id": item.entry_id,
        "entry_type": item.entry_type,
        "normalized_form": item.normalized_form,
        "compiled_payload_sha256": item.compiled_payload_sha256,
        "decision_reason": item.decision_reason,
    }


def add_review_item_event(
    *,
    item: LexiconArtifactReviewItem,
    previous_status: str,
    review_status: CompiledReviewStatus,
    actor_user_id: uuid.UUID | None,
    reason: str | None,
) -> LexiconArtifactReviewItemEvent:
    return LexiconArtifactReviewItemEvent(
        item_id=item.id,
        event_type=review_status,
        from_status=previous_status,
        to_status=review_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )
