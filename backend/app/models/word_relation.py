import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.meaning import Meaning
    from app.models.word import Word


class WordRelation(Base):
    __tablename__ = "word_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("words"), ondelete="CASCADE"), nullable=False, index=True
    )
    meaning_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("meanings"), ondelete="CASCADE"), nullable=True, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    related_word: Mapped[str] = mapped_column(String(255), nullable=False)
    related_word_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("words"), ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    enrichment_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("lexicon_enrichment_runs"), ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    word: Mapped["Word"] = relationship(
        "Word",
        foreign_keys=[word_id],
        back_populates="relations",
    )
    meaning: Mapped["Meaning | None"] = relationship("Meaning")
    related_word_record: Mapped["Word | None"] = relationship("Word", foreign_keys=[related_word_id])
    enrichment_run: Mapped["LexiconEnrichmentRun | None"] = relationship(
        "LexiconEnrichmentRun",
        back_populates="word_relations",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint(
            "word_id",
            "meaning_id",
            "relation_type",
            "related_word",
            name="uq_word_relation_scope",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_word_relations_confidence_range",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<WordRelation {self.relation_type}:{self.related_word}>"
