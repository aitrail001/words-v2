import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.review import ReviewCard, ReviewSession
from app.spaced_repetition import calculate_next_review

logger = get_logger(__name__)


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, user_id: uuid.UUID) -> ReviewSession:
        """Create a new review session for a user."""
        session = ReviewSession(user_id=user_id)
        self.db.add(session)
        await self.db.commit()

        logger.info("Review session created", session_id=str(session.id), user_id=str(user_id))
        return session

    async def get_due_cards(self, user_id: uuid.UUID, limit: int = 20) -> list[ReviewCard]:
        """Get cards due for review for a user."""
        now = datetime.now(timezone.utc)

        # Query for cards where next_review is in the past or null
        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewSession.user_id == user_id)
            .where(
                (ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now)
            )
            .order_by(ReviewCard.next_review.asc().nullsfirst())
            .limit(limit)
        )
        cards = result.scalars().all()

        logger.info("Retrieved due cards", user_id=str(user_id), count=len(cards))
        return list(cards)

    async def add_card_to_session(
        self,
        session_id: uuid.UUID,
        word_id: uuid.UUID,
        meaning_id: uuid.UUID,
        card_type: str,
    ) -> ReviewCard:
        """Add a card to a review session."""
        card = ReviewCard(
            session_id=session_id,
            word_id=word_id,
            meaning_id=meaning_id,
            card_type=card_type,
        )
        self.db.add(card)
        await self.db.commit()

        logger.info(
            "Card added to session",
            session_id=str(session_id),
            card_id=str(card.id),
            card_type=card_type,
        )
        return card

    async def submit_review(
        self,
        card_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
    ) -> ReviewCard:
        """Submit a review for a card and update SM-2 parameters."""
        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewCard.id == card_id, ReviewSession.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if card is None:
            raise ValueError(f"Review card {card_id} not found")

        # Apply SM-2 algorithm
        sm2_result = calculate_next_review(
            quality=quality,
            ease_factor=card.ease_factor or 2.5,
            interval_days=card.interval_days or 0,
            repetitions=card.repetitions or 0,
        )

        card.quality_rating = quality
        card.time_spent_ms = time_spent_ms
        card.ease_factor = sm2_result.ease_factor
        card.interval_days = sm2_result.interval_days
        card.repetitions = sm2_result.repetitions
        card.next_review = sm2_result.next_review

        await self.db.commit()

        logger.info(
            "Review submitted",
            card_id=str(card_id),
            quality=quality,
            new_interval=sm2_result.interval_days,
            new_ease_factor=sm2_result.ease_factor,
        )

        return card

    async def complete_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReviewSession:
        """Mark a review session as completed."""
        result = await self.db.execute(
            select(ReviewSession).where(
                ReviewSession.id == session_id, ReviewSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise ValueError(f"Review session {session_id} not found")

        session.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info("Review session completed", session_id=str(session_id))
        return session
