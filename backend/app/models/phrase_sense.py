import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.phrase_entry import PhraseEntry
    from app.models.phrase_sense_example import PhraseSenseExample
    from app.models.phrase_sense_localization import PhraseSenseLocalization


class PhraseSense(Base):
    __tablename__ = "phrase_senses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    phrase_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_entries"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    usage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    part_of_speech: Mapped[str | None] = mapped_column(String(50), nullable=True)
    register: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secondary_domains: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    grammar_patterns: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    synonyms: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    antonyms: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    collocations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    phrase_entry: Mapped["PhraseEntry"] = relationship("PhraseEntry", back_populates="phrase_senses")
    examples: Mapped[list["PhraseSenseExample"]] = relationship(
        "PhraseSenseExample",
        back_populates="phrase_sense",
        cascade="all, delete-orphan",
        order_by="PhraseSenseExample.order_index",
    )
    localizations: Mapped[list["PhraseSenseLocalization"]] = relationship(
        "PhraseSenseLocalization",
        back_populates="phrase_sense",
        cascade="all, delete-orphan",
        order_by="PhraseSenseLocalization.locale",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("phrase_entry_id", "order_index", name="uq_phrase_sense_entry_order"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("order_index", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<PhraseSense {self.definition[:30]}>"
