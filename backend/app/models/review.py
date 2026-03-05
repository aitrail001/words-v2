import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReviewSession(Base):
    __tablename__ = "review_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cards_reviewed: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)

    cards: Mapped[list["ReviewCard"]] = relationship(
        "ReviewCard", back_populates="session", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("started_at", datetime.now(timezone.utc))
        kwargs.setdefault("cards_reviewed", 0)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ReviewSession {self.id} user={self.user_id}>"


class ReviewCard(Base):
    __tablename__ = "review_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("words.id", ondelete="CASCADE"), nullable=False
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False
    )
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)  # flashcard, cloze, listening
    quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-5 (SM-2)
    time_spent_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ease_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repetitions: Mapped[int | None] = mapped_column(Integer, nullable=True)  # SM-2 repetition count
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    session: Mapped["ReviewSession"] = relationship("ReviewSession", back_populates="cards")

    def __init__(self, **kwargs):
        # If quality_rating and interval_days are provided, calculate next_review
        if "quality_rating" in kwargs and "interval_days" in kwargs and "next_review" not in kwargs:
            interval = kwargs["interval_days"]
            kwargs["next_review"] = datetime.now(timezone.utc) + timedelta(days=interval)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ReviewCard {self.card_type} word={self.word_id}>"


class LearningQueueItem(Base):
    __tablename__ = "learning_queue_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "meaning_id", name="uq_learning_queue_user_meaning"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("priority", 0)
        kwargs.setdefault("review_count", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LearningQueueItem user={self.user_id} meaning={self.meaning_id}>"


class ReviewHistory(Base):
    __tablename__ = "review_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    time_spent_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ease_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repetitions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<ReviewHistory user={self.user_id} meaning={self.meaning_id} "
            f"rating={self.quality_rating}>"
        )
