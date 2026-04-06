import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    accent_preference: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="us")
    translation_locale: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="zh-Hans")
    knowledge_view_preference: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="cards")
    show_translations_by_default: Mapped[bool] = mapped_column(
        nullable=False,
        insert_default=True,
        server_default=text("true"),
    )
    review_depth_preset: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="balanced")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, insert_default="UTC", server_default=text("'UTC'")
    )
    enable_confidence_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, insert_default=True, server_default=text("true")
    )
    enable_word_spelling: Mapped[bool] = mapped_column(
        Boolean, nullable=False, insert_default=True, server_default=text("true")
    )
    enable_audio_spelling: Mapped[bool] = mapped_column(
        Boolean, nullable=False, insert_default=False, server_default=text("false")
    )
    show_pictures_in_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, insert_default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_preferences_user"),
        CheckConstraint("accent_preference IN ('us', 'uk', 'au')", name="ck_user_preferences_accent"),
        CheckConstraint("knowledge_view_preference IN ('cards', 'tags', 'list')", name="ck_user_preferences_view"),
        CheckConstraint(
            "review_depth_preset IN ('gentle', 'balanced', 'deep')",
            name="ck_user_preferences_review_depth",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("accent_preference", "us")
        kwargs.setdefault("translation_locale", "zh-Hans")
        kwargs.setdefault("knowledge_view_preference", "cards")
        kwargs.setdefault("show_translations_by_default", True)
        kwargs.setdefault("review_depth_preset", "balanced")
        kwargs.setdefault("timezone", "UTC")
        kwargs.setdefault("enable_confidence_check", True)
        kwargs.setdefault("enable_word_spelling", True)
        kwargs.setdefault("enable_audio_spelling", False)
        kwargs.setdefault("show_pictures_in_questions", False)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
