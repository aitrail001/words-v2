import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_voice_asset import LexiconVoiceAsset
    from app.models.phrase_sense import PhraseSense


class PhraseEntry(Base):
    __tablename__ = "phrase_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    phrase_text: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_form: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phrase_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    cefr_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    register_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    brief_usage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    seed_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    phrase_senses: Mapped[list["PhraseSense"]] = relationship(
        "PhraseSense",
        back_populates="phrase_entry",
        cascade="all, delete-orphan",
        order_by="PhraseSense.order_index",
    )
    voice_assets: Mapped[list["LexiconVoiceAsset"]] = relationship(
        "LexiconVoiceAsset",
        back_populates="phrase_entry",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LexiconVoiceAsset.created_at.asc()",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("normalized_form", "language", name="uq_phrase_entry_normalized_language"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<PhraseEntry {self.phrase_text} ({self.language})>"
