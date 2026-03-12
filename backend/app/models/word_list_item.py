import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk

if TYPE_CHECKING:
    from app.models.word import Word
    from app.models.word_list import WordList


class WordListItem(Base):
    __tablename__ = "word_list_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word_list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("words"), ondelete="CASCADE"), nullable=False, index=True
    )
    context_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    frequency_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=1)
    variation_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    word_list: Mapped["WordList"] = relationship("WordList", back_populates="items")
    word: Mapped["Word"] = relationship("Word", back_populates="word_list_items")

    __table_args__ = (
        UniqueConstraint("word_list_id", "word_id", name="uq_word_list_item_word"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("frequency_count", 1)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<WordListItem list={self.word_list_id} word={self.word_id}>"
