import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Meaning(Base):
    __tablename__ = "meanings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("words.id", ondelete="CASCADE"), nullable=False
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    part_of_speech: Mapped[str | None] = mapped_column(String(50), nullable=True)
    example_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    word: Mapped["Word"] = relationship("Word", back_populates="meanings")
    translations: Mapped[list["Translation"]] = relationship(
        "Translation", back_populates="meaning", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("order_index", 0)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Meaning {self.definition[:50]}>"
