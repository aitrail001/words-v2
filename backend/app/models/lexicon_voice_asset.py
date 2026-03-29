import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.phrase_entry import PhraseEntry
    from app.models.phrase_sense import PhraseSense
    from app.models.phrase_sense_example import PhraseSenseExample
    from app.models.word import Word


class LexiconVoiceAsset(Base):
    __tablename__ = "lexicon_voice_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4)
    word_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("words"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    meaning_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("meanings"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    meaning_example_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("meaning_examples"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    phrase_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_entries"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    phrase_sense_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_senses"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    phrase_sense_example_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_sense_examples"), ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    storage_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("lexicon_voice_storage_policies"), ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    voice_role: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(32), nullable=False)
    audio_format: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speaking_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch_semitones: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_ms: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    tail_ms: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    effects_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, insert_default="generated")
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    word: Mapped["Word | None"] = relationship("Word", back_populates="voice_assets")
    meaning: Mapped["Meaning | None"] = relationship("Meaning", back_populates="voice_assets")
    meaning_example: Mapped["MeaningExample | None"] = relationship("MeaningExample", back_populates="voice_assets")
    phrase_entry: Mapped["PhraseEntry | None"] = relationship("PhraseEntry", back_populates="voice_assets")
    phrase_sense: Mapped["PhraseSense | None"] = relationship("PhraseSense", back_populates="voice_assets")
    phrase_sense_example: Mapped["PhraseSenseExample | None"] = relationship("PhraseSenseExample", back_populates="voice_assets")
    storage_policy: Mapped["LexiconVoiceStoragePolicy"] = relationship("LexiconVoiceStoragePolicy", back_populates="voice_assets")

    @property
    def storage_kind(self) -> str:
        return self.storage_policy.primary_storage_kind

    @property
    def storage_base(self) -> str:
        return self.storage_policy.primary_storage_base

    @property
    def fallback_storage_kind(self) -> str | None:
        return self.storage_policy.fallback_storage_kind

    @property
    def fallback_storage_base(self) -> str | None:
        return self.storage_policy.fallback_storage_base

    __table_args__ = lexicon_table_args(
        UniqueConstraint("storage_policy_id", "relative_path", name="uq_lexicon_voice_assets_storage_path"),
        CheckConstraint("content_scope IN ('word', 'definition', 'example')", name="ck_lexicon_voice_assets_content_scope"),
        CheckConstraint("voice_role IN ('female', 'male')", name="ck_lexicon_voice_assets_voice_role"),
        CheckConstraint(
            "((word_id IS NOT NULL)::int + (meaning_id IS NOT NULL)::int + (meaning_example_id IS NOT NULL)::int + "
            "(phrase_entry_id IS NOT NULL)::int + (phrase_sense_id IS NOT NULL)::int + (phrase_sense_example_id IS NOT NULL)::int) = 1",
            name="ck_lexicon_voice_assets_single_parent",
        ),
    )
