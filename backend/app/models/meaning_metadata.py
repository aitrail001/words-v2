import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.meaning import Meaning


class MeaningMetadata(Base):
    __tablename__ = "meaning_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("meanings"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metadata_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)

    meaning: Mapped["Meaning"] = relationship("Meaning", back_populates="metadata_entries")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("meaning_id", "metadata_kind", "order_index", name="uq_meaning_metadata_kind_order"),
    )

    def __repr__(self) -> str:
        return f"<MeaningMetadata {self.metadata_kind}#{self.order_index}>"
