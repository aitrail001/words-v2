import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.translation import Translation


class TranslationExample(Base):
    __tablename__ = "translation_examples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    translation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("translations"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)

    translation: Mapped["Translation"] = relationship("Translation", back_populates="example_entries")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("translation_id", "order_index", name="uq_translation_examples_translation_order"),
    )

    def __repr__(self) -> str:
        return f"<TranslationExample {self.translation_id}#{self.order_index}>"
