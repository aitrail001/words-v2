import uuid
from datetime import datetime
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.request_db_metrics import finalize_request_db_metrics
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.services.review import ReviewService

logger = get_logger(__name__)
router = APIRouter()


# Schemas
class SessionResponse(BaseModel):
    id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None
    cards_reviewed: int


class CardResponse(BaseModel):
    id: str
    session_id: str
    word_id: str
    meaning_id: str
    card_type: str
    quality_rating: int | None
    time_spent_ms: int | None
    ease_factor: float | None
    interval_days: int | None
    next_review: datetime | None


class SubmitReviewRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5)
    time_spent_ms: int = Field(..., ge=0)


class QueueAddRequest(BaseModel):
    meaning_id: uuid.UUID


class QueueSubmitRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5)
    time_spent_ms: int = Field(..., ge=0)
    card_type: str | None = Field(default=None, min_length=1, max_length=32)


class QueueItemResponse(BaseModel):
    id: str
    session_id: str | None = None
    word_id: str | None = None
    meaning_id: str
    card_type: str | None = None
    quality_rating: int | None = None
    time_spent_ms: int | None = None
    ease_factor: float | None = None
    interval_days: int | None = None
    repetitions: int | None = None
    next_review: datetime | None = None
    review_count: int | None = None
    correct_count: int | None = None
    word: str | None = None
    definition: str | None = None


class QueueStatsResponse(BaseModel):
    total_items: int
    due_items: int
    review_count: int
    correct_count: int
    accuracy: float


def _to_card_response(card: Any) -> CardResponse:
    return CardResponse(
        id=str(card.id),
        session_id=str(card.session_id),
        word_id=str(card.word_id),
        meaning_id=str(card.meaning_id),
        card_type=card.card_type,
        quality_rating=card.quality_rating,
        time_spent_ms=card.time_spent_ms,
        ease_factor=card.ease_factor,
        interval_days=card.interval_days,
        next_review=card.next_review,
    )


def _to_queue_item_response(
    item: Any,
    word: str | None = None,
    definition: str | None = None,
) -> QueueItemResponse:
    return QueueItemResponse(
        id=str(item.id),
        session_id=str(getattr(item, "session_id", ""))
        if getattr(item, "session_id", None)
        else None,
        word_id=str(getattr(item, "word_id", "")) if getattr(item, "word_id", None) else None,
        meaning_id=str(item.meaning_id),
        card_type=getattr(item, "card_type", None),
        quality_rating=getattr(item, "quality_rating", None),
        time_spent_ms=getattr(item, "time_spent_ms", None),
        ease_factor=getattr(item, "ease_factor", None),
        interval_days=getattr(item, "interval_days", None),
        repetitions=getattr(item, "repetitions", None),
        next_review=getattr(item, "next_review", None),
        review_count=getattr(item, "review_count", None),
        correct_count=getattr(item, "correct_count", None),
        word=word,
        definition=definition,
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Create a new review session."""
    service = ReviewService(db)
    session = await service.create_session(current_user.id)

    logger.info("Review session created", session_id=str(session.id), user_id=str(current_user.id))

    return SessionResponse(
        id=str(session.id),
        user_id=str(session.user_id),
        started_at=session.started_at,
        completed_at=session.completed_at,
        cards_reviewed=session.cards_reviewed,
    )


@router.get("/due", response_model=list[CardResponse])
async def get_due_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CardResponse]:
    """Get cards due for review."""
    service = ReviewService(db)
    cards = await service.get_due_cards(current_user.id)
    return [_to_card_response(card) for card in cards]


@router.post("/cards/{card_id}/submit", response_model=CardResponse)
async def submit_review(
    card_id: uuid.UUID,
    request: SubmitReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    """Submit a review for a card."""
    service = ReviewService(db)

    try:
        card = await service.submit_review(
            card_id=card_id,
            quality=request.quality,
            time_spent_ms=request.time_spent_ms,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return _to_card_response(card)


@router.post("/queue", response_model=QueueItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_queue(
    request: QueueAddRequest,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Add a meaning to the user's review queue."""
    request_start = perf_counter()
    service = ReviewService(db)

    try:
        queue_item = await service.add_to_queue(current_user.id, request.meaning_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_add", **metrics)
    return _to_queue_item_response(queue_item)


@router.get("/queue/due", response_model=list[QueueItemResponse])
async def get_due_queue_items(
    limit: int = Query(default=20, ge=1, le=100),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QueueItemResponse]:
    """Get due items from the review queue with prompt metadata."""
    request_start = perf_counter()
    service = ReviewService(db)
    due_items = await service.get_due_queue_items(current_user.id, limit=limit)

    items = [
        _to_queue_item_response(
            due_entry["item"],
            word=due_entry["word"],
            definition=due_entry["definition"],
        )
        for due_entry in due_items
    ]
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_due", result_count=len(items), **metrics)
    return items


@router.post("/queue/{item_id}/submit", response_model=QueueItemResponse)
async def submit_queue_review(
    item_id: uuid.UUID,
    request: QueueSubmitRequest,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Submit a review result for a queue item."""
    request_start = perf_counter()
    service = ReviewService(db)

    try:
        item = await service.submit_queue_review(
            item_id=item_id,
            quality=request.quality,
            time_spent_ms=request.time_spent_ms,
            card_type=request.card_type,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_submit", **metrics)
    return _to_queue_item_response(item)


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueStatsResponse:
    """Get queue-level review stats for the current user."""
    request_start = perf_counter()
    service = ReviewService(db)
    stats = await service.get_queue_stats(current_user.id)
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_stats", **metrics)
    return QueueStatsResponse(**stats)


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Mark a review session as completed."""
    service = ReviewService(db)

    try:
        session = await service.complete_session(session_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return SessionResponse(
        id=str(session.id),
        user_id=str(session.user_id),
        started_at=session.started_at,
        completed_at=session.completed_at,
        cards_reviewed=session.cards_reviewed,
    )
