import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.meaning import Meaning
    from app.models.word_confusable import WordConfusable
    from app.models.word_form import WordForm
    from app.models.word_list_item import WordListItem
    from app.models.word_relation import WordRelation


class Word(Base):
    __tablename__ = "words"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    phonetics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    phonetic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phonetic_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phonetic_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    phonetic_enrichment_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("lexicon_enrichment_runs"), ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cefr_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    learner_part_of_speech: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    confusable_words: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    learner_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    frequency_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    word_forms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    meanings: Mapped[list["Meaning"]] = relationship(
        "Meaning", back_populates="word", cascade="all, delete-orphan"
    )
    word_list_items: Mapped[list["WordListItem"]] = relationship(
        "WordListItem", back_populates="word", cascade="all, delete-orphan"
    )
    confusable_entries: Mapped[list["WordConfusable"]] = relationship(
        "WordConfusable",
        back_populates="word",
        cascade="all, delete-orphan",
        order_by="WordConfusable.order_index",
    )
    form_entries: Mapped[list["WordForm"]] = relationship(
        "WordForm",
        back_populates="word",
        cascade="all, delete-orphan",
    )
    relations: Mapped[list["WordRelation"]] = relationship(
        "WordRelation",
        foreign_keys="WordRelation.word_id",
        back_populates="word",
        cascade="all, delete-orphan",
    )
    enrichment_jobs: Mapped[list["LexiconEnrichmentJob"]] = relationship(
        "LexiconEnrichmentJob",
        back_populates="word",
        cascade="all, delete-orphan",
    )
    phonetic_enrichment_run: Mapped["LexiconEnrichmentRun | None"] = relationship(
        "LexiconEnrichmentRun",
        back_populates="phonetic_words",
        foreign_keys=[phonetic_enrichment_run_id],
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("word", "language", name="uq_word_language"),
        CheckConstraint(
            "phonetic_confidence IS NULL OR (phonetic_confidence >= 0 AND phonetic_confidence <= 1)",
            name="ck_words_phonetic_confidence_range",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Word {self.word} ({self.language})>"
