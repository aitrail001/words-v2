import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.models.review import ReviewSession, ReviewCard
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
    quality: int  # 0-5
    time_spent_ms: int


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

    return [
        CardResponse(
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
        for card in cards
    ]


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
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

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


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Mark a review session as completed."""
    service = ReviewService(db)

    try:
        session = await service.complete_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return SessionResponse(
        id=str(session.id),
        user_id=str(session.user_id),
        started_at=session.started_at,
        completed_at=session.completed_at,
        cards_reviewed=session.cards_reviewed,
    )
