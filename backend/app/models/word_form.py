import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.word import Word


class WordForm(Base):
    __tablename__ = "word_forms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("words"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    form_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    form_slot: Mapped[str] = mapped_column(String(50), nullable=False, insert_default="")
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    word: Mapped["Word"] = relationship("Word", back_populates="form_entries")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("word_id", "form_kind", "form_slot", "order_index", name="uq_word_forms_word_kind_slot_order"),
    )

    def __repr__(self) -> str:
        return f"<WordForm {self.form_kind}:{self.form_slot}={self.value} word={self.word_id}>"
