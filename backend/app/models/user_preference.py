import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
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
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("accent_preference", "us")
        kwargs.setdefault("translation_locale", "zh-Hans")
        kwargs.setdefault("knowledge_view_preference", "cards")
        kwargs.setdefault("show_translations_by_default", True)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)
