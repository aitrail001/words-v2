import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.meaning import Meaning


class Translation(Base):
    __tablename__ = "translations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("meanings"), ondelete="CASCADE"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    usage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    examples: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    meaning: Mapped["Meaning"] = relationship("Meaning", back_populates="translations")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("meaning_id", "language", name="uq_translation_meaning_language"),
    )

    def __repr__(self) -> str:
        return f"<Translation {self.language}: {self.translation[:30]}>"
