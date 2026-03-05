import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.meaning import Meaning


class Word(Base):
    __tablename__ = "words"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    frequency_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    word_forms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    meanings: Mapped[list["Meaning"]] = relationship(
        "Meaning", back_populates="word", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("word", "language", name="uq_word_language"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Word {self.word} ({self.language})>"
