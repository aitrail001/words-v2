import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.word import Word


class WordConfusable(Base):
    __tablename__ = "word_confusables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("words"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    confusable_word: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    word: Mapped["Word"] = relationship("Word", back_populates="confusable_entries")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("word_id", "order_index", name="uq_word_confusables_word_order"),
    )

    def __repr__(self) -> str:
        return f"<WordConfusable {self.confusable_word} word={self.word_id}>"
