import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, literal, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.logging import get_logger
from app.models import review as review_models
from app.models.meaning import Meaning
from app.models.review import ReviewCard, ReviewSession
from app.models.word import Word
from app.spaced_repetition import calculate_next_review

logger = get_logger(__name__)


class ReviewService:
    def __init__(
        self,
        db: AsyncSession,
        queue_model: type[Any] | None = None,
        history_model: type[Any] | None = None,
    ):
        self.db = db
        self.queue_model = queue_model or self._resolve_queue_model()
        self.history_model = (
            history_model if history_model is not None else self._resolve_history_model()
        )
        self.uses_legacy_queue = self.queue_model is ReviewCard

    @staticmethod
    def _resolve_queue_model() -> type[Any]:
        for model_name in (
            "LearningQueueItem",
            "UserMeaning",
            "ReviewQueueItem",
            "UserMeaningQueue",
        ):
            model = getattr(review_models, model_name, None)
            if model is not None:
                return model

        for model in vars(review_models).values():
            if not isinstance(model, type):
                continue
            table = getattr(model, "__table__", None)
            if table is None:
                continue
            columns = {column.name for column in table.columns}
            if {"user_id", "meaning_id"}.issubset(columns):
                return model

        return ReviewCard

    @staticmethod
    def _resolve_history_model() -> type[Any] | None:
        for model_name in ("ReviewHistory", "QueueReviewHistory"):
            model = getattr(review_models, model_name, None)
            if model is not None:
                return model

        for model in vars(review_models).values():
            if not isinstance(model, type):
                continue
            table = getattr(model, "__table__", None)
            if table is None:
                continue
            columns = {column.name for column in table.columns}
            if "user_id" in columns and "time_spent_ms" in columns and (
                "quality" in columns or "quality_rating" in columns
            ):
                return model

        return None

    @staticmethod
    def _build_model_instance(model: type[Any], values: dict[str, Any]) -> Any | None:
        table = getattr(model, "__table__", None)
        if table is None:
            return model(**values)

        available_columns = {column.name: column for column in table.columns}
        payload = {
            key: value for key, value in values.items() if key in available_columns
        }

        for column in table.columns:
            if column.primary_key or column.name in payload:
                continue
            has_default = column.default is not None or column.server_default is not None
            if not column.nullable and not has_default:
                return None

        return model(**payload)

    def _history_supports_schedule(self) -> bool:
        if self.history_model is None or not hasattr(self.history_model, "__table__"):
            return False
        columns = {column.name for column in self.history_model.__table__.columns}
        return {"meaning_id", "created_at", "interval_days", "user_id"}.issubset(columns)

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

        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewSession.user_id == user_id)
            .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
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

    async def add_to_queue(self, user_id: uuid.UUID, meaning_id: uuid.UUID) -> Any:
        """Add a meaning to a user's queue in an idempotent way."""
        if self.uses_legacy_queue:
            return await self._add_to_legacy_queue(user_id, meaning_id)

        result = await self.db.execute(
            select(self.queue_model).where(
                self.queue_model.user_id == user_id,
                self.queue_model.meaning_id == meaning_id,
            )
        )
        existing_item = result.scalar_one_or_none()
        if existing_item is not None:
            return existing_item

        meaning_result = await self.db.execute(
            select(Meaning).where(Meaning.id == meaning_id)
        )
        meaning = meaning_result.scalar_one_or_none()
        if meaning is None:
            raise ValueError(f"Meaning {meaning_id} not found")

        new_item = self._build_model_instance(
            self.queue_model,
            {
                "user_id": user_id,
                "meaning_id": meaning_id,
                "word_id": meaning.word_id,
                "card_type": "flashcard",
                "priority": 0,
                "review_count": 0,
                "correct_count": 0,
                "next_review": None,
            },
        )
        if new_item is None:
            raise ValueError("Queue model is missing required fields for queue creation")

        # Keep API responses consistent across schemas that may not persist these fields.
        if getattr(new_item, "card_type", None) is None:
            setattr(new_item, "card_type", "flashcard")
        if getattr(new_item, "word_id", None) is None:
            setattr(new_item, "word_id", meaning.word_id)
        if not hasattr(new_item, "next_review"):
            setattr(new_item, "next_review", None)

        self.db.add(new_item)
        await self.db.commit()

        logger.info(
            "Queue item created",
            user_id=str(user_id),
            meaning_id=str(meaning_id),
            queue_item_id=str(getattr(new_item, "id", "")),
        )
        return new_item

    async def _add_to_legacy_queue(
        self, user_id: uuid.UUID, meaning_id: uuid.UUID
    ) -> ReviewCard:
        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewSession.user_id == user_id, ReviewCard.meaning_id == meaning_id)
        )
        existing_item = result.scalar_one_or_none()
        if existing_item is not None:
            return existing_item

        meaning_result = await self.db.execute(
            select(Meaning).where(Meaning.id == meaning_id)
        )
        meaning = meaning_result.scalar_one_or_none()
        if meaning is None:
            raise ValueError(f"Meaning {meaning_id} not found")

        session_result = await self.db.execute(
            select(ReviewSession)
            .where(ReviewSession.user_id == user_id, ReviewSession.completed_at.is_(None))
            .order_by(ReviewSession.started_at.desc())
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            session = ReviewSession(id=uuid.uuid4(), user_id=user_id)
            self.db.add(session)

        card = ReviewCard(
            session_id=session.id,
            word_id=meaning.word_id,
            meaning_id=meaning_id,
            card_type="flashcard",
            next_review=None,
        )
        self.db.add(card)
        await self.db.commit()

        logger.info(
            "Legacy queue item created",
            user_id=str(user_id),
            meaning_id=str(meaning_id),
            queue_item_id=str(card.id),
        )
        return card

    def _build_history_due_query(self, user_id: uuid.UUID, now: datetime):
        latest_history_subquery = (
            select(
                self.history_model.meaning_id.label("meaning_id"),
                func.max(self.history_model.created_at).label("latest_created_at"),
            )
            .where(self.history_model.user_id == user_id)
            .group_by(self.history_model.meaning_id)
            .subquery()
        )

        latest_history = aliased(self.history_model)
        next_review_expr = (
            latest_history.created_at
            + (latest_history.interval_days * literal_column("interval '1 day'"))
        ).label("next_review")

        due_condition = (
            (latest_history.id.is_(None))
            | (latest_history.interval_days.is_(None))
            | (next_review_expr <= now)
        )

        return latest_history_subquery, latest_history, next_review_expr, due_condition

    async def get_due_queue_items(
        self, user_id: uuid.UUID, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get due queue items scoped to a user including prompt metadata."""
        now = datetime.now(timezone.utc)

        if self.uses_legacy_queue:
            query = (
                select(ReviewCard, Word.word, Meaning.definition)
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .join(Meaning, ReviewCard.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(ReviewSession.user_id == user_id)
                .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
                .order_by(ReviewCard.next_review.asc().nullsfirst())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        elif hasattr(self.queue_model, "next_review"):
            query = (
                select(self.queue_model, Word.word, Meaning.definition)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(self.queue_model.user_id == user_id)
                .where(
                    (self.queue_model.next_review.is_(None))
                    | (self.queue_model.next_review <= now)
                )
                .order_by(self.queue_model.next_review.asc().nullsfirst())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        elif self._history_supports_schedule():
            (
                latest_history_subquery,
                latest_history,
                next_review_expr,
                due_condition,
            ) = self._build_history_due_query(user_id=user_id, now=now)

            query = (
                select(self.queue_model, Word.word, Meaning.definition, next_review_expr)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .outerjoin(
                    latest_history_subquery,
                    latest_history_subquery.c.meaning_id == self.queue_model.meaning_id,
                )
                .outerjoin(
                    latest_history,
                    and_(
                        latest_history.meaning_id == latest_history_subquery.c.meaning_id,
                        latest_history.created_at
                        == latest_history_subquery.c.latest_created_at,
                        latest_history.user_id == user_id,
                    ),
                )
                .where(self.queue_model.user_id == user_id)
                .where(due_condition)
                .order_by(next_review_expr.asc().nullsfirst(), self.queue_model.created_at.asc())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        else:
            query = (
                select(self.queue_model, Word.word, Meaning.definition)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(self.queue_model.user_id == user_id)
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()

        due_items: list[dict[str, Any]] = []
        for row in rows:
            if len(row) == 4:
                item, word, definition, next_review = row
            else:
                item, word, definition = row
                next_review = getattr(item, "next_review", None)

            if next_review is not None:
                setattr(item, "next_review", next_review)

            due_items.append(
                {
                    "id": item.id,
                    "item": item,
                    "word": word,
                    "definition": definition,
                    "next_review": next_review,
                }
            )

        return due_items

    async def _get_latest_history_for_meaning(
        self, user_id: uuid.UUID, meaning_id: uuid.UUID
    ) -> Any | None:
        if self.history_model is None:
            return None
        if not hasattr(self.history_model, "meaning_id"):
            return None
        if not hasattr(self.history_model, "user_id"):
            return None
        if not hasattr(self.history_model, "created_at"):
            return None

        result = await self.db.execute(
            select(self.history_model)
            .where(
                self.history_model.user_id == user_id,
                self.history_model.meaning_id == meaning_id,
            )
            .order_by(self.history_model.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def submit_queue_review(
        self,
        item_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
        card_type: str | None = None,
    ) -> Any:
        """Submit a queue review and update scheduling via SM-2."""
        if self.uses_legacy_queue:
            result = await self.db.execute(
                select(ReviewCard)
                .join(ReviewSession)
                .where(ReviewCard.id == item_id, ReviewSession.user_id == user_id)
            )
        else:
            result = await self.db.execute(
                select(self.queue_model).where(
                    self.queue_model.id == item_id,
                    self.queue_model.user_id == user_id,
                )
            )

        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Queue item {item_id} not found")

        latest_history = None
        if (
            not self.uses_legacy_queue
            and not hasattr(self.queue_model, "next_review")
            and self._history_supports_schedule()
        ):
            latest_history = await self._get_latest_history_for_meaning(
                user_id=user_id,
                meaning_id=item.meaning_id,
            )

        previous_ease_factor = float(
            getattr(latest_history, "ease_factor", None)
            or getattr(item, "ease_factor", None)
            or 2.5
        )
        previous_interval_days = int(
            getattr(latest_history, "interval_days", None)
            or getattr(item, "interval_days", None)
            or 0
        )
        previous_repetitions = int(
            getattr(latest_history, "repetitions", None)
            or getattr(item, "repetitions", None)
            or 0
        )

        sm2_result = calculate_next_review(
            quality=quality,
            ease_factor=previous_ease_factor,
            interval_days=previous_interval_days,
            repetitions=previous_repetitions,
        )

        effective_card_type = card_type or getattr(item, "card_type", None) or "flashcard"

        # Set runtime attributes so API responses include scheduling fields
        # even for queue models that don't persist these columns directly.
        item.quality_rating = quality
        item.time_spent_ms = time_spent_ms
        item.ease_factor = sm2_result.ease_factor
        item.interval_days = sm2_result.interval_days
        item.repetitions = sm2_result.repetitions
        item.next_review = sm2_result.next_review
        item.card_type = effective_card_type

        if hasattr(type(item), "last_reviewed_at") or hasattr(item, "last_reviewed_at"):
            item.last_reviewed_at = datetime.now(timezone.utc)
        if hasattr(type(item), "review_count") or hasattr(item, "review_count"):
            item.review_count = int(getattr(item, "review_count", 0) or 0) + 1
        if quality >= 3 and (
            hasattr(type(item), "correct_count") or hasattr(item, "correct_count")
        ):
            item.correct_count = int(getattr(item, "correct_count", 0) or 0) + 1

        history_record = self._build_history_record(
            item=item,
            user_id=user_id,
            quality=quality,
            time_spent_ms=time_spent_ms,
            card_type=effective_card_type,
            previous_ease_factor=previous_ease_factor,
            previous_interval_days=previous_interval_days,
            previous_repetitions=previous_repetitions,
        )
        if history_record is not None:
            self.db.add(history_record)

        await self.db.commit()
        return item

    def _build_history_record(
        self,
        item: Any,
        user_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        card_type: str,
        previous_ease_factor: float,
        previous_interval_days: int,
        previous_repetitions: int,
    ) -> Any | None:
        if self.history_model is None:
            return None

        payload = {
            "user_id": user_id,
            "queue_item_id": getattr(item, "id", None),
            "item_id": getattr(item, "id", None),
            "review_card_id": getattr(item, "id", None),
            "meaning_id": getattr(item, "meaning_id", None),
            "quality": quality,
            "quality_rating": quality,
            "time_spent_ms": time_spent_ms,
            "card_type": card_type,
            "reviewed_at": datetime.now(timezone.utc),
            "is_correct": quality >= 3,
            "ease_factor_before": previous_ease_factor,
            "ease_factor_after": getattr(item, "ease_factor", None),
            "ease_factor": getattr(item, "ease_factor", None),
            "interval_days_before": previous_interval_days,
            "interval_days_after": getattr(item, "interval_days", None),
            "interval_days": getattr(item, "interval_days", None),
            "repetitions_before": previous_repetitions,
            "repetitions_after": getattr(item, "repetitions", None),
            "repetitions": getattr(item, "repetitions", None),
            "next_review": getattr(item, "next_review", None),
        }
        return self._build_model_instance(self.history_model, payload)

    async def get_queue_stats(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get queue totals, due counts, and aggregate performance stats."""
        now = datetime.now(timezone.utc)

        if self.uses_legacy_queue:
            total_result = await self.db.execute(
                select(func.count(ReviewCard.id))
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
            )
            total_items = int(total_result.scalar_one() or 0)

            due_result = await self.db.execute(
                select(func.count(ReviewCard.id))
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
                .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
            )
            due_items = int(due_result.scalar_one() or 0)

            aggregate_result = await self.db.execute(
                select(
                    func.count(ReviewCard.id).filter(ReviewCard.quality_rating.is_not(None)),
                    func.count(ReviewCard.id).filter(ReviewCard.quality_rating >= 3),
                )
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
            )
            review_count, correct_count = aggregate_result.one()
        else:
            total_result = await self.db.execute(
                select(func.count(self.queue_model.id)).where(
                    self.queue_model.user_id == user_id
                )
            )
            total_items = int(total_result.scalar_one() or 0)

            if hasattr(self.queue_model, "next_review"):
                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id))
                    .where(self.queue_model.user_id == user_id)
                    .where(
                        (self.queue_model.next_review.is_(None))
                        | (self.queue_model.next_review <= now)
                    )
                )
            elif self._history_supports_schedule():
                (
                    latest_history_subquery,
                    latest_history,
                    next_review_expr,
                    due_condition,
                ) = self._build_history_due_query(user_id=user_id, now=now)

                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id))
                    .outerjoin(
                        latest_history_subquery,
                        latest_history_subquery.c.meaning_id == self.queue_model.meaning_id,
                    )
                    .outerjoin(
                        latest_history,
                        and_(
                            latest_history.meaning_id == latest_history_subquery.c.meaning_id,
                            latest_history.created_at
                            == latest_history_subquery.c.latest_created_at,
                            latest_history.user_id == user_id,
                        ),
                    )
                    .where(self.queue_model.user_id == user_id)
                    .where(due_condition)
                )
            else:
                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id)).where(
                        self.queue_model.user_id == user_id
                    )
                )

            due_items = int(due_result.scalar_one() or 0)

            if self.history_model is not None and hasattr(self.history_model, "user_id"):
                if hasattr(self.history_model, "quality_rating"):
                    aggregate_result = await self.db.execute(
                        select(
                            func.count(self.history_model.id),
                            func.count(self.history_model.id).filter(
                                self.history_model.quality_rating >= 3
                            ),
                        ).where(self.history_model.user_id == user_id)
                    )
                elif hasattr(self.history_model, "quality"):
                    aggregate_result = await self.db.execute(
                        select(
                            func.count(self.history_model.id),
                            func.count(self.history_model.id).filter(
                                self.history_model.quality >= 3
                            ),
                        ).where(self.history_model.user_id == user_id)
                    )
                else:
                    aggregate_result = await self.db.execute(select(literal(0), literal(0)))
            elif hasattr(self.queue_model, "review_count") and hasattr(
                self.queue_model, "correct_count"
            ):
                aggregate_result = await self.db.execute(
                    select(
                        func.coalesce(func.sum(self.queue_model.review_count), 0),
                        func.coalesce(func.sum(self.queue_model.correct_count), 0),
                    ).where(self.queue_model.user_id == user_id)
                )
            elif hasattr(self.queue_model, "review_count"):
                aggregate_result = await self.db.execute(
                    select(func.coalesce(func.sum(self.queue_model.review_count), 0), literal(0))
                    .where(self.queue_model.user_id == user_id)
                )
            else:
                aggregate_result = await self.db.execute(select(literal(0), literal(0)))

            review_count, correct_count = aggregate_result.one()

        review_count = int(review_count or 0)
        correct_count = int(correct_count or 0)
        accuracy = (correct_count / review_count) if review_count > 0 else 0.0

        return {
            "total_items": total_items,
            "due_items": due_items,
            "review_count": review_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
        }

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
