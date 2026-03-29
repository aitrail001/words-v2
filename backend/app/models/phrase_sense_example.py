import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_voice_asset import LexiconVoiceAsset
    from app.models.phrase_sense import PhraseSense
    from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization


class PhraseSenseExample(Base):
    __tablename__ = "phrase_sense_examples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    phrase_sense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_senses"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    phrase_sense: Mapped["PhraseSense"] = relationship("PhraseSense", back_populates="examples")
    localizations: Mapped[list["PhraseSenseExampleLocalization"]] = relationship(
        "PhraseSenseExampleLocalization",
        back_populates="phrase_sense_example",
        cascade="all, delete-orphan",
        order_by="PhraseSenseExampleLocalization.locale",
    )
    voice_assets: Mapped[list["LexiconVoiceAsset"]] = relationship(
        "LexiconVoiceAsset",
        back_populates="phrase_sense_example",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LexiconVoiceAsset.created_at.asc()",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("phrase_sense_id", "sentence", name="uq_phrase_sense_example_sense_sentence"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("order_index", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<PhraseSenseExample {self.sentence[:50]}>"
